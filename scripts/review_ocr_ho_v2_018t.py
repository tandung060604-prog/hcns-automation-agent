#!/usr/bin/env python3
"""Choose one bounded non-selector diagnostic from OCR-HO-V2-018S evidence."""

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


def validate_scope(source: dict[str, Any], label: str) -> None:
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{label} scope mismatch: {key}")


def validate_018s(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018s-residence-profile-variant-crosstab-validation/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018S"
    ):
        raise SystemExit("018S source schema mismatch")
    validate_scope(source, "018S")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018S must remain sealed and attribution-only")
    protocol = source.get("protocol", {})
    if (
        protocol.get("gate") != "AUTO_DETECTOR"
        or protocol.get("diagnostic")
        != "ORACLE_PROFILE_VARIANT_CROSSTAB_ATTRIBUTION_ONLY"
    ):
        raise SystemExit("018S protocol mismatch")
    cross_tab = source.get("crossTab", {})
    if (
        cross_tab.get("available") is not True
        or cross_tab.get("residenceSpecific") is not True
        or cross_tab.get("combinationCount") != 16
        or cross_tab.get("evaluatedPerCombination") != 15
        or cross_tab.get("oracleAttributionOnly") is not True
    ):
        raise SystemExit("018S cross-tab scope mismatch")
    ceiling = source.get("residenceCeiling", {})
    if (
        ceiling.get("gateAsciiExactCount") != 13
        or ceiling.get("profileOracleBestMaxAsciiExactCount") != 2
        or ceiling.get("variantOracleBestMaxAsciiExactCount") != 2
        or ceiling.get("profileOrVariantReachesGate") is not False
    ):
        raise SystemExit("018S residence ceiling mismatch")
    rows = source.get("profileVariantResidenceRows", [])
    if len(rows) != 16:
        raise SystemExit("018S residence cross-tab row count mismatch")
    if any(row.get("residence", {}).get("evaluated") != 15 for row in rows):
        raise SystemExit("018S residence row evaluation mismatch")
    decision = source.get("decision", {})
    if (
        decision.get("profileVariantWinner") is not None
        or decision.get("profileSelectorAuthorized") is not False
        or decision.get("variantSelectorAuthorized") is not False
        or decision.get("counterfactualAuthorized") is not False
        or decision.get("selectorPathOpen") is not False
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
        or decision.get("heldoutOpened") is not False
        or decision.get("promotionAllowed") is not False
    ):
        raise SystemExit("018S selector boundary mismatch")
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
        raise SystemExit("018S gate mismatch")


def validate_018q(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018q-recognizer-sublayer-selection/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018Q"
    ):
        raise SystemExit("018Q source schema mismatch")
    validate_scope(source, "018Q")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018Q must remain sealed and attribution-only")
    protocol = source.get("protocol", {})
    if (
        protocol.get("gate") != "AUTO_DETECTOR"
        or protocol.get("diagnostic")
        != "AGGREGATE_RECOGNIZER_SUBLAYER_SELECTION_ONLY"
    ):
        raise SystemExit("018Q protocol mismatch")
    comparison = source.get("evidence", {}).get("residenceSubLayerComparison", {})
    if comparison != {
        "recognizerDisagreement": 116,
        "lineOrderMismatch": 32,
        "tokenMismatch": 11,
    }:
        raise SystemExit("018Q residence sub-layer counts mismatch")
    basis = source.get("evidence", {}).get("selectionBasis", {})
    if (
        basis.get("selectedField") != "placeOfResidence"
        or basis.get("selectedCohort") != "AUTO_REGION_HIT"
        or basis.get("selectedClass") != "RECOGNIZER_DISAGREEMENT"
        or basis.get("selectedSubLayer")
        != "PLACE_OF_RESIDENCE_RECOGNIZER_DISAGREEMENT"
        or basis.get("profileOrVariantSelectorUsed") is not False
    ):
        raise SystemExit("018Q selection basis mismatch")
    decision = source.get("decision", {})
    if (
        decision.get("selectedSubLayer")
        != "PLACE_OF_RESIDENCE_RECOGNIZER_DISAGREEMENT"
        or decision.get("selectorPathOpen") is not False
        or decision.get("counterfactualAuthorized") is not False
        or decision.get("profileSelectorAuthorized") is not False
        or decision.get("variantSelectorAuthorized") is not False
        or decision.get("lineOrderChangeAuthorized") is not False
        or decision.get("tokenAlignmentChangeAuthorized") is not False
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
        or decision.get("heldoutOpened") is not False
        or decision.get("promotionAllowed") is not False
    ):
        raise SystemExit("018Q authorization boundary mismatch")
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
        raise SystemExit("018Q gate mismatch")


