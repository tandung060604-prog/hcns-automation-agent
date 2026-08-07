#!/usr/bin/env python3
"""Aggregate-only review of the authorized 15px residence patch surface."""

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


def validate_source(source: dict[str, Any], task_id: str, schema: str) -> None:
    if (
        source.get("schemaVersion") != schema
        or source.get("taskId") != task_id
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
    ):
        raise SystemExit(f"{task_id} source scope/schema mismatch")


def _rule_matches(rule: dict[str, Any]) -> bool:
    return (
        rule.get("name") == RULE["name"]
        and rule.get("field") == RULE["field"]
        and int(rule.get("maxBottomExtensionPixels", 0)) == 15
        and int(rule.get("preserveMaxValueLines", 0)) == 2
        and rule.get("lineIdRemapping") is False
    )


def review(source_017t: dict[str, Any], source_017v: dict[str, Any]) -> dict[str, Any]:
    rule = source_017t.get("candidateRule", {})
    reconciliation = source_017t.get("gateReview", {})
    intake = source_017v.get("authorizationIntake", {})
    bounded_rule = reconciliation.get("reconciliationGate") == "PASS" and _rule_matches(rule)
    authorization = (
        intake.get("status") == "VALID_FOR_PATCH_REVIEW"
        and intake.get("patchReviewAuthorized") is True
        and intake.get("patchAuthorized") is False
        and intake.get("replayAuthorized") is False
        and source_017v.get("gates", {}).get("productionPromotionAllowed") is False
    )
    accepted = bounded_rule and authorization
    return {
        "schemaVersion": "ocr-ho-v2-017w-minimal-patch-review/1.0.0",
        "taskId": "OCR-HO-V2-017W",
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
            "diagnostic": "MINIMAL_RESIDENCE_PATCH_REVIEW_ONLY",
        },
        "candidateRule": RULE,
        "patchSurface": {
            "affectedFile": "apps/ocr_lab/api/phase11_10_cccd_v2.py",
            "affectedFunctions": ["locate_field_regions", "_geometry_line_bboxes"],
            "field": "placeOfResidence",
            "changeType": "BOTTOM_BOUNDARY_ONLY",
            "excludedLayers": [
                "detector",
                "recognizer",
                "reading_order",
                "normalization",
                "parser",
                "selector",
            ],
            "lineIdRemapping": False,
        },
        "review": {
            "reconciliationGate": "PASS" if bounded_rule else "HOLD",
            "authorizationGate": "PASS" if authorization else "HOLD",
            "minimalSurfaceGate": "PASS" if accepted else "HOLD",
            "qualityImprovementProven": False,
            "runtimeChanged": False,
            "patchAuthorized": False,
            "replayAuthorized": False,
            "counterfactualAuthorized": False,
        },
        "decision": {
            "status": "PATCH_SURFACE_REVIEW_ACCEPTED" if accepted else "PATCH_SURFACE_REVIEW_HOLD",
            "recommendedNextTask": "OCR-HO-V2-017X" if accepted else "OCR-HO-V2-017V",
            "recommendedNextDiagnostic": (
                "MINIMAL_RESIDENCE_PATCH_IMPLEMENTATION_REVIEW"
                if accepted
                else "EXPLICIT_PATCH_AUTHORIZATION_INTAKE"
            ),
            "reason": (
                "The 15px bottom-only residence rule is bounded to the existing geometry path; "
                "this review authorizes neither runtime change nor replay."
                if accepted
                else (
                    "Reconciliation or patch-review authorization is incomplete; "
                    "keep all changes closed."
                )
            ),
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
    parser.add_argument("--artifact-017t", type=Path, required=True)
    parser.add_argument("--artifact-017v", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_017t = load(args.artifact_017t)
    source_017v = load(args.artifact_017v)
    validate_source(
        source_017t,
        "OCR-HO-V2-017T",
        "ocr-ho-v2-017t-patch-gate-reconciliation/1.0.0",
    )
    validate_source(
        source_017v,
        "OCR-HO-V2-017V",
        "ocr-ho-v2-017v-authorization-intake/1.0.0",
    )
    report = review(source_017t, source_017v)
    report["sourceDigests"] = {
        "artifact017tSha256": sha256(args.artifact_017t),
        "artifact017vSha256": sha256(args.artifact_017v),
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
                "patchAuthorized": False,
                "replayAuthorized": False,
                "nextTask": report["decision"]["recommendedNextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
