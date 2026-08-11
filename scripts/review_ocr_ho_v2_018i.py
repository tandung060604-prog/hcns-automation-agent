#!/usr/bin/env python3
"""Fail-closed OCR-HO-V2-018I selector safety-authorization intake."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from scripts.review_ocr_ho_v2_018g import load
except ModuleNotFoundError:
    from review_ocr_ho_v2_018g import load

AUTH_SCHEMA = "ocr-ho-v2-018i-selector-safety-authorization-record/1.0.0"
SAFETY_SCOPE = {
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
    "datasetFamily",
    "datasetId",
    "candidateVersion",
    "baselineVersion",
    "sourceArtifactSha256",
    "safetyScope",
    "approval.approved",
    "approval.approverRole",
    "approval.approvedAt",
    "approval.localOnly",
    "approval.selectorSafetyEvidenceAuthorized",
    "approval.counterfactualAuthorized",
    "approval.selectorChangeAuthorized",
    "approval.developmentReplayAuthorized",
    "approval.heldoutEvaluationAuthorized",
    "approval.evaluateOnceAuthorized",
    "approval.primaryRuntimeChangeAuthorized",
    "approval.productionPromotionAllowed",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(source: dict[str, Any]) -> None:
    expected = {
        "schemaVersion": "ocr-ho-v2-018h-selector-safety-evidence-review/1.0.0",
        "taskId": "OCR-HO-V2-018H",
        **SAFETY_SCOPE,
    }
    if any(
        source.get(key) != value
        for key, value in expected.items()
        if key != "protocol"
    ):
        raise SystemExit("018H source scope/schema mismatch")
    if (
        source.get("protocol", {}).get("gate") != "AUTO_DETECTOR"
        or source.get("protocol", {}).get("diagnostic")
        != "AGGREGATE_SELECTOR_SAFETY_EVIDENCE_REVIEW_ONLY"
        or source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("readiness", {}).get("counterfactualOpeningAllowed") is not False
        or source.get("readiness", {}).get("counterfactualAuthorized") is not False
        or source.get("decision", {}).get("status") != "SELECTOR_SAFETY_EVIDENCE_HOLD"
    ):
        raise SystemExit("018H must remain sealed and counterfactual-closed")


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
            "selectorSafetyEvidenceAuthorized": False,
            "counterfactualAuthorized": False,
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
    scope_match = record.get("safetyScope") == SAFETY_SCOPE
    valid = (
        record.get("schemaVersion") == AUTH_SCHEMA
        and record.get("taskId") == "OCR-HO-V2-018I"
        and record.get("datasetFamily") == SAFETY_SCOPE["datasetFamily"]
        and record.get("datasetId") == SAFETY_SCOPE["datasetId"]
        and record.get("candidateVersion") == SAFETY_SCOPE["candidateVersion"]
        and record.get("baselineVersion") == SAFETY_SCOPE["baselineVersion"]
        and record.get("containsRawPII") is False
        and source_match
        and scope_match
        and approval.get("approved") is True
        and bool(str(approval.get("approverRole") or "").strip())
        and _iso_timestamp(approval.get("approvedAt"))
        and approval.get("localOnly") is True
        and approval.get("selectorSafetyEvidenceAuthorized") is True
        and approval.get("counterfactualAuthorized") is False
        and approval.get("selectorChangeAuthorized") is False
        and approval.get("developmentReplayAuthorized") is False
        and approval.get("heldoutEvaluationAuthorized") is False
        and approval.get("evaluateOnceAuthorized") is False
        and approval.get("primaryRuntimeChangeAuthorized") is False
        and approval.get("productionPromotionAllowed") is False
    )
    return {
        "provided": True,
        "status": "VALID_FOR_SAFETY_REVIEW" if valid else "INVALID",
        "requiredSchema": AUTH_SCHEMA,
        "requiredFields": list(REQUIRED_FIELDS),
        "sourceArtifactMatch": source_match,
        "scopeMatch": scope_match,
        "approverRolePresent": bool(str(approval.get("approverRole") or "").strip()),
        "approvedAtPresent": _iso_timestamp(approval.get("approvedAt")),
        "selectorSafetyEvidenceAuthorized": valid,
        "counterfactualAuthorized": False,
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
    accepted = intake["status"] == "VALID_FOR_SAFETY_REVIEW"
    return {
        "schemaVersion": "ocr-ho-v2-018i-selector-safety-authorization-intake/1.0.0",
        "taskId": "OCR-HO-V2-018I",
        **SAFETY_SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "EXPLICIT_SELECTOR_SAFETY_AUTHORIZATION_INTAKE_ONLY",
        },
        "sourceDigests": {
            "artifact018hSha256": source_digest,
            "authorizationRecordSha256": record_digest,
        },
        "safetyScope": SAFETY_SCOPE,
        "authorizationIntake": intake,
        "decision": {
            "status": (
                "SELECTOR_SAFETY_AUTHORIZATION_ACCEPTED"
                if accepted
                else "SELECTOR_SAFETY_AUTHORIZATION_REQUIRED"
                if not intake["provided"]
                else "SELECTOR_SAFETY_AUTHORIZATION_INVALID"
            ),
            "nextTask": "OCR-HO-V2-018J" if accepted else "OCR-HO-V2-018I",
            "reason": (
                "The private record authorizes only safety-evidence review; it does not authorize "
                "a selector change, counterfactual, replay, held-out evaluation or promotion."
                if accepted
                else (
                    "Supply a private record matching the 018H digest, scope and safety-only "
                    "restrictions; do not infer authorization from diagnostic evidence."
                )
            ),
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
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
    parser.add_argument("--artifact-018h", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.artifact_018h)
    validate_source(source)
    source_digest = sha256(args.artifact_018h)
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
                "selectorSafetyEvidenceAuthorized": report["authorizationIntake"][
                    "selectorSafetyEvidenceAuthorized"
                ],
                "counterfactualAuthorized": False,
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
