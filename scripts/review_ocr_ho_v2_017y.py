#!/usr/bin/env python3
"""Aggregate/code-only resolution of the residence geometry guard placement."""

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
        source.get("schemaVersion") != "ocr-ho-v2-017x-minimal-implementation-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-017X"
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
        or source.get("implementationReview", {}).get("guardPlacementGate") != "HOLD"
        or source.get("implementationReview", {}).get("patchAuthorized") is not False
        or source.get("implementationReview", {}).get("replayAuthorized") is not False
    ):
        raise SystemExit("017X source scope/guard state mismatch")


def _line_number(lines: list[str], marker: str) -> int:
    for index, line in enumerate(lines, start=1):
        if marker in line:
            return index
    return 0


def resolve_guard(source_text: str) -> dict[str, Any]:
    lines = source_text.splitlines()
    selected_line = _line_number(lines, "selected = choices[:max_lines]")
    geometry_call_line = _line_number(
        lines, "geometry_bboxes, geometry_ids = _geometry_line_bboxes"
    )
    geometry_source_line = _line_number(
        lines, 'region["regionSource"] = "phase11_10_geometry_line_segmentation"'
    )
    ordered = (
        selected_line > 0
        and geometry_call_line > selected_line
        and geometry_source_line > geometry_call_line
    )
    return {
        "affectedFile": "apps/ocr_lab/api/phase11_10_cccd_v2.py",
        "insertionFunction": "locate_field_regions",
        "insertionAfter": "selected = choices[:max_lines]",
        "insertionBefore": "geometry_bboxes, geometry_ids = _geometry_line_bboxes",
        "selectedAnchorLine": selected_line,
        "geometryCallLine": geometry_call_line,
        "currentGeometrySourceAssignmentLine": geometry_source_line,
        "guardCondition": "field_name == placeOfResidence and not selected",
        "geometrySourceValue": "phase11_10_geometry_line_segmentation",
        "consumerFunction": "_geometry_line_bboxes",
        "detectorSelectedLinesUntouched": True,
        "lineIdRemapping": False,
        "maxValueLines": 2,
        "placementResolved": ordered,
    }


def review(source_017x: dict[str, Any], runtime_text: str) -> dict[str, Any]:
    placement = resolve_guard(runtime_text)
    rule_ok = source_017x.get("candidateRule") == RULE
    resolved = rule_ok and placement["placementResolved"]
    return {
        "schemaVersion": "ocr-ho-v2-017y-guard-placement-resolution/1.0.0",
        "taskId": "OCR-HO-V2-017Y",
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
            "diagnostic": "GUARD_PLACEMENT_RESOLUTION_ONLY",
        },
        "candidateRule": RULE,
        "guardPlacement": placement,
        "resolution": {
            "ruleScopeGate": "PASS" if rule_ok else "HOLD",
            "guardPlacementGate": "PASS" if resolved else "HOLD",
            "detectorIsolationGate": (
                "PASS" if placement["detectorSelectedLinesUntouched"] else "HOLD"
            ),
            "runtimeChanged": False,
            "patchAuthorized": False,
            "replayAuthorized": False,
            "counterfactualAuthorized": False,
            "implementationApplied": False,
        },
        "decision": {
            "status": (
                "GUARD_PLACEMENT_RESOLVED_REQUIRES_EXPLICIT_PATCH"
                if resolved
                else "GUARD_PLACEMENT_RESOLUTION_HOLD"
            ),
            "recommendedNextTask": "OCR-HO-V2-017Z",
            "recommendedNextDiagnostic": "EXPLICIT_RUNTIME_PATCH_AUTHORIZATION",
            "reason": (
                "The guard belongs between selected-line filtering and the geometry bbox call; "
                "only the geometry fallback receives the source marker. This task applies no code."
                if resolved
                else "The runtime anchors do not establish a safe geometry-only insertion point."
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
    parser.add_argument("--artifact-017x", type=Path, required=True)
    parser.add_argument("--runtime-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.artifact_017x)
    validate_source(source)
    report = review(source, args.runtime_file.read_text(encoding="utf-8"))
    report["sourceDigests"] = {
        "artifact017xSha256": sha256(args.artifact_017x),
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
                "guardPlacementGate": report["resolution"]["guardPlacementGate"],
                "patchAuthorized": False,
                "replayAuthorized": False,
                "nextTask": report["decision"]["recommendedNextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
