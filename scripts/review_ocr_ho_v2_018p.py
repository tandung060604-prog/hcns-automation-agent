#!/usr/bin/env python3
"""Produce aggregate-only recognizer/token alignment attribution for OCR-HO-V2."""

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
TOKEN_CLASSES = (
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


def validate_scope(source: dict[str, Any], task_id: str) -> None:
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{task_id} source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
    ):
        raise SystemExit(f"{task_id} must remain sealed and aggregate-only")


def validate_018o(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018o-layer-selection-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018O"
    ):
        raise SystemExit("018O source schema mismatch")
    validate_scope(source, "018O")
    decision = source.get("decision", {})
    if (
        decision.get("selectedLayer") != "RECOGNIZER_TOKEN_ALIGNMENT"
        or decision.get("selectorPathOpen") is not False
        or decision.get("patchAuthorized") is not False
        or decision.get("replayAuthorized") is not False
        or decision.get("counterfactualAuthorized") is not False
        or decision.get("runtimeChanged") is not False
    ):
        raise SystemExit("018O must keep the selected layer diagnostic-only")


def compact_aggregate(value: dict[str, Any]) -> dict[str, Any]:
    class_counts = value.get("classCounts", {})
    if any(key not in class_counts for key in TOKEN_CLASSES):
        raise SystemExit("018F token class schema mismatch")
    return {
        "groups": value.get("groups"),
        "eligibleLineTokenGroups": value.get("eligibleLineTokenGroups"),
        "classCounts": {key: class_counts[key] for key in TOKEN_CLASSES},
        "errorGroupCount": value.get("errorGroupCount"),
        "dominantErrorClass": value.get("dominantErrorClass"),
        "dominantErrorRate": value.get("dominantErrorRate"),
        "tokenMismatchCount": value.get("tokenMismatchCount"),
        "lineOrderMismatchCount": value.get("lineOrderMismatchCount"),
        "recognizerDisagreementCount": value.get("recognizerDisagreementCount"),
    }


def validate_018f(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018f-recognizer-token-attribution/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018F"
    ):
        raise SystemExit("018F source schema mismatch")
    validate_scope(source, "018F")
    protocol = source.get("protocol", {})
    if (
        protocol.get("gate") != "AUTO_DETECTOR"
        or protocol.get("diagnostic") != "ORACLE_LINE_TOKEN_ATTRIBUTION_ONLY"
    ):
        raise SystemExit("018F protocol mismatch")
    if source.get("tokenDefinition") != (
        "NFC-normalized whitespace-delimited tokens; no model token IDs"
    ):
        raise SystemExit("018F token definition mismatch")
    lineage = source.get("lineage", {})
    if (
        lineage.get("automaticRoiReconciled") is not True
        or lineage.get("boundaryPatchAuthorized") is not False
        or lineage.get("replayExecuted") is not False
    ):
        raise SystemExit("018F lineage boundary mismatch")
    cohorts = source.get("cohorts", {})
    hit = cohorts.get("AUTO_REGION_HIT", {})
    miss = cohorts.get("AUTO_REGION_MISS", {})
    if (
        hit.get("groups") != 430
        or hit.get("eligibleLineTokenGroups") != 357
        or hit.get("errorGroupCount") != 375
        or hit.get("dominantErrorClass") != "RECOGNIZER_DISAGREEMENT"
        or hit.get("recognizerDisagreementCount") != 291
        or hit.get("lineOrderMismatchCount") != 72
        or hit.get("tokenMismatchCount") != 11
        or hit.get("dominantErrorRate") != 0.776
        or miss.get("groups") != 245
        or miss.get("errorGroupCount") != 245
        or miss.get("dominantErrorClass") != "LINE_ID_MISS"
    ):
        raise SystemExit("018F cohort evidence mismatch")
    decision = source.get("decision", {})
    gates = source.get("gates", {})
    if (
        decision.get("selectedLayer") != "RECOGNIZER_TOKEN_ALIGNMENT"
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
        or decision.get("patchAuthorized") is not False
        or decision.get("counterfactualAuthorized") is not False
        or gates.get("developmentRegressionGate") != "HOLD"
        or gates.get("heldoutReadinessGate") != "HOLD"
        or gates.get("schemaErrors") != 0
        or gates.get("sensitiveFalseAcceptance") != 0
        or gates.get("acceptedCoverage") != 0
        or gates.get("manualReviewOnly") is not True
        or gates.get("productionPromotionAllowed") is not False
    ):
        raise SystemExit("018F attribution-only invariants mismatch")


