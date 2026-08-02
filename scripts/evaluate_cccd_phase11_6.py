#!/usr/bin/env python3
"""Compare locked Phase 11.5 and Phase 11.6 on the same 15 CCCD development set."""

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
from phase11_6_cccd import FIELD_ORDER  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def load_documents(data_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    sessions = data_root / "user_uploads" / "sessions"
    for record in manifest.get("records", []):
        session = sessions / str(record.get("sessionId", ""))
        ground_truth_path = session / "phase10" / "ground_truth.json"
        phase11_5_path = session / "phase11_5" / "identity_card.json"
        result_path = session / "result.json"
        if not (
            ground_truth_path.is_file()
            and phase11_5_path.is_file()
            and result_path.is_file()
        ):
            continue
        ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        assertions = ground_truth.get("verificationAssertions", {})
        if not (
            assertions.get("comparedWithImage") is True
            and assertions.get("allTextChecked") is True
        ):
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("phase11_6", {}).get("status") != "COMPLETE":
            continue
        documents.append(
            {
                "groundTruth": ground_truth.get("identityFields", {}),
                "phase11_5": json.loads(
                    phase11_5_path.read_text(encoding="utf-8")
                ).get("fields", {}),
                "phase11_6": result.get("phase11", {})
                .get("identityCard", {})
                .get("fields", {}),
                "durations": {
                    "phase11_5": result.get("phase11_5", {}).get("durationMs") or 0.0,
                    "phase11_6": result.get("phase11_6", {}).get("durationMs") or 0.0,
                },
            }
        )
    return documents


def gate(
    before: dict[str, Any],
    after: dict[str, Any],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    regressions = 0
    improvements = 0
    regressions_by_field: Counter[str] = Counter()
    improvements_by_field: Counter[str] = Counter()
    for document in documents:
        for field_name in FIELD_ORDER:
            expected = value(document["groundTruth"].get(field_name))
            if not expected:
                continue
            before_exact = value(document["phase11_5"].get(field_name)) == expected
            after_exact = value(document["phase11_6"].get(field_name)) == expected
            regressions += int(before_exact and not after_exact)
            improvements += int(not before_exact and after_exact)
            regressions_by_field[field_name] += int(before_exact and not after_exact)
            improvements_by_field[field_name] += int(not before_exact and after_exact)
    full_name_ascii = after["perField"].get("fullName", {}).get("asciiExactMatch", 0.0)
    address_ascii = sum(
        after["perField"].get(name, {}).get("asciiExactMatch", 0.0)
        for name in ("placeOfOrigin", "placeOfResidence")
    ) / 2
    checks = {
        "strictExactMatchNotWorse": (
            after["strictFieldExactMatch"] >= before["strictFieldExactMatch"]
        ),
        "asciiExactMatchNotWorse": (
            after["asciiFieldExactMatch"] >= before["asciiFieldExactMatch"]
        ),
        "cerNotWorse": after["cer"] <= before["cer"],
        "derNotWorse": after["der"] <= before["der"],
        "acceptedPrecision": after["acceptedPrecision"] == 1.0,
        "noExactRegression": regressions == 0,
        "fullNameAsciiExactMatch": full_name_ascii >= 0.90,
        "addressAsciiExactMatch": address_ascii >= 0.85,
        "fieldPresence": after["fieldPresence"] >= 0.95,
        "noSensitiveFalseAcceptance": (
            after["sensitiveFieldFalseAcceptanceCount"] == 0
        ),
    }
    return {
        "status": (
            "READY_FOR_NEW_HELDOUT"
            if all(checks.values())
            else "SHADOW_REVIEW_ONLY"
        ),
        "checks": checks,
        "exactImprovementCount": improvements,
        "exactRegressionCount": regressions,
        "exactImprovementByField": dict(sorted(improvements_by_field.items())),
        "exactRegressionByField": dict(sorted(regressions_by_field.items())),
        "fullNameAsciiExactMatch": full_name_ascii,
        "addressAsciiExactMatch": round(address_ascii, 6),
    }


def markdown(report: dict[str, Any]) -> str:
    before = report["metrics"]["phase11_5"]
    after = report["metrics"]["phase11_6"]

    def row(label: str, key: str) -> str:
        return f"| {label} | {before[key]:.2%} | {after[key]:.2%} |"

    return "\n".join(
        [
            "# Phase 11.6 CCCD Development Comparison",
            "",
            f"- Documents: {report['documentCount']}",
            f"- Decision: **{report['promotionGate']['status']}**",
            "- Same locked 15-document development/regression set; not held-out evidence.",
            "",
            "| Metric | Phase 11.5 | Phase 11.6 |",
            "|---|---:|---:|",
            row("Strict Field Exact Match", "strictFieldExactMatch"),
            row("ASCII Field Exact Match", "asciiFieldExactMatch"),
            row("CER", "cer"),
            row("Base CER", "baseCer"),
            row("DER", "der"),
            row("Character Omission Rate", "characterOmissionRate"),
            row("Field Presence", "fieldPresence"),
            row("Accepted Precision", "acceptedPrecision"),
            row("Accepted Coverage", "acceptedCoverage"),
            row("Region Selection Accuracy", "regionSelectionAccuracy"),
            "",
            (
                "- Exact improvements/regressions: "
                f"{report['promotionGate']['exactImprovementCount']}/"
                f"{report['promotionGate']['exactRegressionCount']}."
            ),
            (
                "- Mean duration: "
                f"11.5 {before['meanDurationMs']:.1f} ms/document; "
                f"11.6 {after['meanDurationMs']:.1f} ms/document."
            ),
            "",
            "No raw OCR text, Ground Truth value, or PII is included in this report.",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    report_dir = args.data_root / "output" / "phase11" / "reports"
    json_path = report_dir / "CCCD_PHASE11_6_DEVELOPMENT_COMPARISON.json"
    md_path = report_dir / "CCCD_PHASE11_6_DEVELOPMENT_COMPARISON.md"
    if json_path.is_file() and not args.overwrite:
        raise FileExistsError("Report exists; pass --overwrite")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    documents = load_documents(args.data_root, manifest)
    before = evaluate_variant(documents, "phase11_5")
    after = evaluate_variant(documents, "phase11_6")
    report = {
        "schemaVersion": "phase11.6-evaluation/1.0.0",
        "containsRawPII": False,
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": len(documents),
        "metrics": {"phase11_5": before, "phase11_6": after},
        "promotionGate": gate(before, after, documents),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["promotionGate"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
