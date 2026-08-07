#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017Q minimal boundary-rule review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-017p-residence-geometry-segmentation-boundary-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-017P"
        or source.get("datasetFamily") != "CCCD"
        or source.get("datasetId") != "DATA-HO-014"
        or source.get("documentCount") != 15
        or source.get("evaluatedFieldCount") != 120
        or source.get("diagnosticFieldCount") != 45
    ):
        raise SystemExit("017P source scope/schema mismatch")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit("017P must be aggregate-only with prediction sealed")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit("017P must not use Ground Truth at selection")


def derive_rule(source: dict[str, Any]) -> dict[str, Any]:
    summary = source["evidence"]["bottomBoundaryCases"]
    overlap_rate = float(source["candidateRule"]["sealedLineIdOverlapRate"])
    max_overflow = int(summary["maxBottomOverflowPixels"])
    return {
        "name": "GEOMETRY_REGION_BOTTOM_EXTEND_TO_OBSERVED_LINE_BBOX",
        "field": "placeOfResidence",
        "guard": {
            "regionSource": "phase11_10_geometry_line_segmentation",
            "category": "bottom_boundary",
            "normalizedBboxPattern": "0.28,0.70,0.98,0.90",
        },
        "maxBottomExtensionPixels": max_overflow,
        "preserveMaxValueLines": 2,
        "lineIdRemapping": False,
        "lineIdOverlapRateInEvidence": overlap_rate,
        "status": "REVIEW_ONLY_LINE_ID_LIMITATION",
        "patchAuthorized": False,
        "replayAuthorized": False,
    }


def review(source: dict[str, Any], source_digest: str) -> dict[str, Any]:
    rule = derive_rule(source)
    return {
        "schemaVersion": "ocr-ho-v2-017q-residence-geometry-minimal-boundary-rule-review/1.0.0",
        "taskId": "OCR-HO-V2-017Q",
        "candidateVersion": source["candidateVersion"],
        "baselineVersion": source["baselineVersion"],
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "RESIDENCE_GEOMETRY_MINIMAL_BOUNDARY_RULE_REVIEW_ONLY",
        },
        "sourceDigests": {"artifact017p": source_digest},
        "evidence": {
            "caseCount": source["evidence"]["bottomBoundaryCases"]["caseCount"],
            "bottomOverflowCaseRate": source["candidateRule"]["bottomOverflowCaseRate"],
            "maxBottomOverflowPixels": source["evidence"]["bottomBoundaryCases"][
                "maxBottomOverflowPixels"
            ],
            "sealedLineIdOverlapRate": source["candidateRule"]["sealedLineIdOverlapRate"],
            "normalizedBboxCounts": source["evidence"]["bottomBoundaryCases"][
                "normalizedBboxCounts"
            ],
            "maxValueLinesCounts": source["evidence"]["bottomBoundaryCases"]["maxValueLinesCounts"],
        },
        "candidateRule": rule,
        "decision": {
            "status": "MINIMAL_BOUNDARY_RULE_REVIEW_HOLD",
            "recommendedNextTask": "OCR-HO-V2-017R",
            "recommendedNextDiagnostic": "RESIDENCE_GEOMETRY_PATCH_GATED_REVIEW",
            "reason": (
                "A bottom-only extension capped at the observed 15 pixels is the smallest "
                "candidate rule, but zero sealed line-ID overlap means the rule cannot be "
                "treated as sufficient without an independently gated review."
            ),
            "runtimeChanged": False,
            "patchAuthorized": False,
            "replayAuthorized": False,
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
    parser.add_argument("--artifact-017p", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.artifact_017p)
    validate_source(source)
    report = review(source, sha256(args.artifact_017p))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rule": report["candidateRule"]["name"],
                "maxBottomExtensionPixels": report["candidateRule"]["maxBottomExtensionPixels"],
                "patchAuthorized": False,
                "nextTask": "OCR-HO-V2-017R",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