def review(
    source_018s: dict[str, Any], source_018q: dict[str, Any], digests: dict[str, str]
) -> dict[str, Any]:
    ceiling = source_018s["residenceCeiling"]
    best_row = source_018s["decision"]["bestDiagnosticRow"]
    residence_classes = source_018q["evidence"]["residenceSubLayerComparison"]
    eligible = sum(residence_classes.values())
    return {
        "schemaVersion": (
            "ocr-ho-v2-018t-bounded-non-selector-diagnostic-selection/1.0.0"
        ),
        "taskId": "OCR-HO-V2-018T",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_BOUNDED_NON_SELECTOR_SELECTION_ONLY",
        },
        "sourceDigests": digests,
        "evidence": {
            "crossTabCeiling": {
                "crossTabValidated": True,
                "combinationCount": 16,
                "evaluatedPerCombination": 15,
                "gateAsciiExactCount": ceiling["gateAsciiExactCount"],
                "profileOracleBestMaxAsciiExactCount": ceiling[
                    "profileOracleBestMaxAsciiExactCount"
                ],
                "variantOracleBestMaxAsciiExactCount": ceiling[
                    "variantOracleBestMaxAsciiExactCount"
                ],
                "profileOrVariantReachesGate": ceiling[
                    "profileOrVariantReachesGate"
                ],
                "bestDiagnosticRow": {
                    "profile": best_row["profile"],
                    "variant": best_row["variant"],
                    "asciiExactCount": best_row["asciiExactCount"],
                    "strictExactCount": best_row["strictExactCount"],
                },
            },
            "residenceErrorClasses": {
                **residence_classes,
                "eligibleErrorGroupCount": eligible,
                "dominantClass": "RECOGNIZER_DISAGREEMENT",
                "dominantClassCount": residence_classes["recognizerDisagreement"],
            },
            "selectionBasis": {
                "selectedDiagnostic": "RESIDENCE_RECOGNIZER_ERROR_CLASS_ATTRIBUTION",
                "reason": (
                    "The residence profile/variant cross-tab is valid but its best "
                    "oracle result is only 2/15 ASCII exact versus the 13/15 gate. "
                    "Within the residence AUTO_REGION_HIT cohort, recognizer "
                    "disagreement is the dominant bounded error class (116), ahead "
                    "of line-order mismatch (32) and token mismatch (11)."
                ),
                "notASelector": True,
            },
        },
        "decision": {
            "status": "NON_SELECTOR_DIAGNOSTIC_SELECTED_HOLD",
            "selectedDiagnostic": "RESIDENCE_RECOGNIZER_ERROR_CLASS_ATTRIBUTION",
            "candidateRule": (
                "Review residence recognizer error-class attribution across existing "
                "evidence; do not choose a profile/variant or modify selector logic."
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
                "Cross-tab evidence establishes a low ceiling, not a winner. The "
                "next step is one aggregate-only residence recognizer error-class "
                "review, with all selector, replay and runtime paths closed."
            ),
            "nextTask": "OCR-HO-V2-018U",
            "nextAction": (
                "Run one aggregate-only residence recognizer error-class attribution "
                "review; no selector, counterfactual, replay, OCR or runtime change."
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
            "source018sCrossTabValidated": True,
            "source018qBoundedResidenceLayer": True,
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
    parser.add_argument("--artifact-018s", type=Path, required=True)
    parser.add_argument("--artifact-018q", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018s = load(args.artifact_018s)
    source_018q = load(args.artifact_018q)
    validate_018s(source_018s)
    validate_018q(source_018q)
    report = review(
        source_018s,
        source_018q,
        {
            "artifact018sSha256": sha256(args.artifact_018s),
            "artifact018qSha256": sha256(args.artifact_018q),
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
                "selectedDiagnostic": report["decision"]["selectedDiagnostic"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