def review(
    source_018o: dict[str, Any], source_018f: dict[str, Any], digests: dict[str, str]
) -> dict[str, Any]:
    cohorts = source_018f["cohorts"]
    hit = compact_aggregate(cohorts["AUTO_REGION_HIT"])
    miss = compact_aggregate(cohorts["AUTO_REGION_MISS"])
    by_field = {
        name: compact_aggregate(value)
        for name, value in source_018f.get("byField", {}).items()
    }
    by_profile = {
        name: {
            "autoRegionHit": compact_aggregate(value["autoRegionHit"]),
            "autoRegionMiss": compact_aggregate(value["autoRegionMiss"]),
            "recognizerDisagreementRateAmongHitErrors": value[
                "recognizerDisagreementRateAmongHitErrors"
            ],
        }
        for name, value in source_018f.get("byProfile", {}).items()
    }
    by_variant = {
        name: {
            "autoRegionHit": compact_aggregate(value["autoRegionHit"]),
            "autoRegionMiss": compact_aggregate(value["autoRegionMiss"]),
            "recognizerDisagreementRateAmongHitErrors": value[
                "recognizerDisagreementRateAmongHitErrors"
            ],
        }
        for name, value in source_018f.get("byVariant", {}).items()
    }
    dominant_field = max(
        by_field,
        key=lambda name: by_field[name]["recognizerDisagreementCount"],
        default=None,
    )
    return {
        "schemaVersion": "ocr-ho-v2-018p-recognizer-token-attribution/1.0.0",
        "taskId": "OCR-HO-V2-018P",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_RECOGNIZER_TOKEN_ATTRIBUTION_ONLY",
        },
        "sourceDigests": digests,
        "tokenDefinition": "NFC-normalized whitespace-delimited tokens; no model token IDs",
        "attribution": {
            "AUTO_REGION_HIT": hit,
            "AUTO_REGION_MISS": miss,
            "dominantErrorClass": hit["dominantErrorClass"],
            "dominantErrorRate": hit["dominantErrorRate"],
            "dominantFieldByRecognizerDisagreement": dominant_field,
            "parserContaminationSignalCountFrom017K": source_018f[
                "attribution"
            ]["autoRegionHit"]["parserContaminationSignalCountFrom017K"],
        },
        "byField": by_field,
        "byProfile": by_profile,
        "byVariant": by_variant,
        "candidateRule": {
            "name": "RECOGNIZER_TOKEN_COHORT_REVIEW_ONLY",
            "scope": "AUTO_REGION_HIT",
            "trigger": "RECOGNIZER_DISAGREEMENT_DOMINANT",
            "threshold": 0.5,
            "observedRate": hit["dominantErrorRate"],
            "selectionEligible": False,
            "counterfactualAuthorized": False,
            "runtimeChangeAuthorized": False,
        },
        "decision": {
            "status": "RECOGNIZER_TOKEN_ATTRIBUTION_HOLD",
            "selectedLayer": "RECOGNIZER_TOKEN_ALIGNMENT",
            "dominantClass": hit["dominantErrorClass"],
            "counterfactualAuthorized": False,
            "selectorChanged": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "Recognizer disagreement dominates AUTO_REGION_HIT attribution, but "
                "the evidence does not establish a safe selector, model or legal-value "
                "change. Keep this diagnostic-only and manual-review-only."
            ),
            "nextTask": "OCR-HO-V2-018Q",
            "nextAction": (
                "Review the aggregate cohort evidence and choose one bounded recognizer "
                "or token-alignment sub-layer; do not reopen selector counterfactuals."
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
    parser.add_argument("--artifact-018o", type=Path, required=True)
    parser.add_argument("--artifact-018f", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018o = load(args.artifact_018o)
    source_018f = load(args.artifact_018f)
    validate_018o(source_018o)
    validate_018f(source_018f)
    report = review(
        source_018o,
        source_018f,
        {
            "artifact018oSha256": sha256(args.artifact_018o),
            "artifact018fSha256": sha256(args.artifact_018f),
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
                "dominantClass": report["decision"]["dominantClass"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
