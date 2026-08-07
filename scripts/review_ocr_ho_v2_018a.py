#!/usr/bin/env python3
"""Aggregate/code-only review of the applied 018A shadow patch."""

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
        source.get("schemaVersion")
        != "ocr-ho-v2-017z-runtime-patch-authorization-intake/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-017Z"
        or source.get("candidateVersion") != "11.10.2"
        or source.get("baselineVersion") != "11.9.1"
        or source.get("datasetFamily") != "CCCD"
        or source.get("datasetId") != "DATA-HO-014"
        or source.get("datasetRole") != "DEVELOPMENT_REGRESSION"
        or source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("authorizationIntake", {}).get("status")
        != "VALID_FOR_DEVELOPMENT_PATCH"
        or source.get("authorizationIntake", {}).get("runtimePatchAuthorized") is not True
        or source.get("authorizationIntake", {}).get("primaryRuntimeChangeAuthorized") is not False
        or source.get("authorizationIntake", {}).get("replayAuthorized") is not False
        or source.get("gates", {}).get("productionPromotionAllowed") is not False
    ):
        raise SystemExit("017Z authorization scope mismatch")


def inspect_patch(source_text: str) -> dict[str, Any]:
    markers = {
        "boundedExtension": "geometry_bottom_extension = (" in source_text,
        "residenceOnly": 'field_name == "placeOfResidence"' in source_text,
        "geometrySourceGuard": (
            'region.get("regionSource") == "phase11_10_geometry_line_segmentation"'
            in source_text
        ),
        "fallbackSourceOverride": (
            'dict(region, regionSource="phase11_10_geometry_line_segmentation")'
            in source_text
        ),
        "selectedLineGuard": "field_name == \"placeOfResidence\" and not selected" in source_text,
        "detectorPathPreserved": '"phase11_10_detector_lines"' in source_text,
        "lineCapPreserved": "groups[: (1 if field_name == \"fullName\" else 2)]" in source_text,
        "lineIdsPreserved": 'region["lineIds"] = geometry_ids' in source_text,
    }
    return {
        "affectedFile": "apps/ocr_lab/api/phase11_10_cccd_v2.py",
        "affectedFunctions": ["locate_field_regions", "_geometry_line_bboxes"],
        "markers": markers,
        "allRequiredMarkers": all(markers.values()),
        "rule": RULE,
        "primaryRuntimeChanged": False,
        "replayAuthorized": False,
        "productionPromotionAllowed": False,
    }


def review(source_017z: dict[str, Any], runtime_text: str) -> dict[str, Any]:
    patch = inspect_patch(runtime_text)
    applied = patch["allRequiredMarkers"]
    return {
        "schemaVersion": "ocr-ho-v2-018a-shadow-patch-review/1.0.0",
        "taskId": "OCR-HO-V2-018A",
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
            "diagnostic": "MINIMAL_SHADOW_PATCH_REVIEW_ONLY",
        },
        "candidateRule": RULE,
        "patchInspection": patch,
        "review": {
            "authorizationGate": "PASS",
            "patchScopeGate": "PASS" if applied else "HOLD",
            "detectorIsolationGate": (
                "PASS" if patch["markers"]["detectorPathPreserved"] else "HOLD"
            ),
            "lineCapGate": "PASS" if patch["markers"]["lineCapPreserved"] else "HOLD",
            "lineIdMappingGate": "PASS" if patch["markers"]["lineIdsPreserved"] else "HOLD",
            "shadowPatchApplied": applied,
            "primaryRuntimeChanged": False,
            "qualityImprovementProven": False,
            "replayAuthorized": False,
            "counterfactualAuthorized": False,
        },
        "decision": {
            "status": "SHADOW_PATCH_APPLIED_REVIEW_ONLY" if applied else "SHADOW_PATCH_REVIEW_HOLD",
            "recommendedNextTask": "OCR-HO-V2-018B",
            "recommendedNextDiagnostic": "DEVELOPMENT_REPLAY_AUTHORIZATION_INTAKE",
            "reason": (
                "The authorized 15px residence geometry patch is applied only to the shadow "
                "candidate; no replay, primary-runtime change or promotion is authorized."
                if applied
                else "Required patch markers are incomplete; keep the candidate closed."
            ),
            "runtimeChanged": applied,
            "patchApplied": applied,
            "patchAuthorized": True,
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
    parser.add_argument("--artifact-017z", type=Path, required=True)
    parser.add_argument("--runtime-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.artifact_017z)
    validate_source(source)
    report = review(source, args.runtime_file.read_text(encoding="utf-8"))
    report["sourceDigests"] = {
        "artifact017zSha256": sha256(args.artifact_017z),
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
                "shadowPatchApplied": report["review"]["shadowPatchApplied"],
                "replayAuthorized": False,
                "nextTask": report["decision"]["recommendedNextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
