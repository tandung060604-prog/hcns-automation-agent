#!/usr/bin/env python3
"""Review residence recognizer error classes from sealed aggregate evidence."""

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
ERROR_CLASSES = (
    "LINE_ID_MISS",
    "LINE_ORDER_MISMATCH",
    "TOKEN_OMISSION",
    "TOKEN_EXTRA",
    "TOKEN_SWAP",
    "DUPLICATE_LINE",
    "RECOGNIZER_DISAGREEMENT",
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_scope(source: dict[str, Any], label: str) -> None:
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{label} scope mismatch: {key}")


def validate_018t(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018t-bounded-non-selector-diagnostic-selection/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018T"
    ):
        raise SystemExit("018T source schema mismatch")
    validate_scope(source, "018T")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018T must remain sealed and attribution-only")
    protocol = source.get("protocol", {})
    if (
        protocol.get("gate") != "AUTO_DETECTOR"
        or protocol.get("diagnostic")
        != "AGGREGATE_BOUNDED_NON_SELECTOR_SELECTION_ONLY"
    ):
        raise SystemExit("018T protocol mismatch")
    ceiling = source.get("evidence", {}).get("crossTabCeiling", {})
    if (
        ceiling.get("combinationCount") != 16
        or ceiling.get("evaluatedPerCombination") != 15
        or ceiling.get("gateAsciiExactCount") != 13
        or ceiling.get("profileOracleBestMaxAsciiExactCount") != 2
        or ceiling.get("variantOracleBestMaxAsciiExactCount") != 2
        or ceiling.get("profileOrVariantReachesGate") is not False
    ):
        raise SystemExit("018T cross-tab ceiling mismatch")
    if (
        source.get("decision", {}).get("selectedDiagnostic")
        != "RESIDENCE_RECOGNIZER_ERROR_CLASS_ATTRIBUTION"
    ):
        raise SystemExit("018T selected diagnostic mismatch")
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
        raise SystemExit("018T authorization boundary mismatch")
    validate_gates(source.get("gates", {}), "018T")


def validate_gates(gates: dict[str, Any], label: str) -> None:
    if (
        gates.get("developmentRegressionGate") != "HOLD"
        or gates.get("heldoutReadinessGate") != "HOLD"
        or gates.get("schemaErrors") != 0
        or gates.get("sensitiveFalseAcceptance") != 0
        or gates.get("acceptedCoverage") != 0
        or gates.get("manualReviewOnly") is not True
        or gates.get("productionPromotionAllowed") is not False
    ):
        raise SystemExit(f"{label} gate mismatch")


def validate_018p(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018p-recognizer-token-attribution/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018P"
    ):
        raise SystemExit("018P source schema mismatch")
    validate_scope(source, "018P")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018P must remain sealed and attribution-only")
    protocol = source.get("protocol", {})
    if (
        protocol.get("gate") != "AUTO_DETECTOR"
        or protocol.get("diagnostic")
        != "AGGREGATE_RECOGNIZER_TOKEN_ATTRIBUTION_ONLY"
    ):
        raise SystemExit("018P protocol mismatch")
    if source.get("tokenDefinition") != (
        "NFC-normalized whitespace-delimited tokens; no model token IDs"
    ):
        raise SystemExit("018P token definition mismatch")
    residence = source.get("byField", {}).get("placeOfResidence", {})
    classes = residence.get("classCounts", {})
    expected = {
        "LINE_ID_MISS": 1,
        "LINE_ORDER_MISMATCH": 32,
        "TOKEN_OMISSION": 0,
        "TOKEN_EXTRA": 8,
        "TOKEN_SWAP": 3,
        "DUPLICATE_LINE": 0,
        "RECOGNIZER_DISAGREEMENT": 116,
    }
    if (
        residence.get("groups") != 160
        or residence.get("eligibleLineTokenGroups") != 127
        or residence.get("errorGroupCount") != 160
        or residence.get("dominantErrorClass") != "RECOGNIZER_DISAGREEMENT"
        or residence.get("dominantErrorRate") != 0.725
        or residence.get("tokenMismatchCount") != 11
        or residence.get("lineOrderMismatchCount") != 32
        or residence.get("recognizerDisagreementCount") != 116
        or classes != expected
    ):
        raise SystemExit("018P residence error-class evidence mismatch")
    validate_gates(source.get("gates", {}), "018P")
    decision = source.get("decision", {})
    if any(
        decision.get(key) is not False
        for key in (
            "counterfactualAuthorized",
            "selectorChanged",
            "runtimeChanged",
            "replayExecuted",
            "heldoutOpened",
            "promotionAllowed",
        )
    ):
        raise SystemExit("018P authorization boundary mismatch")


def review(
    source_018t: dict[str, Any], source_018p: dict[str, Any], digests: dict[str, str]
) -> dict[str, Any]:
    residence = source_018p["byField"]["placeOfResidence"]
    class_counts = {
        key: residence["classCounts"][key] for key in ERROR_CLASSES
    }
    total_errors = sum(class_counts.values())
    recognizer_count = class_counts["RECOGNIZER_DISAGREEMENT"]
    non_recognizer_count = total_errors - recognizer_count
    recognizer_rate = recognizer_count / total_errors
    eligible_groups = residence["eligibleLineTokenGroups"]
    recognizer_share_of_eligible = recognizer_count / eligible_groups
    return {
        "schemaVersion": "ocr-ho-v2-018u-residence-error-class-attribution/1.0.0",
        "taskId": "OCR-HO-V2-018U",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_RESIDENCE_ERROR_CLASS_ATTRIBUTION_ONLY",
        },
        "sourceDigests": digests,
        "tokenDefinition": "NFC-normalized whitespace-delimited tokens; no model token IDs",
        "evidence": {
            "source018tSelection": {
                "selectedDiagnostic": source_018t["decision"]["selectedDiagnostic"],
                "crossTabCeiling": source_018t["evidence"]["crossTabCeiling"],
            },
            "residenceAutoRegionHitCohort": {
                "field": "placeOfResidence",
                "cohort": "AUTO_REGION_HIT",
                "groups": residence["groups"],
                "eligibleLineTokenGroups": eligible_groups,
                "errorGroupCount": residence["errorGroupCount"],
                "classCounts": class_counts,
                "recognizerDisagreementRateAmongErrorGroups": recognizer_rate,
                "recognizerDisagreementShareOfEligibleGroups": recognizer_share_of_eligible,
                "nonRecognizerErrorCount": non_recognizer_count,
                "tokenMismatchCount": residence["tokenMismatchCount"],
                "lineOrderMismatchCount": residence["lineOrderMismatchCount"],
            },
            "attributionBoundary": {
                "fieldErrorClassBreakdownAvailable": True,
                "profileVariantErrorClassCrossTabAvailable": False,
                "reason": (
                    "018P provides residence field-level class counts, while its "
                    "profile/variant aggregates cover all target fields. 018S provides "
                    "residence profile/variant exact metrics but no joint error-class "
                    "counts; therefore no profile/variant error attribution is claimed."
                ),
            },
        },
        "decision": {
            "status": "RESIDENCE_ERROR_CLASS_ATTRIBUTED_HOLD",
            "selectedDiagnostic": "RESIDENCE_RECOGNIZER_ERROR_CLASS_ATTRIBUTION",
            "dominantErrorClass": "RECOGNIZER_DISAGREEMENT",
            "dominanceThreshold": 0.5,
            "dominanceObserved": recognizer_rate,
            "dominanceThresholdReached": recognizer_rate >= 0.5,
            "candidateRule": (
                "Keep residence recognizer disagreement as the bounded attribution "
                "cohort; do not infer a profile/variant winner or change selector."
            ),
            "profileSelectorAuthorized": False,
            "variantSelectorAuthorized": False,
            "counterfactualAuthorized": False,
            "selectorPathOpen": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "Recognizer disagreement is 116/160 residence error groups (72.5%) "
                "and 116/127 eligible line/token groups, so the selected error class "
                "is confirmed as the dominant bounded cohort. Existing evidence does "
                "not support a profile/variant attribution or a safe runtime change."
            ),
            "nextTask": "OCR-HO-V2-018V",
            "nextAction": (
                "Prepare one new aggregate-only residence profile/variant-by-error-class "
                "evidence review if independently authorized; do not run OCR, replay "
                "or selector counterfactual."
            ),
        },
        "gates": {
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
            "productionPromotionAllowed": False,
        },
        "lineage": {
            "source018tBoundedSelection": True,
            "source018pResidenceClassCounts": True,
            "rawPredictionOpened": False,
            "groundTruthUsedAtSelection": False,
            "groundTruthUsedForAttribution": True,
            "selectorChanged": False,
            "counterfactualExecuted": False,
            "replayExecuted": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-018t", type=Path, required=True)
    parser.add_argument("--artifact-018p", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018t = load(args.artifact_018t)
    source_018p = load(args.artifact_018p)
    validate_018t(source_018t)
    validate_018p(source_018p)
    report = review(
        source_018t,
        source_018p,
        {
            "artifact018tSha256": sha256(args.artifact_018t),
            "artifact018pSha256": sha256(args.artifact_018p),
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
                "dominantErrorClass": report["decision"]["dominantErrorClass"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
