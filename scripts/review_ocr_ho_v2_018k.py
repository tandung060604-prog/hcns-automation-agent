#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-018K selector safety decision review."""

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


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018j-aggregate-selector-safety-evidence/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018J"
    ):
        raise SystemExit("018J source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018J source scope mismatch: {key}")
    if source.get("containsRawPII") is not False:
        raise SystemExit("018J must remain aggregate-only")
    if source.get("predictionOpened") is not False:
        raise SystemExit("018J prediction must remain sealed")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit("018J used Ground Truth at selection")
    if source.get("protocol", {}).get("gate") != "AUTO_DETECTOR":
        raise SystemExit("018J gate protocol mismatch")
    if source.get("protocol", {}).get("diagnostic") != (
        "AGGREGATE_SELECTOR_SAFETY_EVIDENCE_ONLY"
    ):
        raise SystemExit("018J diagnostic protocol mismatch")
    readiness = source.get("readiness", {})
    if (
        readiness.get("safetyEvidenceCollected") is not True
        or readiness.get("independentSafetyEvidenceReady") is not False
        or readiness.get("selectorCounterfactualOpeningAllowed") is not False
        or readiness.get("counterfactualAuthorized") is not False
    ):
        raise SystemExit("018J safety evidence must remain counterfactual-closed")
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
        raise SystemExit("018J gate invariants mismatch")


def review(source: dict[str, Any], source_digest: str) -> dict[str, Any]:
    evidence = source["evidence"]
    non_regression = evidence["priorNonRegression"]
    eligible_switch = evidence["eligibleSwitch"]
    replay_change = evidence["replayChange"]
    blockers = {
        "priorNonRegressionFailure": (
            non_regression["status"] != "PASS"
            or non_regression["derDelta"] > 0
            or non_regression["diacriticErrorDelta"] > 0
            or non_regression["strictExactDelta"] < 0
        ),
        "noEligibleSelectorSwitch": eligible_switch["eligibleSwitchCount"] == 0,
        "noReplayChangedField": replay_change["changedFieldCount"] == 0,
    }
    return {
        "schemaVersion": "ocr-ho-v2-018k-selector-safety-decision-review/1.0.0",
        "taskId": "OCR-HO-V2-018K",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_SELECTOR_SAFETY_DECISION_REVIEW_ONLY",
        },
        "sourceDigests": {"artifact018jSha256": source_digest},
        "evidence": {
            "priorNonRegression": {
                "status": non_regression["status"],
                "derDelta": non_regression["derDelta"],
                "diacriticErrorDelta": non_regression["diacriticErrorDelta"],
                "strictExactDelta": non_regression["strictExactDelta"],
            },
            "eligibleSwitch": {
                "status": eligible_switch["status"],
                "eligibleSwitchCount": eligible_switch["eligibleSwitchCount"],
                "changedFieldCount": eligible_switch["changedFieldCount"],
            },
            "replayChange": {
                "status": replay_change["status"],
                "eligibleSwitchCount": replay_change["eligibleSwitchCount"],
                "changedFieldCount": replay_change["changedFieldCount"],
            },
            "safetyInvariants": evidence["safetyInvariants"],
            "blockers": blockers,
        },
        "decision": {
            "status": "SELECTOR_COUNTERFACTUAL_NOT_RECOMMENDED_HOLD",
            "counterfactualRecommended": False,
            "counterfactualOpeningAllowed": False,
            "counterfactualAuthorized": False,
            "ownerAuthorizationRequired": True,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "018J safety evidence does not support a selector counterfactual: prior "
                "DER non-regression failed and neither the strict rule nor prior replay "
                "changed a field. Keep the candidate shadow-only."
            ),
            "nextTask": "OCR-HO-V2-018L",
            "nextAction": (
                "Require a new explicit owner authorization record before any selector "
                "counterfactual; do not run one in 018K."
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
    parser.add_argument("--artifact-018j", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.artifact_018j)
    validate_source(source)
    report = review(source, sha256(args.artifact_018j))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "counterfactualRecommended": False,
                "counterfactualAuthorized": False,
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
