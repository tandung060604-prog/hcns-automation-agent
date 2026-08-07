#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017U explicit patch authorization review."""

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


def validate_017t(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion") != "ocr-ho-v2-017t-patch-gate-reconciliation/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-017T"
        or source.get("candidateVersion") != "11.10.2"
        or source.get("baselineVersion") != "11.9.1"
        or source.get("datasetFamily") != "CCCD"
        or source.get("datasetId") != "DATA-HO-014"
        or source.get("datasetRole") != "DEVELOPMENT_REGRESSION"
        or source.get("documentCount") != 15
        or source.get("evaluatedFieldCount") != 120
        or source.get("diagnosticFieldCount") != 45
    ):
        raise SystemExit("017T source scope/schema mismatch")
    if source.get("containsRawPII") is not False:
        raise SystemExit("017T must be aggregate-only")
    if source.get("predictionOpened") is not False:
        raise SystemExit("017T prediction must remain sealed")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit("017T must not use GroundTruth at selection")
    if source.get("protocol", {}).get("diagnostic") != (
        "RESIDENCE_GEOMETRY_PATCH_GATE_RECONCILIATION_ONLY"
    ):
        raise SystemExit("017T diagnostic protocol mismatch")


def review_authorization(source: dict[str, Any]) -> dict[str, Any]:
    gate = source.get("gateReview", {})
    reconciled = gate.get("reconciliationGate") == "PASS"
    return {
        "reconciliationGate": "PASS" if reconciled else "HOLD",
        "qualityImprovementProven": source.get("gateReview", {}).get(
            "qualityImprovementProven", False
        ),
        "explicitPatchApprovalRequired": True,
        "authorizationRecordProvided": False,
        "authorizationStatus": "MISSING",
        "authorizationScope": "MINIMAL_RESIDENCE_BOTTOM_BOUNDARY_ONLY",
        "patchReviewAuthorized": False,
        "patchAuthorized": False,
        "replayAuthorized": False,
        "selectorChangeAuthorized": False,
        "primaryRuntimeChangeAuthorized": False,
        "productionPromotionAllowed": False,
    }


def build_report(source: dict[str, Any], source_digest: str) -> dict[str, Any]:
    authorization = review_authorization(source)
    reconciled = authorization["reconciliationGate"] == "PASS"
    return {
        "schemaVersion": "ocr-ho-v2-017u-explicit-patch-authorization-review/1.0.0",
        "taskId": "OCR-HO-V2-017U",
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
            "diagnostic": "EXPLICIT_PATCH_AUTHORIZATION_REVIEW_ONLY",
        },
        "sourceDigests": {"artifact017tSha256": source_digest},
        "candidateRule": {
            "name": source["candidateRule"]["name"],
            "field": source["candidateRule"]["field"],
            "maxBottomExtensionPixels": source["candidateRule"]["maxBottomExtensionPixels"],
            "preserveMaxValueLines": source["candidateRule"]["preserveMaxValueLines"],
            "lineIdRemapping": source["candidateRule"]["lineIdRemapping"],
        },
        "authorizationReview": authorization,
        "decision": {
            "status": (
                "PATCH_AUTHORIZATION_REQUIRED"
                if reconciled
                else "PATCH_AUTHORIZATION_BLOCKED_BY_RECONCILIATION"
            ),
            "recommendedNextTask": "OCR-HO-V2-017V" if reconciled else "OCR-HO-V2-017U",
            "recommendedNextDiagnostic": "EXPLICIT_PATCH_AUTHORIZATION_INTAKE",
            "reason": (
                "017T reconciles the bounded rule and independent line-ID evidence, but no "
                "independent approval record authorizes a patch. Keep runtime, replay and "
                "promotion closed until explicit approval is supplied."
                if reconciled
                else "The 017T reconciliation gate is not PASS; authorization cannot be considered."
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
    parser.add_argument("--artifact-017t", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.artifact_017t)
    validate_017t(source)
    report = build_report(source, sha256(args.artifact_017t))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "authorizationStatus": report["authorizationReview"]["authorizationStatus"],
                "patchAuthorized": False,
                "replayAuthorized": False,
                "nextTask": report["decision"]["recommendedNextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
