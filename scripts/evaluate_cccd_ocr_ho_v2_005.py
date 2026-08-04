#!/usr/bin/env python3
"""Evaluate the guarded OCR-HO-V2-005 candidate on development evidence.

The evaluator consumes only the already-sealed Phase 11.5 OCR evidence and
the user-reviewed development Ground Truth for scoring. Ground Truth is never
passed to the candidate selector and no raw field values are written to the
aggregate report. The official held-out evaluate-once artifact is out of scope.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "ocr_lab" / "api"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from evaluate_cccd_phase11_5 import evaluate_variant, value  # noqa: E402
from phase11_5_cccd import FIELD_ORDER  # noqa: E402
from phase11_5_cccd_v2 import (  # noqa: E402
    OCR_HO_V2_005_ORIENTATION_POLICY,
    OCR_HO_V2_005_POLICY_ID,
    OCR_HO_V2_005_SCOPE,
    OCR_HO_V2_005_VERSION,
    build_shadow_fields,
    summarize_recovery,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _session_root(data_root: Path) -> Path:
    sessions = data_root / "user_uploads" / "sessions"
    if sessions.is_dir():
        return sessions
    sessions = data_root / "user_uploads-sessions"
    if sessions.is_dir():
        return sessions
    raise RuntimeError("No development session root found")


def load_documents(
    data_root: Path,
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int]:
    """Load only complete, reviewed, fixed-0-degree development sessions."""

    documents: list[dict[str, Any]] = []
    out_of_scope_rotations = 0
    skipped_documents = 0
    sessions = _session_root(data_root)
    for record in manifest.get("records", []):
        session = sessions / str(record.get("sessionId", ""))
        ground_truth_path = session / "phase10" / "ground_truth.json"
        baseline_path = session / "phase11_5" / "identity_card.json"
        result_path = session / "result.json"
        if not (
            ground_truth_path.is_file()
            and baseline_path.is_file()
            and result_path.is_file()
        ):
            skipped_documents += 1
            continue
        if int(record.get("selectedRotationDegrees") or 0) != 0:
            out_of_scope_rotations += 1
            continue
        ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        assertions = ground_truth.get("verificationAssertions", {})
        if not (
            assertions.get("comparedWithImage") is True
            and assertions.get("allTextChecked") is True
        ):
            skipped_documents += 1
            continue
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_fields = baseline.get("fields") or {}
        if set(baseline_fields) != set(FIELD_ORDER):
            skipped_documents += 1
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        candidate_fields = build_shadow_fields(copy.deepcopy(baseline_fields))
        documents.append(
            {
                "documentIndex": int(record.get("documentIndex", 0)),
                "groundTruth": ground_truth.get("identityFields", {}),
                "phase11_5": baseline_fields,
                "ocr_ho_v2_005": candidate_fields,
                "durations": {
                    "phase11_5": result.get("phase11_5", {}).get("durationMs") or 0.0,
                    "ocr_ho_v2_005": result.get("phase11_5", {}).get("durationMs") or 0.0,
                },
                "recovery": summarize_recovery(candidate_fields),
            }
        )
    return documents, out_of_scope_rotations, skipped_documents


def exact_delta(
    documents: list[dict[str, Any]],
) -> tuple[int, int, dict[str, int], dict[str, int]]:
    improvements = 0
    regressions = 0
    improved_by_field: Counter[str] = Counter()
    regressed_by_field: Counter[str] = Counter()
    for document in documents:
        for field_name in FIELD_ORDER:
            expected = value(document["groundTruth"].get(field_name))
            if not expected:
                continue
            before = value(document["phase11_5"].get(field_name)) == expected
            after = value(document["ocr_ho_v2_005"].get(field_name)) == expected
            if after and not before:
                improvements += 1
                improved_by_field[field_name] += 1
            elif before and not after:
                regressions += 1
                regressed_by_field[field_name] += 1
    return (
        improvements,
        regressions,
        dict(sorted(improved_by_field.items())),
        dict(sorted(regressed_by_field.items())),
    )


def aggregate_recovery(documents: list[dict[str, Any]]) -> dict[str, Any]:
    totals = Counter()
    by_field: dict[str, Counter[str]] = {
        field_name: Counter() for field_name in FIELD_ORDER
    }
    for document in documents:
        recovery = document["recovery"]
        totals.update(
            {
                key: int(recovery.get(key) or 0)
                for key in (
                    "candidateAvailableCount",
                    "guardedRecoveryAppliedCount",
                    "baselineRecoveryRequiredCount",
                )
            }
        )
        for field_name, row in recovery["byField"].items():
            by_field[field_name].update(row)
    return {
        "candidateAvailableCount": totals["candidateAvailableCount"],
        "guardedRecoveryAppliedCount": totals["guardedRecoveryAppliedCount"],
        "baselineRecoveryRequiredCount": totals["baselineRecoveryRequiredCount"],
        "byField": {
            field_name: dict(sorted(counter.items()))
            for field_name, counter in by_field.items()
        },
    }


def build_gate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    improvements, regressions, improved_by_field, regressed_by_field = exact_delta(
        documents
    )
    schema_errors = sum(
        int(set(document["ocr_ho_v2_005"]) != set(FIELD_ORDER))
        for document in documents
    )
    manual_review = all(
        field.get("status") != "accepted"
        for document in documents
        for field in document["ocr_ho_v2_005"].values()
    )
    checks = {
        "strictExactMatchNotWorse": candidate["strictFieldExactMatch"]
        >= baseline["strictFieldExactMatch"],
        "asciiExactMatchNotWorse": candidate["asciiFieldExactMatch"]
        >= baseline["asciiFieldExactMatch"],
        "cerNotWorse": candidate["cer"] <= baseline["cer"],
        "derNotWorse": candidate["der"] <= baseline["der"],
        "fieldPresenceNotWorse": candidate["fieldPresence"]
        >= baseline["fieldPresence"],
        "noExactRegression": regressions == 0,
        "schemaErrorsZero": schema_errors == 0,
        "manualReviewPolicy": manual_review,
    }
    return {
        "status": "DEVELOPMENT_PASS" if all(checks.values()) else "DEVELOPMENT_FAIL",
        "productionPromotionAllowed": False,
        "checks": checks,
        "exactImprovementCount": improvements,
        "exactRegressionCount": regressions,
        "exactImprovementByField": improved_by_field,
        "exactRegressionByField": regressed_by_field,
        "schemaErrorCount": schema_errors,
        "manualReviewFieldCount": sum(
            field.get("status") != "accepted"
            for document in documents
            for field in document["ocr_ho_v2_005"].values()
        ),
    }


def markdown(report: dict[str, Any]) -> str:
    baseline = report["metrics"]["baseline_phase11_5"]
    candidate = report["metrics"]["ocr_ho_v2_005"]

    def row(label: str, key: str) -> str:
        return f"| {label} | {baseline[key]:.2%} | {candidate[key]:.2%} |"

    lines = [
        "# OCR-HO-V2-005 Development Comparison",
        "",
        f"- Development documents in scope: {report['documentCount']}",
        f"- Candidate: OCR-HO-V2 v{report['candidateVersion']} ({report['policyId']})",
        f"- Orientation policy: `{report['orientationPolicy']}`",
        f"- Decision: **{report['promotionGate']['status']}**",
        "- Production promotion: **not allowed**; this is a shadow development evaluation.",
        (
            "- Candidate selector input: sealed Phase 11.5 OCR evidence only; "
            "Ground Truth is scoring-only."
        ),
        "",
        "| Metric | Baseline Phase 11.5 | OCR-HO-V2-005 |",
        "|---|---:|---:|",
        row("Strict Field Exact Match", "strictFieldExactMatch"),
        row("ASCII Field Exact Match", "asciiFieldExactMatch"),
        row("CER", "cer"),
        row("Base CER", "baseCer"),
        row("DER", "der"),
        row("Field Presence", "fieldPresence"),
        row("Accepted Precision", "acceptedPrecision"),
        "",
        (
            "- Exact improvements/regressions: "
            f"{report['promotionGate']['exactImprovementCount']}/"
            f"{report['promotionGate']['exactRegressionCount']}."
        ),
        (
            "- Guarded recoveries applied: "
            f"{report['recovery']['guardedRecoveryAppliedCount']} of "
            f"{report['recovery']['baselineRecoveryRequiredCount']} baseline-risk fields."
        ),
        "- OCR output remains `MANUAL_REVIEW`; no candidate is auto-accepted.",
        "- No raw OCR text, Ground Truth value, or PII is included in this report.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report_dir = args.data_root / "output" / "phase11" / "reports"
    json_path = report_dir / "CCCD_OCR_HO_V2_005_DEVELOPMENT_COMPARISON.json"
    md_path = report_dir / "CCCD_OCR_HO_V2_005_DEVELOPMENT_COMPARISON.md"
    if (json_path.is_file() or md_path.is_file()) and not args.overwrite:
        raise FileExistsError("Report exists; pass --overwrite")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    documents, out_of_scope_rotations, skipped_documents = load_documents(
        args.data_root,
        manifest,
    )
    if not documents:
        raise RuntimeError(
            "No eligible development documents found; refusing to emit a vacuous pass"
        )
    baseline = evaluate_variant(documents, "phase11_5")
    candidate = evaluate_variant(documents, "ocr_ho_v2_005")
    report = {
        "schemaVersion": "ocr-ho-v2-005-evaluation/1.0.0",
        "containsRawPII": False,
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "candidateVersion": OCR_HO_V2_005_VERSION,
        "policyId": OCR_HO_V2_005_POLICY_ID,
        "scope": OCR_HO_V2_005_SCOPE,
        "orientationPolicy": OCR_HO_V2_005_ORIENTATION_POLICY,
        "documentCount": len(documents),
        "outOfScopeRotationDocumentCount": out_of_scope_rotations,
        "skippedDocumentCount": skipped_documents,
        "metrics": {
            "baseline_phase11_5": baseline,
            "ocr_ho_v2_005": candidate,
        },
        "recovery": aggregate_recovery(documents),
        "promotionGate": build_gate(baseline, candidate, documents),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["promotionGate"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
