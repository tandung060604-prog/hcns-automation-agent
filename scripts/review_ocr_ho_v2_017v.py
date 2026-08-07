#!/usr/bin/env python3
"""Local-only OCR-HO-V2-017V authorization-record intake."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

AUTH_SCHEMA = "ocr-ho-v2-017v-authorization-record/1.0.0"
RULE = {
    "name": "GEOMETRY_REGION_BOTTOM_EXTEND_TO_OBSERVED_LINE_BBOX",
    "field": "placeOfResidence",
    "maxBottomExtensionPixels": 15,
    "preserveMaxValueLines": 2,
    "lineIdRemapping": False,
}
REQUIRED_FIELDS = (
    "schemaVersion",
    "taskId",
    "datasetFamily",
    "datasetId",
    "candidateVersion",
    "sourceArtifactSha256",
    "rule",
    "approval.approved",
    "approval.approverRole",
    "approval.approvedAt",
    "approval.localOnly",
    "approval.productionPromotionAllowed",
    "approval.replayAuthorized",
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_017u(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion") != "ocr-ho-v2-017u-explicit-patch-authorization-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-017U"
        or source.get("candidateVersion") != "11.10.2"
        or source.get("baselineVersion") != "11.9.1"
        or source.get("datasetFamily") != "CCCD"
        or source.get("datasetId") != "DATA-HO-014"
        or source.get("datasetRole") != "DEVELOPMENT_REGRESSION"
        or source.get("documentCount") != 15
        or source.get("evaluatedFieldCount") != 120
        or source.get("diagnosticFieldCount") != 45
    ):
        raise SystemExit("017U source scope/schema mismatch")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
    ):
        raise SystemExit("017U must remain sealed and aggregate-only")
    if source.get("protocol", {}).get("diagnostic") != (
        "EXPLICIT_PATCH_AUTHORIZATION_REVIEW_ONLY"
    ):
        raise SystemExit("017U diagnostic protocol mismatch")


def _iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


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
            "patchReviewAuthorized": False,
            "patchAuthorized": False,
            "replayAuthorized": False,
            "productionPromotionAllowed": False,
        }
    approval = record.get("approval", {})
    source_artifact = str(record.get("sourceArtifactSha256") or "")
    source_match = source_artifact.casefold() == source_digest.casefold()
    valid = (
        record.get("schemaVersion") == AUTH_SCHEMA
        and record.get("taskId") == "OCR-HO-V2-017V"
        and record.get("datasetFamily") == "CCCD"
        and record.get("datasetId") == "DATA-HO-014"
        and record.get("candidateVersion") == "11.10.2"
        and record.get("containsRawPII") is False
        and source_match
        and record.get("rule") == RULE
        and approval.get("approved") is True
        and isinstance(approval.get("approverRole"), str)
        and bool(approval["approverRole"].strip())
        and _iso_timestamp(approval.get("approvedAt"))
        and approval.get("localOnly") is True
        and approval.get("productionPromotionAllowed") is False
        and approval.get("replayAuthorized") is False
    )
    return {
        "provided": True,
        "status": "VALID_FOR_PATCH_REVIEW" if valid else "INVALID",
        "requiredSchema": AUTH_SCHEMA,
        "requiredFields": list(REQUIRED_FIELDS),
        "sourceArtifactMatch": source_match,
        "approverRolePresent": bool(str(approval.get("approverRole") or "").strip()),
        "approvedAtPresent": _iso_timestamp(approval.get("approvedAt")),
        "patchReviewAuthorized": valid,
        "patchAuthorized": False,
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
    accepted = intake["status"] == "VALID_FOR_PATCH_REVIEW"
    return {
        "schemaVersion": "ocr-ho-v2-017v-authorization-intake/1.0.0",
        "taskId": "OCR-HO-V2-017V",
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
            "diagnostic": "EXPLICIT_PATCH_AUTHORIZATION_INTAKE_ONLY",
        },
        "sourceDigests": {
            "artifact017uSha256": source_digest,
            "authorizationRecordSha256": record_digest,
        },
        "candidateRule": RULE,
        "authorizationIntake": intake,
        "decision": {
            "status": (
                "AUTHORIZATION_RECORD_ACCEPTED_FOR_PATCH_REVIEW"
                if accepted
                else (
                    "AUTHORIZATION_RECORD_INVALID"
                    if intake["provided"]
                    else "AUTHORIZATION_RECORD_REQUIRED"
                )
            ),
            "recommendedNextTask": "OCR-HO-V2-017W" if accepted else "OCR-HO-V2-017V",
            "recommendedNextDiagnostic": (
                "MINIMAL_PATCH_IMPLEMENTATION_REVIEW"
                if accepted
                else "EXPLICIT_PATCH_AUTHORIZATION_INTAKE"
            ),
            "reason": (
                "The private record matches the sealed 017U artifact and authorizes only "
                "a separate patch review; no runtime patch or replay is authorized here."
                if accepted
                else "Supply a private record matching the required schema, source digest and "
                "minimal residence rule; do not infer approval from diagnostic evidence."
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
    parser.add_argument("--artifact-017u", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.artifact_017u)
    validate_017u(source)
    source_digest = sha256(args.artifact_017u)
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
                "patchReviewAuthorized": report["authorizationIntake"]["patchReviewAuthorized"],
                "patchAuthorized": False,
                "replayAuthorized": False,
                "nextTask": report["decision"]["recommendedNextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
