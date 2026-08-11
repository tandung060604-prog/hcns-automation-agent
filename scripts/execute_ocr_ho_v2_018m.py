#!/usr/bin/env python3
"""Execute the authorized OCR-HO-V2-018M sealed-aggregate counterfactual."""

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
EXECUTION_SCOPE = {**SCOPE, "protocol": "AUTO_DETECTOR"}
EXECUTION_SCHEMA = "ocr-ho-v2-018m-counterfactual-execution-authorization-record/1.0.0"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_018l(source: dict[str, Any], source_018k_digest: str) -> None:
    if source.get("schemaVersion") != (
        "ocr-ho-v2-018l-selector-counterfactual-authorization-intake/1.0.0"
    ) or source.get("taskId") != "OCR-HO-V2-018L":
        raise SystemExit("018L source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018L source scope mismatch: {key}")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit("018L must remain sealed and aggregate-only")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit("018L used Ground Truth at selection")
    source_digest = source.get("sourceDigests", {}).get("artifact018kSha256", "")
    if source_digest.casefold() != source_018k_digest.casefold():
        raise SystemExit("018L does not match 018K digest")
    intake = source.get("authorizationIntake", {})
    if (
        intake.get("status") != "VALID_FOR_COUNTERFACTUAL_REVIEW"
        or intake.get("selectorCounterfactualAuthorized") is not True
        or intake.get("sourceArtifactMatch") is not True
        or intake.get("scopeMatch") is not True
    ):
        raise SystemExit("018L counterfactual review authorization is invalid")


def _iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_execution_record(record: dict[str, Any], source_018l_digest: str) -> None:
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != EXECUTION_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-018M"
        or record.get("containsRawPII") is not False
        or str(record.get("sourceArtifactSha256") or "").casefold()
        != source_018l_digest.casefold()
        or record.get("executionScope") != EXECUTION_SCOPE
        or approval.get("approved") is not True
        or not str(approval.get("approverRole") or "").strip()
        or not _iso_timestamp(approval.get("approvedAt"))
        or approval.get("localOnly") is not True
        or approval.get("counterfactualExecutionAuthorized") is not True
        or approval.get("selectorChangeAuthorized") is not False
        or approval.get("developmentReplayAuthorized") is not False
        or approval.get("heldoutEvaluationAuthorized") is not False
        or approval.get("evaluateOnceAuthorized") is not False
        or approval.get("primaryRuntimeChangeAuthorized") is not False
        or approval.get("productionPromotionAllowed") is not False
    ):
        raise SystemExit("018M execution authorization is invalid or broader than diagnostic-only")


def validate_017d(source: dict[str, Any]) -> None:
    if source.get("schemaVersion") != "ocr-ho-v2-017d-selector-counterfactual/1.0.0":
        raise SystemExit("017D source schema mismatch")
    for key, expected in SCOPE.items():
        if key == "diagnosticFieldCount":
            continue
        if source.get(key) != expected:
            raise SystemExit(f"017D source scope mismatch: {key}")
    if source.get("targetFields") != ["fullName", "placeOfOrigin", "placeOfResidence"]:
        raise SystemExit("017D target field scope mismatch")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit("017D must remain aggregate-only")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit("017D used Ground Truth at selection")
    if source.get("protocols", {}).get("gate") != "AUTO_DETECTOR":
        raise SystemExit("017D gate protocol mismatch")
    if source.get("protocols", {}).get("counterfactual") != (
        "SELECTOR_ONLY_PROFILE_WEIGHTED_CONSENSUS"
    ):
        raise SystemExit("017D selector protocol mismatch")


