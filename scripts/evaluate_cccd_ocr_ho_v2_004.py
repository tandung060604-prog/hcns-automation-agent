#!/usr/bin/env python3
"""Evaluate OCR-HO-V2-004 field recovery on the old development set.

The script reuses only already-sealed OCR pages and the user-confirmed
development Ground Truth. It writes aggregate metrics without raw OCR text or
PII. The report is explicitly development-only; it cannot change the consumed
held-out evaluate-once report.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "ocr_lab" / "api"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from evaluate_cccd_phase11_5 import evaluate_variant, value  # noqa: E402
from phase11_cccd import (  # noqa: E402
    FIELD_ORDER,
    OCR_HO_V2_VERSION,
    ORIENTATION_POLICY,
    extract_cccd_fields,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def load_documents(
    data_root: Path,
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int]:
    documents: list[dict[str, Any]] = []
    out_of_scope_rotations = 0
    skipped_documents = 0
    sessions = data_root / "user_uploads" / "sessions"
    for record in manifest.get("records", []):
        session_id = str(record.get("sessionId", ""))
        session = sessions / session_id
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

        ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        assertions = ground_truth.get("verificationAssertions", {})
        if not (
            assertions.get("comparedWithImage") is True
            and assertions.get("allTextChecked") is True
        ):
            skipped_documents += 1
            continue

        result = json.loads(result_path.read_text(encoding="utf-8"))
        rotation = int(record.get("selectedRotationDegrees") or 0)
        if rotation != 0:
            out_of_scope_rotations += 1
            continue
        pages = result.get("phase11", {}).get("pages") or []
        if not pages:
            skipped_documents += 1
            continue

        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        candidate = extract_cccd_fields(
            pages,
            engine="PaddleOCR/PP-OCRv5",
        )
        if set(candidate.get("fields", {})) != set(FIELD_ORDER):
            skipped_documents += 1
            continue
        documents.append(
            {
                "documentIndex": int(record.get("documentIndex", 0)),
                "groundTruth": ground_truth.get("identityFields", {}),
                "phase11_5": baseline.get("fields", {}),
                "phase11_6": candidate.get("fields", {}),
                "durations": {
                    "phase11_5": result.get("phase11_5", {}).get("durationMs") or 0.0,
                    "phase11_6": result.get("phase11", {}).get("durationMs") or 0.0,
                },
            }
        )
    return documents, out_of_scope_rotations, skipped_documents


def exact_delta(
    documents: list[dict[str, Any]],
) -> tuple[int, int, dict[str, int], dict[str, int]]:
    regressions = 0
    improvements = 0
    regression_by_field: Counter[str] = Counter()
    improvement_by_field: Counter[str] = Counter()
    for document in documents:
        for field_name in FIELD_ORDER:
            expected = value(document["groundTruth"].get(field_name))
            if not expected:
                continue
            before = value(document["phase11_5"].get(field_name)) == expected
            after = value(document["phase11_6"].get(field_name)) == expected
            if before and not after:
                regressions += 1
                regression_by_field[field_name] += 1
            elif after and not before:
                improvements += 1
                improvement_by_field[field_name] += 1
    return (
        improvements,
        regressions,
        dict(sorted(improvement_by_field.items())),
        dict(sorted(regression_by_field.items())),
    )


def build_gate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    improvements, regressions, improved_by_field, regressed_by_field = exact_delta(
        documents
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
        "schemaErrorsZero": all(
            set(document["phase11_6"]) == set(FIELD_ORDER)
            for document in documents
        ),
        "manualReviewPolicy": True,
    }
    return {
        "status": "DEVELOPMENT_PASS" if all(checks.values()) else "DEVELOPMENT_FAIL",
        "productionPromotionAllowed": False,
        "checks": checks,
        "exactImprovementCount": improvements,
        "exactRegressionCount": regressions,
        "exactImprovementByField": improved_by_field,
        "exactRegressionByField": regressed_by_field,
    }


def markdown(report: dict[str, Any]) -> str:
    baseline = report["metrics"]["baseline_phase11_5"]
    candidate = report["metrics"]["ocr_ho_v2_004"]

    def row(label: str, key: str, inverse: bool = False) -> str:
        return f"| {label} | {baseline[key]:.2%} | {candidate[key]:.2%} |"

    lines = [
        "# OCR-HO-V2-004 Development Comparison",
        "",
        f"- Development documents in scope: {report['documentCount']}",
        f"- Out-of-scope rotations: {report['outOfScopeRotationDocumentCount']}",
        f"- Candidate: OCR-HO-V2 v{report['candidateVersion']} ({report['orientationPolicy']})",
        f"- Decision: **{report['promotionGate']['status']}**",
        (
            "- This is development evidence only; the consumed held-out "
            "evaluate-once report is unchanged."
        ),
        "",
        "| Metric | Baseline Phase 11.5 | OCR-HO-V2 v1.1 |",
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
        "- No raw OCR text, Ground Truth value, or PII is included in this report.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report_dir = args.data_root / "output" / "phase11" / "reports"
    json_path = report_dir / "CCCD_OCR_HO_V2_004_DEVELOPMENT_COMPARISON.json"
    md_path = report_dir / "CCCD_OCR_HO_V2_004_DEVELOPMENT_COMPARISON.md"
    if (json_path.is_file() or md_path.is_file()) and not args.overwrite:
        raise FileExistsError("Report exists; pass --overwrite")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    documents, out_of_scope_rotations, skipped_documents = load_documents(
        args.data_root,
        manifest,
    )
    baseline = evaluate_variant(documents, "phase11_5")
    candidate = evaluate_variant(documents, "phase11_6")
    report = {
        "schemaVersion": "ocr-ho-v2-004-evaluation/1.0.0",
        "containsRawPII": False,
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "candidateVersion": OCR_HO_V2_VERSION,
        "orientationPolicy": ORIENTATION_POLICY,
        "documentCount": len(documents),
        "outOfScopeRotationDocumentCount": out_of_scope_rotations,
        "skippedDocumentCount": skipped_documents,
        "metrics": {
            "baseline_phase11_5": baseline,
            "ocr_ho_v2_004": candidate,
        },
        "promotionGate": build_gate(baseline, candidate, documents),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["promotionGate"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
