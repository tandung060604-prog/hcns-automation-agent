#!/usr/bin/env python3
"""Close the OCR-HO-V2-018M selector path after aggregate regression review."""

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
        != "ocr-ho-v2-018m-selector-counterfactual-diagnostic/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018M"
    ):
        raise SystemExit("018M source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018M source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForScoring") is not True
    ):
        raise SystemExit("018M must remain sealed and aggregate-only")
    protocol = source.get("protocol", {})
    if (
        protocol.get("gate") != "AUTO_DETECTOR"
        or protocol.get("diagnostic")
        != "SELECTOR_ONLY_PROFILE_WEIGHTED_CONSENSUS_SEALED_AGGREGATE"
    ):
        raise SystemExit("018M protocol mismatch")
    authorization = source.get("authorization", {})
    if (
        authorization.get("counterfactualExecutionAuthorized") is not True
        or authorization.get("selectorChangeAuthorized") is not False
        or authorization.get("developmentReplayAuthorized") is not False
        or authorization.get("heldoutEvaluationAuthorized") is not False
        or authorization.get("evaluateOnceAuthorized") is not False
        or authorization.get("primaryRuntimeChangeAuthorized") is not False
        or authorization.get("productionPromotionAllowed") is not False
    ):
        raise SystemExit("018M authorization is broader than diagnostic-only")
    execution = source.get("execution", {})
    if (
        execution.get("counterfactualExecuted") is not True
        or execution.get("ocrRerun") is not False
        or execution.get("replayExecuted") is not False
        or execution.get("selectorChanged") is not False
        or execution.get("runtimeChanged") is not False
    ):
        raise SystemExit("018M execution boundary mismatch")
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
        raise SystemExit("018M gate invariants mismatch")
    if source.get("decision", {}).get("status") != "COUNTERFACTUAL_DIAGNOSTIC_COMPLETE_HOLD":
        raise SystemExit("018M decision is not a completed HOLD")


def review(source: dict[str, Any], source_digest: str) -> dict[str, Any]:
    delta = source["counterfactual"]["delta"]
    changed_fields = source["counterfactual"]["changedFieldCount"]
    regression = {
        "derDelta": delta["der"],
        "diacriticErrorDelta": delta["diacriticErrorCount"],
        "strictExactDelta": delta["strictExactCount"],
        "changedFieldCount": changed_fields,
        "qualityNonRegression": "FAIL"
        if delta["der"] > 0
        or delta["diacriticErrorCount"] > 0
        or delta["strictExactCount"] < 0
        else "PASS",
    }
    return {
        "schemaVersion": "ocr-ho-v2-018n-selector-path-closure-review/1.0.0",
        "taskId": "OCR-HO-V2-018N",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "SELECTOR_PATH_CLOSURE_REVIEW_ONLY",
        },
        "sourceDigests": {"artifact018mSha256": source_digest},
        "evidence": {
            "regression": regression,
            "safetyInvariants": {
                "schemaErrors": 0,
                "sensitiveFalseAcceptance": 0,
                "acceptedCoverage": 0,
                "manualReviewOnly": True,
            },
            "executionBoundaries": {
                "counterfactualExecuted": True,
                "ocrRerun": False,
                "replayExecuted": False,
                "selectorChanged": False,
                "runtimeChanged": False,
            },
        },
        "decision": {
            "status": "SELECTOR_PATH_CLOSED_HOLD",
            "selectorPathOpen": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "The authorized selector simulation worsened DER and diacritic errors "
                "and reduced strict exact; close the selector path and return to a "
                "bounded non-selector layer."
            ),
            "nextTask": "OCR-HO-V2-018O",
            "nextAction": (
                "Review one bounded detector/crop or recognizer/token-alignment layer; "
                "do not reopen selector counterfactuals."
            ),
        },
        "gates": {
            "counterfactualExecutionAuthorized": True,
            "counterfactualExecuted": True,
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
    parser.add_argument("--artifact-018m", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.artifact_018m)
    validate_source(source)
    report = review(source, sha256(args.artifact_018m))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "selectorPathOpen": report["decision"]["selectorPathOpen"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
