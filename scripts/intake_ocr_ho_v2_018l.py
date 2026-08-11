#!/usr/bin/env python3
"""Fail-closed OCR-HO-V2-018L selector-counterfactual authorization intake."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

AUTH_SCHEMA = "ocr-ho-v2-018l-selector-counterfactual-authorization-record/1.0.0"
SCOPE = {
    "datasetFamily": "CCCD",
    "datasetId": "DATA-HO-014",
    "datasetRole": "DEVELOPMENT_REGRESSION",
    "documentCount": 15,
    "evaluatedFieldCount": 120,
    "diagnosticFieldCount": 45,
    "candidateVersion": "11.10.2",
    "baselineVersion": "11.9.1",
    "protocol": "AUTO_DETECTOR",
}
REQUIRED_FIELDS = (
    "schemaVersion",
    "taskId",
    "containsRawPII",
    "sourceArtifactSha256",
    "counterfactualScope",
    "approval.approved",
    "approval.approverRole",
    "approval.approvedAt",
    "approval.localOnly",
    "approval.selectorCounterfactualAuthorized",
    "approval.selectorChangeAuthorized",
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
        != "ocr-ho-v2-018k-selector-safety-decision-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018K"
    ):
        raise SystemExit("018K source schema mismatch")
    for key, expected in SCOPE.items():
        if key == "protocol":
            continue
        if source.get(key) != expected:
            raise SystemExit(f"018K source scope mismatch: {key}")
    if source.get("containsRawPII") is not False:
        raise SystemExit("018K must remain aggregate-only")
    if source.get("predictionOpened") is not False:
        raise SystemExit("018K prediction must remain sealed")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit("018K used Ground Truth at selection")
    if source.get("protocol", {}).get("gate") != "AUTO_DETECTOR":
        raise SystemExit("018K gate protocol mismatch")
    if source.get("protocol", {}).get("diagnostic") != (
        "AGGREGATE_SELECTOR_SAFETY_DECISION_REVIEW_ONLY"
    ):
        raise SystemExit("018K diagnostic protocol mismatch")
    decision = source.get("decision", {})
    if (
        decision.get("status") != "SELECTOR_COUNTERFACTUAL_NOT_RECOMMENDED_HOLD"
        or decision.get("counterfactualRecommended") is not False
        or decision.get("counterfactualOpeningAllowed") is not False
        or decision.get("counterfactualAuthorized") is not False
    ):
        raise SystemExit("018K must keep counterfactual closed")


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
            "selectorCounterfactualAuthorized": False,
            "selectorChangeAuthorized": False,
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
    scope_match = record.get("counterfactualScope") == SCOPE
    valid = (
        record.get("schemaVersion") == AUTH_SCHEMA
        and record.get("taskId") == "OCR-HO-V2-018L"
        and record.get("containsRawPII") is False
        and source_match
        and scope_match
        and approval.get("approved") is True
        and bool(str(approval.get("approverRole") or "").strip())
        and _iso_timestamp(approval.get("approvedAt"))
        and approval.get("localOnly") is True
        and approval.get("selectorCounterfactualAuthorized") is True
        and approval.get("selectorChangeAuthorized") is False
        and approval.get("developmentReplayAuthorized") is False
        and approval.get("heldoutEvaluationAuthorized") is False
        and approval.get("evaluateOnceAuthorized") is False
        and approval.get("primaryRuntimeChangeAuthorized") is False
        and approval.get("productionPromotionAllowed") is False
    )
    return {
        "provided": True,
        "status": "VALID_FOR_COUNTERFACTUAL_REVIEW" if valid else "INVALID",
        "requiredSchema": AUTH_SCHEMA,
        "requiredFields": list(REQUIRED_FIELDS),
        "sourceArtifactMatch": source_match,
        "scopeMatch": scope_match,
        "approverRolePresent": bool(str(approval.get("approverRole") or "").strip()),
        "approvedAtPresent": _iso_timestamp(approval.get("approvedAt")),
        "selectorCounterfactualAuthorized": valid,
        "selectorChangeAuthorized": False,
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
    accepted = intake["status"] == "VALID_FOR_COUNTERFACTUAL_REVIEW"
    return {
        "schemaVersion": "ocr-ho-v2-018l-selector-counterfactual-authorization-intake/1.0.0",
        "taskId": "OCR-HO-V2-018L",
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
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "EXPLICIT_SELECTOR_COUNTERFACTUAL_AUTHORIZATION_INTAKE_ONLY",
        },
        "sourceDigests": {
            "artifact018kSha256": source_digest,
            "authorizationRecordSha256": record_digest,
        },
        "authorizationIntake": intake,
        "decision": {
            "status": (
                "COUNTERFACTUAL_AUTHORIZATION_ACCEPTED_FOR_REVIEW"
                if accepted
                else "COUNTERFACTUAL_AUTHORIZATION_REQUIRED"
                if not intake["provided"]
                else "COUNTERFACTUAL_AUTHORIZATION_INVALID"
            ),
            "counterfactualAuthorized": accepted,
            "counterfactualExecutionAllowed": False,
            "counterfactualExecuted": False,
            "selectorChanged": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "nextTask": "OCR-HO-V2-018M" if accepted else "OCR-HO-V2-018L",
            "reason": (
                "The private record authorizes a future diagnostic counterfactual review "
                "only; it does not authorize selector change, replay, held-out evaluation, "
                "evaluate-once, runtime change or promotion."
                if accepted
                else "Provide a private record matching the sealed 018K digest, exact CCCD "
                "scope and safety restrictions before any counterfactual is considered."
            ),
        },
        "gates": {
            "counterfactualAuthorized": accepted,
            "counterfactualExecutionAllowed": False,
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
    parser.add_argument("--artifact-018k", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.artifact_018k)
    validate_source(source)
    record = load(args.authorization_record) if args.authorization_record else None
    report = build_report(
        source,
        sha256(args.artifact_018k),
        record,
        sha256(args.authorization_record) if args.authorization_record else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "authorizationStatus": report["authorizationIntake"]["status"],
                "counterfactualAuthorized": report["decision"]["counterfactualAuthorized"],
                "counterfactualExecuted": False,
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
