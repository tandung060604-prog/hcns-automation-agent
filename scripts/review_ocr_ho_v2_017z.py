#!/usr/bin/env python3
"""Fail-closed intake for explicit development-only runtime patch authorization."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

AUTH_SCHEMA = "ocr-ho-v2-017z-runtime-patch-authorization-record/1.0.0"
RULE = {
    "name": "GEOMETRY_REGION_BOTTOM_EXTEND_TO_OBSERVED_LINE_BBOX",
    "field": "placeOfResidence",
    "maxBottomExtensionPixels": 15,
    "preserveMaxValueLines": 2,
    "lineIdRemapping": False,
}
PATCH_SURFACE = {
    "affectedFile": "apps/ocr_lab/api/phase11_10_cccd_v2.py",
    "guardAfter": "selected = choices[:max_lines]",
    "guardBefore": "geometry_bboxes, geometry_ids = _geometry_line_bboxes",
    "guardCondition": "field_name == placeOfResidence and not selected",
    "detectorSelectedLinesUntouched": True,
}
REQUIRED_FIELDS = (
    "schemaVersion",
    "taskId",
    "datasetFamily",
    "datasetId",
    "candidateVersion",
    "sourceArtifactSha256",
    "rule",
    "patchSurface",
    "approval.approved",
    "approval.approverRole",
    "approval.approvedAt",
    "approval.localOnly",
    "approval.runtimePatchAuthorized",
    "approval.primaryRuntimeChangeAuthorized",
    "approval.selectorChangeAuthorized",
    "approval.replayAuthorized",
    "approval.productionPromotionAllowed",
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_source(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-017y-guard-placement-resolution/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-017Y"
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
        or source.get("resolution", {}).get("guardPlacementGate") != "PASS"
        or source.get("resolution", {}).get("implementationApplied") is not False
    ):
        raise SystemExit("017Y source scope/resolution mismatch")


def validate_record(record: dict[str, Any] | None, source_digest: str) -> dict[str, Any]:
    if record is None:
        return {
            "provided": False,
            "status": "MISSING",
            "requiredSchema": AUTH_SCHEMA,
            "requiredFields": list(REQUIRED_FIELDS),
            "sourceArtifactMatch": False,
            "approverRolePresent": False,
            "approvedAtPresent": False,
            "runtimePatchAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "selectorChangeAuthorized": False,
            "replayAuthorized": False,
            "productionPromotionAllowed": False,
        }
    approval = record.get("approval", {})
    source_match = (
        str(record.get("sourceArtifactSha256") or "").casefold()
        == source_digest.casefold()
    )
    valid = (
        record.get("schemaVersion") == AUTH_SCHEMA
        and record.get("taskId") == "OCR-HO-V2-017Z"
        and record.get("datasetFamily") == "CCCD"
        and record.get("datasetId") == "DATA-HO-014"
        and record.get("candidateVersion") == "11.10.2"
        and record.get("containsRawPII") is False
        and source_match
        and record.get("rule") == RULE
        and record.get("patchSurface") == PATCH_SURFACE
        and approval.get("approved") is True
        and bool(str(approval.get("approverRole") or "").strip())
        and _iso_timestamp(approval.get("approvedAt"))
        and approval.get("localOnly") is True
        and approval.get("runtimePatchAuthorized") is True
        and approval.get("primaryRuntimeChangeAuthorized") is False
        and approval.get("selectorChangeAuthorized") is False
        and approval.get("replayAuthorized") is False
        and approval.get("productionPromotionAllowed") is False
    )
    return {
        "provided": True,
        "status": "VALID_FOR_DEVELOPMENT_PATCH" if valid else "INVALID",
        "requiredSchema": AUTH_SCHEMA,
        "requiredFields": list(REQUIRED_FIELDS),
        "sourceArtifactMatch": source_match,
        "approverRolePresent": bool(str(approval.get("approverRole") or "").strip()),
        "approvedAtPresent": _iso_timestamp(approval.get("approvedAt")),
        "runtimePatchAuthorized": valid,
        "primaryRuntimeChangeAuthorized": False,
        "selectorChangeAuthorized": False,
        "replayAuthorized": False,
        "productionPromotionAllowed": False,
    }


def build_report(
    source: dict[str, Any],
    source_digest: str,
    record: dict[str, Any] | None,
    record_digest: str | None,
) -> dict[str, Any]:
    intake = validate_record(record, source_digest)
    accepted = intake["status"] == "VALID_FOR_DEVELOPMENT_PATCH"
    return {
        "schemaVersion": "ocr-ho-v2-017z-runtime-patch-authorization-intake/1.0.0",
        "taskId": "OCR-HO-V2-017Z",
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
            "diagnostic": "EXPLICIT_RUNTIME_PATCH_AUTHORIZATION_INTAKE_ONLY",
        },
        "sourceDigests": {
            "artifact017ySha256": source_digest,
            "authorizationRecordSha256": record_digest,
        },
        "candidateRule": RULE,
        "patchSurface": PATCH_SURFACE,
        "authorizationIntake": intake,
        "decision": {
            "status": (
                "RUNTIME_PATCH_AUTHORIZATION_ACCEPTED"
                if accepted
                else "RUNTIME_PATCH_AUTHORIZATION_REQUIRED"
                if not intake["provided"]
                else "RUNTIME_PATCH_AUTHORIZATION_INVALID"
            ),
            "recommendedNextTask": "OCR-HO-V2-018A" if accepted else "OCR-HO-V2-017Z",
            "recommendedNextDiagnostic": (
                "MINIMAL_SHADOW_PATCH_REVIEW"
                if accepted
                else "EXPLICIT_RUNTIME_PATCH_AUTHORIZATION_INTAKE"
            ),
            "reason": (
                "Record authorizes only the resolved development shadow patch; primary runtime, "
                "selector, replay and promotion remain closed."
                if accepted
                else (
                    "Supply a private record matching the 017Y digest, rule and "
                    "development-only scope."
                )
            ),
            "runtimeChanged": False,
            "patchApplied": False,
            "patchAuthorized": accepted,
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
    parser.add_argument("--artifact-017y", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.artifact_017y)
    validate_source(source)
    source_digest = sha256(args.artifact_017y)
    record = load(args.authorization_record) if args.authorization_record else None
    record_digest = sha256(args.authorization_record) if args.authorization_record else None
    report = build_report(source, source_digest, record, record_digest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "authorizationStatus": report["authorizationIntake"]["status"],
                "runtimePatchAuthorized": report["authorizationIntake"][
                    "runtimePatchAuthorized"
                ],
                "patchApplied": False,
                "replayAuthorized": False,
                "nextTask": report["decision"]["recommendedNextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
