#!/usr/bin/env python3
"""Aggregate-only review of the 017X residence patch implementation surface."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

RULE = {
    "name": "GEOMETRY_REGION_BOTTOM_EXTEND_TO_OBSERVED_LINE_BBOX",
    "field": "placeOfResidence",
    "maxBottomExtensionPixels": 15,
    "preserveMaxValueLines": 2,
    "lineIdRemapping": False,
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion") != "ocr-ho-v2-017w-minimal-patch-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-017W"
        or source.get("candidateVersion") != "11.10.2"
        or source.get("baselineVersion") != "11.9.1"
        or source.get("datasetFamily") != "CCCD"
        or source.get("datasetId") != "DATA-HO-014"
        or source.get("datasetRole") != "DEVELOPMENT_REGRESSION"
        or source.get("documentCount") != 15
        or source.get("evaluatedFieldCount") != 120
        or source.get("diagnosticFieldCount") != 45
        or source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("review", {}).get("minimalSurfaceGate") != "PASS"
        or source.get("review", {}).get("patchAuthorized") is not False
        or source.get("review", {}).get("replayAuthorized") is not False
    ):
        raise SystemExit("017W source scope/authorization mismatch")


def inspect_runtime(source_text: str) -> dict[str, Any]:
    geometry_call = source_text.find("geometry_bboxes, geometry_ids = _geometry_line_bboxes")
    source_assignment = source_text.find(
        'region["regionSource"] = "phase11_10_geometry_line_segmentation"'
    )
    markers = {
        "geometryFunction": "def _geometry_line_bboxes(" in source_text,
        "fieldLocator": "def locate_field_regions(" in source_text,
        "bottomSelector": "center_y <= bottom" in source_text,
        "maxTwoValueLines": "groups[: (1 if field_name == \"fullName\" else 2)]" in source_text,
        "geometryLineIdsPreserved": 'region["lineIds"] = geometry_ids' in source_text,
        "detectorPathPresent": '"phase11_10_detector_lines"' in source_text,
        "geometryPathPresent": '"phase11_10_geometry_line_segmentation"' in source_text,
    }
    guard_placement = (
        "PASS"
        if geometry_call >= 0 and source_assignment >= 0 and source_assignment < geometry_call
        else "HOLD"
    )
    return {
        "affectedFile": "apps/ocr_lab/api/phase11_10_cccd_v2.py",
        "affectedFunctions": ["locate_field_regions", "_geometry_line_bboxes"],
        "markers": markers,
        "geometryCallBeforeRegionSourceAssignment": (
            geometry_call >= 0 and source_assignment > geometry_call >= 0
        ),
        "guardPlacementGate": guard_placement,
    }


def review(source_017w: dict[str, Any], runtime_text: str) -> dict[str, Any]:
    runtime = inspect_runtime(runtime_text)
    markers = runtime["markers"]
    bounded = source_017w.get("candidateRule") == RULE
    line_cap = markers["maxTwoValueLines"] and markers["geometryLineIdsPreserved"]
    detector_isolation = markers["detectorPathPresent"] and markers["geometryPathPresent"]
    guard = runtime["guardPlacementGate"] == "PASS"
    implementation_gate = bounded and line_cap and detector_isolation and guard
    return {
        "schemaVersion": "ocr-ho-v2-017x-minimal-implementation-review/1.0.0",
        "taskId": "OCR-HO-V2-017X",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
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
            "diagnostic": "MINIMAL_RESIDENCE_PATCH_IMPLEMENTATION_REVIEW_ONLY",
        },
        "candidateRule": RULE,
        "runtimeInspection": runtime,
        "implementationReview": {
            "boundedRuleGate": "PASS" if bounded else "HOLD",
            "lineCapAndMappingGate": "PASS" if line_cap else "HOLD",
            "detectorIsolationGate": "PASS" if detector_isolation else "HOLD",
            "guardPlacementGate": runtime["guardPlacementGate"],
            "implementationReviewGate": "PASS" if implementation_gate else "HOLD",
            "qualityImprovementProven": False,
            "runtimeChanged": False,
            "patchAuthorized": False,
            "replayAuthorized": False,
            "counterfactualAuthorized": False,
        },
        "decision": {
            "status": (
                "IMPLEMENTATION_REVIEW_READY_FOR_EXPLICIT_PATCH"
                if implementation_gate
                else "IMPLEMENTATION_REVIEW_HOLD_GUARD_PLACEMENT"
            ),
            "recommendedNextTask": "OCR-HO-V2-017Y",
            "recommendedNextDiagnostic": "MINIMAL_GUARD_PLACEMENT_REVIEW",
            "reason": (
                "The existing runtime assigns the geometry region source after the geometry "
                "bbox call; place the 15px guard only after isolating the geometry fallback "
                "from detector-selected lines. No code change is made in 017X."
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
    parser.add_argument("--artifact-017w", type=Path, required=True)
    parser.add_argument("--runtime-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.artifact_017w)
    validate_source(source)
    report = review(source, args.runtime_file.read_text(encoding="utf-8"))
    report["sourceDigests"] = {
        "artifact017wSha256": sha256(args.artifact_017w),
        "runtimeSourceSha256": sha256(args.runtime_file),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "implementationReviewGate": report["implementationReview"][
                    "implementationReviewGate"
                ],
                "patchAuthorized": False,
                "replayAuthorized": False,
                "nextTask": report["decision"]["recommendedNextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