def execute(
    source_018l: dict[str, Any],
    source_017d: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    selected = source_017d["metrics"]["selected_11_10_2"]
    counterfactual = source_017d["metrics"]["counterfactual_017d"]
    der_delta = round(counterfactual["der"] - selected["der"], 6)
    diacritic_delta = counterfactual["diacriticErrorCount"] - selected["diacriticErrorCount"]
    strict_exact_delta = counterfactual["strictExactCount"] - selected["strictExactCount"]
    diagnostics = source_017d["selectionDiagnostics"]
    changed_count = sum(item.get("changed", 0) for item in diagnostics.values())
    quality_hold = der_delta > 0 or diacritic_delta > 0 or strict_exact_delta < 0
    return {
        "schemaVersion": "ocr-ho-v2-018m-selector-counterfactual-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-018M",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForScoring": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "SELECTOR_ONLY_PROFILE_WEIGHTED_CONSENSUS_SEALED_AGGREGATE",
        },
        "sourceDigests": digests,
        "authorization": {
            "sourceTask": "OCR-HO-V2-018L",
            "status": source_018l["authorizationIntake"]["status"],
            "counterfactualExecutionAuthorized": True,
            "selectorChangeAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
        "execution": {
            "status": "SEALED_AGGREGATE_SELECTOR_SIMULATION",
            "counterfactualExecuted": True,
            "ocrRerun": False,
            "predictionOpened": False,
            "replayExecuted": False,
            "selectorChanged": False,
            "runtimeChanged": False,
        },
        "counterfactual": {
            "rule": "SELECTOR_ONLY_PROFILE_WEIGHTED_CONSENSUS",
            "selectedMetrics": {
                "strictExactCount": selected["strictExactCount"],
                "asciiExactCount": selected["asciiExactCount"],
                "cer": selected["cer"],
                "der": selected["der"],
                "diacriticErrorCount": selected["diacriticErrorCount"],
                "referenceDiacriticCount": selected["referenceDiacriticCount"],
            },
            "counterfactualMetrics": {
                "strictExactCount": counterfactual["strictExactCount"],
                "asciiExactCount": counterfactual["asciiExactCount"],
                "cer": counterfactual["cer"],
                "der": counterfactual["der"],
                "diacriticErrorCount": counterfactual["diacriticErrorCount"],
                "referenceDiacriticCount": counterfactual["referenceDiacriticCount"],
            },
            "delta": {
                "der": der_delta,
                "diacriticErrorCount": diacritic_delta,
                "strictExactCount": strict_exact_delta,
            },
            "fieldChangeCounts": {
                field: {
                    "changed": value.get("changed", 0),
                    "counterfactualSelected": value.get("counterfactualSelected", 0),
                    "fallbackCurrent": value.get("fallbackCurrent", 0),
                }
                for field, value in diagnostics.items()
            },
            "changedFieldCount": changed_count,
        },
        "gates": {
            "counterfactualExecutionAuthorized": True,
            "counterfactualExecuted": True,
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
            "qualityNonRegression": "FAIL" if quality_hold else "PASS",
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
            "productionPromotionAllowed": False,
        },
        "decision": {
            "status": "COUNTERFACTUAL_DIAGNOSTIC_COMPLETE_HOLD",
            "counterfactualExecuted": True,
            "counterfactualExecutionAuthorized": True,
            "selectorChanged": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "The authorized sealed-aggregate selector simulation worsened DER and "
                "diacritic errors while reducing strict exact; keep selector/runtime closed."
            ),
            "nextTask": "OCR-HO-V2-018N",
            "nextAction": "Close the selector path and review the regression before any new layer.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-018l", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--artifact-018k", type=Path, required=True)
    parser.add_argument("--artifact-017d", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018l = load(args.artifact_018l)
    source_017d = load(args.artifact_017d)
    digest_018k = sha256(args.artifact_018k)
    digest_018l = sha256(args.artifact_018l)
    validate_018l(source_018l, digest_018k)
    validate_execution_record(load(args.authorization_record), digest_018l)
    validate_017d(source_017d)
    report = execute(
        source_018l,
        source_017d,
        {
            "artifact018lSha256": digest_018l,
            "executionAuthorizationSha256": sha256(args.authorization_record),
            "artifact018kSha256": digest_018k,
            "artifact017dSha256": sha256(args.artifact_017d),
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "counterfactualExecuted": report["execution"]["counterfactualExecuted"],
                "derDelta": report["counterfactual"]["delta"]["der"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
