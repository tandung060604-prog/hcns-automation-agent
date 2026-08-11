#!/usr/bin/env python3
"""Review residence recognizer disagreement across sealed profile/variant aggregates."""

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


def validate_018q(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018q-recognizer-sublayer-selection/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018Q"
    ):
        raise SystemExit("018Q source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018Q source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018Q must remain sealed and aggregate-only")
    decision = source.get("decision", {})
    if (
        decision.get("selectedSubLayer")
        != "PLACE_OF_RESIDENCE_RECOGNIZER_DISAGREEMENT"
        or decision.get("selectorPathOpen") is not False
        or decision.get("counterfactualAuthorized") is not False
        or decision.get("profileSelectorAuthorized") is not False
        or decision.get("variantSelectorAuthorized") is not False
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
    ):
        raise SystemExit("018Q sub-layer authorization is broader than diagnostic-only")
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
        raise SystemExit("018Q gate invariants mismatch")


def validate_018p(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018p-recognizer-token-attribution/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018P"
    ):
        raise SystemExit("018P source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018P source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018P must remain sealed and aggregate-only")
    if source.get("protocol", {}).get("gate") != "AUTO_DETECTOR":
        raise SystemExit("018P gate protocol mismatch")
    if source.get("protocol", {}).get("diagnostic") != (
        "AGGREGATE_RECOGNIZER_TOKEN_ATTRIBUTION_ONLY"
    ):
        raise SystemExit("018P diagnostic protocol mismatch")
    residence = source.get("byField", {}).get("placeOfResidence", {})
    classes = residence.get("classCounts", {})
    if (
        classes.get("RECOGNIZER_DISAGREEMENT") != 116
        or classes.get("LINE_ORDER_MISMATCH") != 32
        or residence.get("tokenMismatchCount") != 11
    ):
        raise SystemExit("018P residence cohort mismatch")
    if not source.get("byProfile") or not source.get("byVariant"):
        raise SystemExit("018P profile/variant aggregate evidence is missing")
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
        raise SystemExit("018P gate invariants mismatch")


def summarize_group(value: dict[str, Any]) -> dict[str, Any]:
    hit = value["autoRegionHit"]
    return {
        "autoRegionHitErrorGroups": hit["errorGroupCount"],
        "recognizerDisagreementCount": hit["recognizerDisagreementCount"],
        "recognizerDisagreementRate": value[
            "recognizerDisagreementRateAmongHitErrors"
        ],
        "lineOrderMismatchCount": hit["lineOrderMismatchCount"],
        "tokenMismatchCount": hit["tokenMismatchCount"],
        "autoRegionMissLineIdCount": value["autoRegionMiss"]["errorGroupCount"],
    }


def review(
    source_018q: dict[str, Any], source_018p: dict[str, Any], digests: dict[str, str]
) -> dict[str, Any]:
    profile_evidence = {
        name: summarize_group(value)
        for name, value in source_018p["byProfile"].items()
    }
    variant_evidence = {
        name: summarize_group(value)
        for name, value in source_018p["byVariant"].items()
    }
    residence = source_018q["evidence"]["fieldCohorts"]["placeOfResidence"]
    profile_ranking = sorted(
        profile_evidence,
        key=lambda name: profile_evidence[name]["recognizerDisagreementRate"],
    )
    variant_ranking = sorted(
        variant_evidence,
        key=lambda name: variant_evidence[name]["recognizerDisagreementRate"],
    )
    return {
        "schemaVersion": "ocr-ho-v2-018r-residence-profile-variant-review/1.0.0",
        "taskId": "OCR-HO-V2-018R",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_RESIDENCE_PROFILE_VARIANT_REVIEW_ONLY",
        },
        "sourceDigests": digests,
        "evidenceScope": {
            "residenceCohort": "PLACE_OF_RESIDENCE_AUTO_REGION_HIT",
            "profileVariantAggregateScope": "ALL_TARGET_FIELDS_AUTO_REGION_HIT",
            "residenceSpecificProfileVariantCrossTabAvailable": False,
            "reason": (
                "018P stores profile and variant aggregates across all target fields, "
                "not a residence-by-profile/variant cross-tab."
            ),
        },
        "residenceCohort": {
            "recognizerDisagreementCount": residence["recognizerDisagreementCount"],
            "lineOrderMismatchCount": residence["lineOrderMismatchCount"],
            "tokenMismatchCount": residence["tokenMismatchCount"],
            "dominantErrorClass": residence["dominantErrorClass"],
        },
        "profileEvidence": profile_evidence,
        "variantEvidence": variant_evidence,
        "aggregateRankings": {
            "lowestGlobalRecognizerDisagreementRateProfiles": profile_ranking,
            "lowestGlobalRecognizerDisagreementRateVariants": variant_ranking,
            "rankingIsNotResidenceSpecific": True,
        },
        "decision": {
            "status": "RESIDENCE_PROFILE_VARIANT_REVIEW_HOLD",
            "selectedSubLayer": "PLACE_OF_RESIDENCE_RECOGNIZER_DISAGREEMENT",
            "profileVariantWinner": None,
            "profileSelectorAuthorized": False,
            "variantSelectorAuthorized": False,
            "counterfactualAuthorized": False,
            "selectorPathOpen": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "Global profile/variant rates are descriptive only; residence-specific "
                "cross-tab evidence is unavailable, so no profile or variant winner is "
                "selected and no selector path is reopened."
            ),
            "nextTask": "OCR-HO-V2-018S",
            "nextAction": (
                "Obtain or validate an independent residence-by-profile/variant "
                "aggregate artifact without opening raw prediction values; keep HOLD "
                "if the cross-tab is unavailable."
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
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-018q", type=Path, required=True)
    parser.add_argument("--artifact-018p", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018q = load(args.artifact_018q)
    source_018p = load(args.artifact_018p)
    validate_018q(source_018q)
    validate_018p(source_018p)
    report = review(
        source_018q,
        source_018p,
        {
            "artifact018qSha256": sha256(args.artifact_018q),
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
                "crossTabAvailable": report["evidenceScope"][
                    "residenceSpecificProfileVariantCrossTabAvailable"
                ],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
