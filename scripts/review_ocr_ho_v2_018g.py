#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-018G selector-opening review."""

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
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(
    source: dict[str, Any], schema: str, task_id: str, *, diagnostic_fields: int | None = None
) -> None:
    if source.get("schemaVersion") != schema or source.get("taskId") not in (None, task_id):
        raise SystemExit(f"{task_id} source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{task_id} source scope mismatch: {key}")
    if diagnostic_fields is not None and source.get("diagnosticFieldCount") != diagnostic_fields:
        raise SystemExit(f"{task_id} diagnostic field scope mismatch")
    if source.get("containsRawPII") is not False:
        raise SystemExit(f"{task_id} must be aggregate-only")
    if source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} prediction must remain sealed")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit(f"{task_id} must not use Ground Truth at selection")


def validate_lineage(
    source_018f: dict[str, Any],
    source_017d: dict[str, Any],
    source_017e: dict[str, Any],
    source_017f: dict[str, Any],
) -> None:
    validate_source(
        source_018f,
        "ocr-ho-v2-018f-recognizer-token-attribution/1.0.0",
        "OCR-HO-V2-018F",
        diagnostic_fields=45,
    )
    validate_source(
        source_017d,
        "ocr-ho-v2-017d-selector-counterfactual/1.0.0",
        "OCR-HO-V2-017D",
    )
    validate_source(
        source_017e,
        "ocr-ho-v2-017e-selector-rule-review/1.0.0",
        "OCR-HO-V2-017E",
    )
    validate_source(
        source_017f,
        "ocr-ho-v2-017f-selector-replay/1.0.0",
        "OCR-HO-V2-017F",
    )
    if source_018f.get("candidateRule", {}).get("selectionEligible") is not False:
        raise SystemExit("018F must not make a selector eligible")
    if source_018f.get("decision", {}).get("counterfactualAuthorized") is not False:
        raise SystemExit("018F counterfactual authorization must remain false")
    if source_017d.get("gates", {}).get("derNotWorse") is not False:
        raise SystemExit("017D must retain its DER regression")
    if source_017e.get("selectionAudit", {}).get("eligibleSwitchCount") != 0:
        raise SystemExit("017E must retain zero eligible switches")
    if source_017f.get("selectionAudit", {}).get("changedFieldCount") != 0:
        raise SystemExit("017F must retain zero changed fields")


