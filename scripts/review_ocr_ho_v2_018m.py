#!/usr/bin/env python3
"""Fail-closed OCR-HO-V2-018M counterfactual-execution authorization review."""

from __future__ import annotations

import argparse
import hashlib
import json
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
EXECUTION_AUTH_SCHEMA = "ocr-ho-v2-018m-counterfactual-execution-authorization-record/1.0.0"
REQUIRED_EXECUTION_FIELDS = (
    "schemaVersion",
    "taskId",
    "containsRawPII",
    "sourceArtifactSha256",
    "executionScope",
    "approval.approved",
    "approval.approverRole",
    "approval.approvedAt",
    "approval.localOnly",
    "approval.counterfactualExecutionAuthorized",
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


def _validate_scope(source: dict[str, Any], task_id: str, schema: str) -> None:
    if source.get("schemaVersion") != schema or source.get("taskId") != task_id:
        raise SystemExit(f"{task_id} source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{task_id} source scope mismatch: {key}")
    if source.get("containsRawPII") is not False:
        raise SystemExit(f"{task_id} must remain aggregate-only")
    if source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} prediction must remain sealed")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit(f"{task_id} used Ground Truth at selection")


def validate_lineage(source_018l: dict[str, Any], source_018k_digest: str) -> None:
    _validate_scope(
        source_018l,
        "OCR-HO-V2-018L",
        "ocr-ho-v2-018l-selector-counterfactual-authorization-intake/1.0.0",
    )
    if source_018l.get("protocol", {}).get("gate") != "AUTO_DETECTOR":
        raise SystemExit("018L gate protocol mismatch")
    if source_018l.get("protocol", {}).get("diagnostic") != (
        "EXPLICIT_SELECTOR_COUNTERFACTUAL_AUTHORIZATION_INTAKE_ONLY"
    ):
        raise SystemExit("018L must be authorization intake only")
    if source_018l.get("sourceDigests", {}).get("artifact018kSha256", "").casefold() != (
        source_018k_digest.casefold()
    ):
        raise SystemExit("018L does not match the supplied 018K digest")
    intake = source_018l.get("authorizationIntake", {})
    decision = source_018l.get("decision", {})
    if (
        intake.get("status") != "VALID_FOR_COUNTERFACTUAL_REVIEW"
        or intake.get("sourceArtifactMatch") is not True
        or intake.get("scopeMatch") is not True
        or intake.get("selectorCounterfactualAuthorized") is not True
        or intake.get("selectorChangeAuthorized") is not False
        or intake.get("developmentReplayAuthorized") is not False
        or intake.get("heldoutEvaluationAuthorized") is not False
        or intake.get("evaluateOnceAuthorized") is not False
        or intake.get("primaryRuntimeChangeAuthorized") is not False
        or intake.get("productionPromotionAllowed") is not False
        or decision.get("counterfactualAuthorized") is not True
        or decision.get("counterfactualExecutionAllowed") is not False
        or decision.get("counterfactualExecuted") is not False
    ):
        raise SystemExit("018L authorization lineage is not execution-closed")


def review(
    source_018l: dict[str, Any], source_018l_digest: str, source_018k_digest: str
) -> dict[str, Any]:
    return {
        "schemaVersion": "ocr-ho-v2-018m-counterfactual-execution-review/1.0.0",
        "taskId": "OCR-HO-V2-018M",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "COUNTERFACTUAL_EXECUTION_AUTHORIZATION_REVIEW_ONLY",
        },
        "sourceDigests": {
            "artifact018lSha256": source_018l_digest,
            "artifact018kSha256": source_018k_digest,
        },
        "authorizationEvidence": {
            "sourceTask": "OCR-HO-V2-018L",
            "status": source_018l["authorizationIntake"]["status"],
            "counterfactualAuthorized": True,
            "counterfactualExecutionAllowed": False,
            "executionAuthorizationPresent": False,
        },
        "requiredExecutionAuthorization": {
            "schema": EXECUTION_AUTH_SCHEMA,
            "fields": list(REQUIRED_EXECUTION_FIELDS),
            "reason": (
                "018L authorizes future review only. A separate execution record is required "
                "before any diagnostic counterfactual is run."
            ),
        },
        "decision": {
            "status": "COUNTERFACTUAL_EXECUTION_AUTHORIZATION_REQUIRED",
            "counterfactualAuthorized": True,
            "counterfactualExecutionAuthorized": False,
            "counterfactualExecuted": False,
            "selectorChanged": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "The 018L record authorizes consideration only and explicitly leaves execution "
                "false. Do not infer execution authority from review authorization."
            ),
            "nextTask": "OCR-HO-V2-018M",
            "nextAction": (
                "Obtain a separate execution authorization record, or keep the diagnostic "
                "counterfactual closed."
            ),
        },
        "gates": {
            "counterfactualAuthorized": True,
            "counterfactualExecutionAuthorized": False,
            "counterfactualExecuted": False,
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
    parser.add_argument("--artifact-018l", type=Path, required=True)
    parser.add_argument("--artifact-018k", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018l = load(args.artifact_018l)
    source_018k_digest = sha256(args.artifact_018k)
    validate_lineage(source_018l, source_018k_digest)
    report = review(source_018l, sha256(args.artifact_018l), source_018k_digest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "counterfactualExecutionAuthorized": False,
                "counterfactualExecuted": False,
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
