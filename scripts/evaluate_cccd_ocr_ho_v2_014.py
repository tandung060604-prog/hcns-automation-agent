#!/usr/bin/env python3
"""Aggregate-only evaluation for OCR-HO-V2 v11.10 development replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_cccd_phase11_5 import evaluate_variant, value  # noqa: E402
from ocr_ho_v2_014_evaluation import gates  # noqa: E402
from phase11_5_cccd import FIELD_ORDER  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    root = args.data_root.resolve()
    sessions = root / "user_uploads-sessions"
    if not sessions.is_dir():
        sessions = root / "user_uploads" / "sessions"
    report_path = (
        root / "output" / "phase11" / "reports" / "CCCD_OCR_HO_V2_014_DEVELOPMENT_COMPARISON.json"
    )
    if report_path.exists() and not args.overwrite:
        raise SystemExit("Report exists; pass --overwrite")
    documents: list[dict[str, Any]] = []
    baseline_versions: set[str] = set()
    for record in json.loads(args.manifest.read_text(encoding="utf-8")).get("records", []):
        session = sessions / str(record.get("sessionId", ""))
        ground_truth_path = session / "phase10" / "ground_truth.json"
        baseline_path = session / "phase11_9_v2" / "field_consensus.json"
        baseline_version = "11.9.1"
        if not baseline_path.is_file():
            baseline_path = session / "phase11_5" / "identity_card.json"
            baseline_version = "11.5"
        candidate_path = session / "phase11_10_v2" / "field_consensus.json"
        paths = (ground_truth_path, baseline_path, candidate_path)
        if (
            not all(path.is_file() for path in paths)
            or int(record.get("selectedRotationDegrees") or 0) != 0
        ):
            continue
        ground_truth, baseline, candidate = (
            json.loads(path.read_text(encoding="utf-8")) for path in paths
        )
        assertions = ground_truth.get("verificationAssertions", {})
        if not (assertions.get("comparedWithImage") and assertions.get("allTextChecked")):
            continue
        baseline_fields = baseline.get("identityCard", {}).get("fields") or baseline.get(
            "fields", {}
        )
        documents.append(
            {
                "groundTruth": ground_truth.get("identityFields", {}),
                "baseline": baseline_fields,
                "phase11_10": candidate.get("identityCard", {}).get("fields", {}),
                "durations": {"baseline": 0.0, "phase11_10": 0.0},
            }
        )
        baseline_versions.add(baseline_version)
    if not documents:
        raise SystemExit("No eligible development documents")
    before, after = (
        evaluate_variant(documents, "baseline"),
        evaluate_variant(documents, "phase11_10"),
    )
    improvements = regressions = 0
    for document in documents:
        for field in FIELD_ORDER:
            expected = value(document["groundTruth"].get(field))
            if expected:
                before_exact = value(document["baseline"].get(field)) == expected
                after_exact = value(document["phase11_10"].get(field)) == expected
                improvements += int(not before_exact and after_exact)
                regressions += int(before_exact and not after_exact)
    all_manual = all(
        field.get("status") != "accepted"
        for document in documents
        for field in document["phase11_10"].values()
    )
    baseline_version = "11.9.1" if baseline_versions == {"11.9.1"} else "mixed"
    baseline_key = "baseline_phase11_9" if baseline_version == "11.9.1" else "baseline_latest"
    report = {
        "schemaVersion": "ocr-ho-v2-014-evaluation/1.0.0",
        "candidateVersion": "11.10.0",
        "baselineVersion": baseline_version,
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": len(documents),
        "containsRawPII": False,
        "metrics": {baseline_key: before, "ocr_ho_v2_014": after},
        "gates": gates(
            before,
            after,
            improvements=improvements,
            regressions=regressions,
            schema_errors=0,
            all_manual_review=all_manual,
        ),
        "exactImprovementCount": improvements,
        "exactRegressionCount": regressions,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["gates"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