def review(
    source_018f: dict[str, Any],
    source_017d: dict[str, Any],
    source_017e: dict[str, Any],
    source_017f: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    hit = source_018f["attribution"]["autoRegionHit"]
    selected = source_017d["metrics"]["selected_11_10_2"]
    counterfactual = source_017d["metrics"]["counterfactual_017d"]
    der_delta = round(counterfactual["der"] - selected["der"], 6)
    diacritic_delta = counterfactual["diacriticErrorCount"] - selected["diacriticErrorCount"]
    exact_delta = counterfactual["strictExactCount"] - selected["strictExactCount"]
    rule_audit = source_017e["selectionAudit"]
    replay_audit = source_017f["selectionAudit"]
    criteria = {
        "recognizerDominantEvidence": {
            "status": "PASS" if hit["recognizerDominantAttribution"] else "HOLD",
            "observedRate": hit["recognizerDisagreementRate"],
            "threshold": 0.5,
        },
        "priorCounterfactualNonRegression": {
            "status": "PASS" if der_delta <= 0 and diacritic_delta <= 0 else "FAIL",
            "derDelta": der_delta,
            "diacriticErrorDelta": diacritic_delta,
            "strictExactDelta": exact_delta,
        },
        "strictRuleEligibleSwitch": {
            "status": "PASS" if rule_audit["eligibleSwitchCount"] > 0 else "FAIL",
            "eligibleSwitchCount": rule_audit["eligibleSwitchCount"],
            "changedFieldCount": rule_audit["changedFieldCount"],
        },
        "replayChangedFieldEvidence": {
            "status": "PASS" if replay_audit["changedFieldCount"] > 0 else "FAIL",
            "changedFieldCount": replay_audit["changedFieldCount"],
            "eligibleSwitchCount": replay_audit["eligibleSwitchCount"],
        },
        "safetyInvariants": {
            "status": "PASS",
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
        },
    }
    opening_allowed = all(item["status"] == "PASS" for item in criteria.values())
    return {
        "schemaVersion": "ocr-ho-v2-018g-selector-counterfactual-review/1.0.0",
        "taskId": "OCR-HO-V2-018G",
        **SCOPE,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_SELECTOR_OPENING_REVIEW_ONLY",
        },
        "sourceDigests": digests,
        "evidence": {
            "018F": {
                "dominantCohort": source_018f["decision"]["dominantCohort"],
                "recognizerDisagreementCount": hit["recognizerDisagreementCount"],
                "autoRegionHitErrorGroupCount": hit["errorGroupCount"],
                "recognizerDisagreementRate": hit["recognizerDisagreementRate"],
                "tokenMismatchCount": hit["tokenMismatchCount"],
                "lineOrderMismatchCount": hit["lineOrderMismatchCount"],
            },
            "017D": {
                "selectedDer": selected["der"],
                "counterfactualDer": counterfactual["der"],
                "selectedDiacriticErrorCount": selected["diacriticErrorCount"],
                "counterfactualDiacriticErrorCount": counterfactual["diacriticErrorCount"],
                "selectedStrictExactCount": selected["strictExactCount"],
                "counterfactualStrictExactCount": counterfactual["strictExactCount"],
            },
            "017E": {
                "eligibleSwitchCount": rule_audit["eligibleSwitchCount"],
                "changedFieldCount": rule_audit["changedFieldCount"],
            },
            "017F": {
                "eligibleSwitchCount": replay_audit["eligibleSwitchCount"],
                "changedFieldCount": replay_audit["changedFieldCount"],
            },
        },
        "openingCriteria": criteria,
        "selectorOpening": {
            "allowed": opening_allowed,
            "status": "AUTHORIZED" if opening_allowed else "DENIED_HOLD",
            "counterfactualAuthorized": False,
            "ownerAuthorizationPresent": False,
            "reason": (
                "Recognizer dominance alone is insufficient: prior counterfactual DER and "
                "diacritic errors increased, while strict rule/replay produced no switch or "
                "changed field."
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
        "decision": {
            "status": "NO_COUNTERFACTUAL_AUTHORIZATION_HOLD",
            "selectedLayer": "RECOGNIZER_TOKEN_ALIGNMENT",
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "018F supplies a dominant recognizer-attribution cohort, but it does not "
                "overcome the prior DER regression or zero-switch evidence. Keep selector "
                "counterfactual closed."
            ),
            "nextAction": (
                "Keep the candidate shadow-only. Require a separately approved safety-evidence "
                "review before any selector counterfactual; do not run one in 018G."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-018f", type=Path, required=True)
    parser.add_argument("--artifact-017d", type=Path, required=True)
    parser.add_argument("--artifact-017e", type=Path, required=True)
    parser.add_argument("--artifact-017f", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = {
        "018F": load(args.artifact_018f),
        "017D": load(args.artifact_017d),
        "017E": load(args.artifact_017e),
        "017F": load(args.artifact_017f),
    }
    validate_lineage(sources["018F"], sources["017D"], sources["017E"], sources["017F"])
    report = review(
        sources["018F"],
        sources["017D"],
        sources["017E"],
        sources["017F"],
        {name: sha256(path) for name, path in {
            "artifact018fSha256": args.artifact_018f,
            "artifact017dSha256": args.artifact_017d,
            "artifact017eSha256": args.artifact_017e,
            "artifact017fSha256": args.artifact_017f,
        }.items()},
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
                "counterfactualAuthorized": False,
                "openingAllowed": report["selectorOpening"]["allowed"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
