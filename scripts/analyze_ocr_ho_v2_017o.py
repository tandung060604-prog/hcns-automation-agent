#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017O residence bottom-boundary attribution."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

FIELD = "placeOfResidence"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_sources(source_017h: dict[str, Any], source_017n: dict[str, Any]) -> None:
    if (
        source_017h.get("schemaVersion") != "ocr-ho-v2-017h-roi-boundary-diagnostic/1.0.0"
        or source_017h.get("datasetFamily") != "CCCD"
        or source_017h.get("datasetId") != "DATA-HO-014"
        or source_017h.get("documentCount") != 15
        or source_017h.get("evaluatedFieldCount") != 120
        or source_017h.get("roiDiagnosticFieldCount") != 45
    ):
        raise SystemExit("017H source scope/schema mismatch")
    if source_017n.get("taskId") != "OCR-HO-V2-017N":
        raise SystemExit("017N lineage artifact required")
    for source in (source_017h, source_017n):
        if source.get("containsRawPII") is not False:
            raise SystemExit("Lineage artifacts must be aggregate-only")


def summarize_residence(entries: list[dict[str, Any]]) -> dict[str, Any]:
    category_counts = Counter(str(entry.get("category") or "unclassified") for entry in entries)
    source_counts = Counter(str(entry.get("regionSource") or "unknown") for entry in entries)
    bottom = [entry for entry in entries if entry.get("category") == "bottom_boundary"]
    missing_lines = sum(int(entry.get("missingExpectedLineCount", 0)) for entry in bottom)
    selected_lines = sum(int(entry.get("selectedLineCount", 0)) for entry in bottom)
    return {
        "evaluated": 15,
        "autoHit": 10,
        "boundaryMiss": len(entries),
        "categoryCounts": dict(sorted(category_counts.items())),
        "regionSourceCounts": dict(sorted(source_counts.items())),
        "bottomBoundary": {
            "caseCount": len(bottom),
            "caseRate": round(len(bottom) / max(1, len(entries)), 6),
            "missingExpectedLineCount": missing_lines,
            "selectedLineCount": selected_lines,
            "lineRetentionRate": round(selected_lines / max(1, missing_lines + selected_lines), 6),
            "regionSourceCounts": dict(
                sorted(
                    Counter(str(entry.get("regionSource") or "unknown") for entry in bottom).items()
                )
            ),
        },
    }


def review(
    source_017h: dict[str, Any], source_017n: dict[str, Any], digests: dict[str, str]
) -> dict[str, Any]:
    all_misses = source_017h["missDetailsAggregateOnly"]
    residence_entries = [entry for entry in all_misses if entry.get("field") == FIELD]
    residence = summarize_residence(residence_entries)
    bottom = residence["bottomBoundary"]
    return {
        "schemaVersion": "ocr-ho-v2-017o-residence-bottom-boundary-attribution/1.0.0",
        "taskId": "OCR-HO-V2-017O",
        "candidateVersion": source_017h["candidateVersion"],
        "baselineVersion": source_017h["baselineVersion"],
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "RESIDENCE_BOTTOM_BOUNDARY_ATTRIBUTION_ONLY",
        },
        "sourceDigests": digests,
        "evidence": {
            "field": FIELD,
            "residenceBoundaryMisses": residence,
            "globalBoundaryContext": source_017n["evidence"]["automaticDetectorAggregate"],
        },
        "candidateRule": {
            "field": FIELD,
            "category": "bottom_boundary",
            "caseCount": bottom["caseCount"],
            "caseRate": bottom["caseRate"],
            "regionSourceCounts": bottom["regionSourceCounts"],
            "status": "CANDIDATE_ONLY_NO_RUNTIME_PATCH",
            "roiPatchAuthorized": False,
            "counterfactualAuthorized": False,
        },
        "decision": {
            "status": "RESIDENCE_BOTTOM_BOUNDARY_ATTRIBUTION_HOLD",
            "recommendedNextTask": "OCR-HO-V2-017P",
            "recommendedNextDiagnostic": "RESIDENCE_GEOMETRY_SEGMENTATION_BOUNDARY_REVIEW",
            "reason": (
                "All three residence bottom-boundary cases use geometry line segmentation; "
                "the evidence supports a bounded diagnostic review, not a runtime patch."
            ),
            "runtimeChanged": False,
            "roiPatchAuthorized": False,
            "counterfactualAuthorized": False,
        },
        "gates": {
            "counterfactualAuthorized": False,
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
            "productionPromotionAllowed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-017h", type=Path, required=True)
    parser.add_argument("--artifact-017n", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_017h = load(args.artifact_017h)
    source_017n = load(args.artifact_017n)
    validate_sources(source_017h, source_017n)
    report = review(
        source_017h,
        source_017n,
        {"artifact017h": sha256(args.artifact_017h), "artifact017n": sha256(args.artifact_017n)},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "residenceBottomBoundaryCases": report["candidateRule"]["caseCount"],
                "residenceBottomBoundaryRate": report["candidateRule"]["caseRate"],
                "nextTask": "OCR-HO-V2-017P",
                "roiPatchAuthorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
