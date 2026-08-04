#!/usr/bin/env python3
"""Compare the OCR-HO-V2-006 ROI candidate on the private dev replay.

The candidate fields are loaded from the private ``phase11_6_v2`` evidence
written by the replay runner.  Ground Truth is used only by this evaluator for
scoring; it is never passed to candidate selection.  The report is aggregate
only and the official 14-document evaluate-once artifact is out of scope.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "ocr_lab" / "api"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from evaluate_cccd_phase11_5 import evaluate_variant, value  # noqa: E402
from phase11_5_cccd import FIELD_ORDER  # noqa: E402
from phase11_6_cccd_v2 import (  # noqa: E402
    CANDIDATE_VERSION,
    POLICY_ID,
    PROTECTED_FIELDS,
    TARGET_FIELDS,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def session_root(data_root: Path) -> Path:
    # The archived snapshot uses the hyphenated layout.  Prefer it when both
    # layouts exist so a stale empty compatibility directory cannot be chosen.
    for candidate in (
        data_root / "user_uploads-sessions",
        data_root / "user_uploads" / "sessions",
    ):
        if candidate.is_dir():
            return candidate
    raise RuntimeError("No development session root found")


def load_documents(
    data_root: Path,
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int]:
    documents: list[dict[str, Any]] = []
    out_of_scope_rotations = 0
    skipped_documents = 0
    sessions = session_root(data_root)
    for record in manifest.get("records", []):
        session = sessions / str(record.get("sessionId", ""))
        ground_truth_path = session / "phase10" / "ground_truth.json"
        baseline_path = session / "phase11_5" / "identity_card.json"
        candidate_path = session / "phase11_6_v2" / "field_consensus.json"
        result_path = session / "result.json"
        if not all(
            path.is_file()
            for path in (
                ground_truth_path,
                baseline_path,
                candidate_path,
                result_path,
            )
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
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        baseline_fields = baseline.get("fields") or {}
        candidate_fields = (candidate.get("identityCard") or {}).get("fields") or {}
        if set(baseline_fields) != set(FIELD_ORDER) or set(candidate_fields) != set(
            FIELD_ORDER
        ):
            skipped_documents += 1
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        documents.append(
            {
                "documentIndex": int(record.get("documentIndex", 0)),
                "groundTruth": ground_truth.get("identityFields", {}),
                "phase11_5": baseline_fields,
                "ocr_ho_v2_006": candidate_fields,
                "durations": {
                    "phase11_5": result.get("phase11_5", {}).get("durationMs") or 0.0,
                    "ocr_ho_v2_006": result.get("phase11_6_v2", {}).get("durationMs")
                    or 0.0,
                },
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
            after = value(document["ocr_ho_v2_006"].get(field_name)) == expected
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


def schema_error_count(documents: list[dict[str, Any]]) -> int:
    schema_path = REPO_ROOT / "schemas" / "vietnam_identity_card_phase11_6.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = 0
    for document in documents:
        candidate_fields = document["ocr_ho_v2_006"]
        if set(candidate_fields) != set(FIELD_ORDER):
            errors += 1
            continue
        # The field-level comparison stores only the schema payload; assemble
        # the same envelope emitted by the candidate API before validation.
        card = {
            "schemaVersion": "11.6.0",
            "documentType": "VIETNAM_CITIZEN_ID_FRONT",
            "extractionPolicy": "phase11.6-cccd-address-lines-name-selection",
            "policyMode": "SHADOW_REVIEW_ONLY",
            "fields": candidate_fields,
            "summary": {
                "expectedFieldCount": len(FIELD_ORDER),
                "presentFieldCount": sum(
                    field.get("value") is not None
                    for field in candidate_fields.values()
                ),
                "acceptedFieldCount": sum(
                    field.get("status") == "accepted"
                    for field in candidate_fields.values()
                ),
                "needsReviewFieldCount": sum(
                    field.get("status") == "needs_review"
                    for field in candidate_fields.values()
                ),
                "notFoundFieldCount": sum(
                    field.get("status") == "not_found"
                    for field in candidate_fields.values()
                ),
                "documentCompleteness": round(
                    sum(field.get("value") is not None for field in candidate_fields.values())
                    / len(FIELD_ORDER),
                    6,
                ),
                "acceptedRate": round(
                    sum(field.get("status") == "accepted" for field in candidate_fields.values())
                    / len(FIELD_ORDER),
                    6,
                ),
                "readyForAutomaticUse": False,
                "candidateVersion": CANDIDATE_VERSION,
                "targetFields": list(TARGET_FIELDS),
                "guardedRecoveryAvailableCount": 0,
                "guardedRecoveryAppliedCount": 0,
            },
        }
        try:
            validate(card, schema)
        except ValidationError:
            errors += 1
    return errors


def build_gate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    documents: list[dict[str, Any]],
    schema_errors: int,
) -> dict[str, Any]:
    improvements, regressions, improved_by_field, regressed_by_field = exact_delta(
        documents
    )
    manual_review = all(
        field.get("status") != "accepted"
        for document in documents
        for field in document["ocr_ho_v2_006"].values()
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
        "hasExactImprovement": improvements >= 1,
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
            for field in document["ocr_ho_v2_006"].values()
        ),
    }


def markdown(report: dict[str, Any]) -> str:
    baseline = report["metrics"]["baseline_phase11_5"]
    candidate = report["metrics"]["ocr_ho_v2_006"]

    def row(label: str, key: str) -> str:
        return f"| {label} | {baseline[key]:.2%} | {candidate[key]:.2%} |"

    lines = [
        "# OCR-HO-V2-006 Development Comparison",
        "",
        f"- Development documents in scope: {report['documentCount']}",
        f"- Candidate: OCR-HO-V2 v{report['candidateVersion']} ({report['policyId']})",
        f"- Target fields: {', '.join(report['targetFields'])}",
        f"- Decision: **{report['promotionGate']['status']}**",
        "- Production promotion: **not allowed**; this is a shadow development evaluation.",
        "- Candidate selector input: ROI OCR evidence only; Ground Truth is scoring-only.",
        "",
        "| Metric | Baseline Phase 11.5 | OCR-HO-V2-006 |",
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
        f"- Schema errors: {report['promotionGate']['schemaErrorCount']}.",
        f"- Manual-review fields: {report['promotionGate']['manualReviewFieldCount']}.",
        "- No raw OCR text, Ground Truth value, or PII is included in this report.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report_dir = args.data_root / "output" / "phase11" / "reports"
    json_path = report_dir / "CCCD_OCR_HO_V2_006_DEVELOPMENT_COMPARISON.json"
    md_path = report_dir / "CCCD_OCR_HO_V2_006_DEVELOPMENT_COMPARISON.md"
    if (json_path.is_file() or md_path.is_file()) and not args.overwrite:
        raise FileExistsError("Report exists; pass --overwrite")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    documents, out_of_scope_rotations, skipped_documents = load_documents(
        args.data_root,
        manifest,
    )
    if not documents:
        raise RuntimeError("No eligible development documents found")
    baseline = evaluate_variant(documents, "phase11_5")
    candidate = evaluate_variant(documents, "ocr_ho_v2_006")
    report = {
        "schemaVersion": "ocr-ho-v2-006-evaluation/1.0.0",
        "containsRawPII": False,
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "candidateVersion": CANDIDATE_VERSION,
        "policyId": POLICY_ID,
        "targetFields": list(TARGET_FIELDS),
        "protectedFields": list(PROTECTED_FIELDS),
        "documentCount": len(documents),
        "outOfScopeRotationDocumentCount": out_of_scope_rotations,
        "skippedDocumentCount": skipped_documents,
        "metrics": {
            "baseline_phase11_5": baseline,
            "ocr_ho_v2_006": candidate,
        },
        "promotionGate": build_gate(
            baseline,
            candidate,
            documents,
            schema_error_count(documents),
        ),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["promotionGate"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
