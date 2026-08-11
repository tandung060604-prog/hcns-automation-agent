#!/usr/bin/env python3
"""Fail-closed authorization intake for OCR-HO-V2-018V aggregate review."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

SCOPE = {
    "candidateVersion": "11.10.2",
    "baselineVersion": "11.9.1",
    "datasetFamily": "CCCD",
    "datasetId": "DATA-HO-014",
    "datasetRole": "DEVELOPMENT_REGRESSION",
    "documentCount": 15,
    "evaluatedFieldCount": 120,
    "diagnosticFieldCount": 45,
}
REVIEW_SCOPE = {
    "protocol": "AUTO_DETECTOR",
    "review": "AGGREGATE_PROFILE_VARIANT_BY_ERROR_CLASS_ONLY",
    "targetField": "placeOfResidence",
    "selectedErrorClass": "RECOGNIZER_DISAGREEMENT",
    "profileVariantSelectorChange": False,
}
AUTH_SCHEMA = "ocr-ho-v2-018v-profile-variant-error-class-authorization-record/1.0.0"
REQUIRED_FIELDS = (
    "schemaVersion",
    "taskId",
    "datasetFamily",
    "datasetId",
    "candidateVersion",
    "baselineVersion",
    "sourceArtifactSha256",
    "reviewScope",
    "approval.approved",
    "approval.approverRole",
    "approval.approvedAt",
    "approval.localOnly",
    "approval.aggregateProfileVariantErrorClassReviewAuthorized",
    "approval.selectorChangeAuthorized",
    "approval.counterfactualAuthorized",
    "approval.developmentReplayAuthorized",
    "approval.heldoutEvaluationAuthorized",
    "approval.evaluateOnceAuthorized",
    "approval.primaryRuntimeChangeAuthorized",
    "approval.productionPromotionAllowed",
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018u-residence-error-class-attribution/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018U"
    ):
        raise SystemExit("018U source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018U source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018U must remain sealed and attribution-only")
    protocol = source.get("protocol", {})
    if (
        protocol.get("gate") != "AUTO_DETECTOR"
        or protocol.get("diagnostic")
        != "AGGREGATE_RESIDENCE_ERROR_CLASS_ATTRIBUTION_ONLY"
    ):
        raise SystemExit("018U protocol mismatch")
    evidence = source.get("evidence", {})
    if (
        evidence.get("attributionBoundary", {}).get(
            "profileVariantErrorClassCrossTabAvailable"
        )
        is not False
        or source.get("decision", {}).get("selectedDiagnostic")
        != "RESIDENCE_RECOGNIZER_ERROR_CLASS_ATTRIBUTION"
    ):
        raise SystemExit("018U attribution boundary mismatch")
    decision = source.get("decision", {})
    if any(
        decision.get(key) is not False
        for key in (
            "profileSelectorAuthorized",
            "variantSelectorAuthorized",
            "counterfactualAuthorized",
            "selectorPathOpen",
            "runtimeChanged",
            "replayExecuted",
            "heldoutOpened",
            "promotionAllowed",
        )
    ):
        raise SystemExit("018U authorization boundary mismatch")
    gates = source.get("gates", {})
    if (
        gates.get("developmentRegressionGate") != "HOLD"
        or gates.get("heldoutReadinessGate") != "HOLD"
        or gates.get("schemaErrors") != 0
        or gates.get("sensitiveFalseAcceptance") != 0
        or gates.get("acceptedCoverage") != 0
        or gates.get("manualReviewOnly") is not True
        or gates.get("productionPromotionAllowed") is not False
    ):
        raise SystemExit("018U gate mismatch")


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
            "scopeMatch": False,
            "approverRolePresent": False,
            "approvedAtPresent": False,
            "aggregateProfileVariantErrorClassReviewAuthorized": False,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        }
    approval = record.get("approval", {})
    source_match = (
        str(record.get("sourceArtifactSha256") or "").casefold()
        == source_digest.casefold()
    )
    scope_match = record.get("reviewScope") == REVIEW_SCOPE
    valid = (
        record.get("schemaVersion") == AUTH_SCHEMA
        and record.get("taskId") == "OCR-HO-V2-018V"
        and record.get("datasetFamily") == SCOPE["datasetFamily"]
        and record.get("datasetId") == SCOPE["datasetId"]
        and record.get("candidateVersion") == SCOPE["candidateVersion"]
        and record.get("baselineVersion") == SCOPE["baselineVersion"]
        and record.get("containsRawPII") is False
        and source_match
        and scope_match
        and approval.get("approved") is True
        and bool(str(approval.get("approverRole") or "").strip())
        and _iso_timestamp(approval.get("approvedAt"))
        and approval.get("localOnly") is True
        and approval.get("aggregateProfileVariantErrorClassReviewAuthorized") is True
        and approval.get("selectorChangeAuthorized") is False
        and approval.get("counterfactualAuthorized") is False
        and approval.get("developmentReplayAuthorized") is False
        and approval.get("heldoutEvaluationAuthorized") is False
        and approval.get("evaluateOnceAuthorized") is False
        and approval.get("primaryRuntimeChangeAuthorized") is False
        and approval.get("productionPromotionAllowed") is False
    )
    return {
        "provided": True,
        "status": "VALID_FOR_PROFILE_VARIANT_ERROR_CLASS_REVIEW" if valid else "INVALID",
        "requiredSchema": AUTH_SCHEMA,
        "requiredFields": list(REQUIRED_FIELDS),
        "sourceArtifactMatch": source_match,
        "scopeMatch": scope_match,
        "approverRolePresent": bool(str(approval.get("approverRole") or "").strip()),
        "approvedAtPresent": _iso_timestamp(approval.get("approvedAt")),
        "aggregateProfileVariantErrorClassReviewAuthorized": valid,
        "selectorChangeAuthorized": False,
        "counterfactualAuthorized": False,
        "developmentReplayAuthorized": False,
        "heldoutEvaluationAuthorized": False,
        "evaluateOnceAuthorized": False,
        "primaryRuntimeChangeAuthorized": False,
        "productionPromotionAllowed": False,
    }


def build_report(
    source: dict[str, Any],
    source_digest: str,
    record: dict[str, Any] | None,
    record_digest: str | None,
) -> dict[str, Any]:
    intake = validate_record(record, source_digest)
    accepted = intake["status"] == "VALID_FOR_PROFILE_VARIANT_ERROR_CLASS_REVIEW"
    return {
        "schemaVersion": "ocr-ho-v2-018v-profile-variant-error-class-authorization-intake/1.0.0",
        "taskId": "OCR-HO-V2-018V",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "EXPLICIT_PROFILE_VARIANT_ERROR_CLASS_AUTHORIZATION_INTAKE_ONLY",
        },
        "sourceDigests": {
            "artifact018uSha256": source_digest,
            "authorizationRecordSha256": record_digest,
        },
        "reviewScope": REVIEW_SCOPE,
        "authorizationIntake": intake,
        "decision": {
            "status": (
                "PROFILE_VARIANT_ERROR_CLASS_AUTHORIZATION_ACCEPTED"
                if accepted
                else "PROFILE_VARIANT_ERROR_CLASS_AUTHORIZATION_REQUIRED"
                if not intake["provided"]
                else "PROFILE_VARIANT_ERROR_CLASS_AUTHORIZATION_INVALID"
            ),
            "nextTask": "OCR-HO-V2-018W" if accepted else "OCR-HO-V2-018V",
            "evidenceReviewExecuted": False,
            "selectorChanged": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "The private record authorizes only aggregate profile/variant-by-error-class "
                "evidence review; it does not authorize selector changes, counterfactuals, "
                "replay, runtime changes, held-out evaluation or promotion."
                if accepted
                else (
                    "Supply a private record matching the 018U digest, scope and "
                    "aggregate-only restrictions; do not infer authorization from diagnostics."
                )
            ),
        },
        "gates": {
            "profileVariantErrorClassReviewAuthorized": accepted,
            "evidenceReviewExecuted": False,
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
    parser.add_argument("--artifact-018u", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.artifact_018u)
    validate_source(source)
    source_digest = sha256(args.artifact_018u)
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
                "profileVariantErrorClassReviewAuthorized": report[
                    "authorizationIntake"
                ]["aggregateProfileVariantErrorClassReviewAuthorized"],
                "evidenceReviewExecuted": False,
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
