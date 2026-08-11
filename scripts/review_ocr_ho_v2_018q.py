#!/usr/bin/env python3
"""Select one bounded recognizer/token sub-layer from OCR-HO-V2-018P."""

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
    protocol = source.get("protocol", {})
    if (
        protocol.get("gate") != "AUTO_DETECTOR"
        or protocol.get("diagnostic") != "AGGREGATE_RECOGNIZER_TOKEN_ATTRIBUTION_ONLY"
    ):
        raise SystemExit("018P protocol mismatch")
    if source.get("tokenDefinition") != (
        "NFC-normalized whitespace-delimited tokens; no model token IDs"
    ):
        raise SystemExit("018P token definition mismatch")
    decision = source.get("decision", {})
    gates = source.get("gates", {})
    if (
        decision.get("selectedLayer") != "RECOGNIZER_TOKEN_ALIGNMENT"
        or decision.get("counterfactualAuthorized") is not False
        or decision.get("selectorChanged") is not False
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
        or gates.get("developmentRegressionGate") != "HOLD"
        or gates.get("heldoutReadinessGate") != "HOLD"
        or gates.get("schemaErrors") != 0
        or gates.get("sensitiveFalseAcceptance") != 0
        or gates.get("acceptedCoverage") != 0
        or gates.get("manualReviewOnly") is not True
        or gates.get("productionPromotionAllowed") is not False
    ):
        raise SystemExit("018P attribution-only invariants mismatch")
    for field in ("fullName", "placeOfOrigin", "placeOfResidence"):
        if field not in source.get("byField", {}):
            raise SystemExit(f"018P field cohort missing: {field}")


def field_summary(value: dict[str, Any]) -> dict[str, Any]:
    classes = value.get("classCounts", {})
    return {
        "groups": value["groups"],
        "eligibleLineTokenGroups": value["eligibleLineTokenGroups"],
        "errorGroupCount": value["errorGroupCount"],
        "recognizerDisagreementCount": classes["RECOGNIZER_DISAGREEMENT"],
        "lineOrderMismatchCount": classes["LINE_ORDER_MISMATCH"],
        "tokenMismatchCount": value["tokenMismatchCount"],
        "dominantErrorClass": value["dominantErrorClass"],
        "dominantErrorRate": value["dominantErrorRate"],
    }


def review(source: dict[str, Any], source_digest: str) -> dict[str, Any]:
    fields = {
        name: field_summary(source["byField"][name])
        for name in ("fullName", "placeOfOrigin", "placeOfResidence")
    }
    residence = fields["placeOfResidence"]
    comparison = {
        "recognizerDisagreement": residence["recognizerDisagreementCount"],
        "lineOrderMismatch": residence["lineOrderMismatchCount"],
        "tokenMismatch": residence["tokenMismatchCount"],
    }
    return {
        "schemaVersion": "ocr-ho-v2-018q-recognizer-sublayer-selection/1.0.0",
        "taskId": "OCR-HO-V2-018Q",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_RECOGNIZER_SUBLAYER_SELECTION_ONLY",
        },
        "sourceDigests": {"artifact018pSha256": source_digest},
        "evidence": {
            "fieldCohorts": fields,
            "residenceSubLayerComparison": comparison,
            "selectionBasis": {
                "selectedField": "placeOfResidence",
                "selectedCohort": "AUTO_REGION_HIT",
                "selectedClass": "RECOGNIZER_DISAGREEMENT",
                "selectedSubLayer": "PLACE_OF_RESIDENCE_RECOGNIZER_DISAGREEMENT",
                "reason": (
                    "Residence has the highest recognizer disagreement count among the "
                    "three target fields; within residence it is larger than line-order "
                    "and token mismatch."
                ),
                "profileOrVariantSelectorUsed": False,
            },
        },
        "decision": {
            "status": "RECOGNIZER_SUBLAYER_SELECTED_HOLD",
            "selectedLayer": "RECOGNIZER_TOKEN_ALIGNMENT",
            "selectedSubLayer": "PLACE_OF_RESIDENCE_RECOGNIZER_DISAGREEMENT",
            "selectorPathOpen": False,
            "counterfactualAuthorized": False,
            "profileSelectorAuthorized": False,
            "variantSelectorAuthorized": False,
            "lineOrderChangeAuthorized": False,
            "tokenAlignmentChangeAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "Bound the next diagnostic to residence recognizer disagreement; do not "
                "combine profile selection, variant selection, reading order, token "
                "alignment, parser or normalization changes."
            ),
            "nextTask": "OCR-HO-V2-018R",
            "nextAction": (
                "Run one aggregate-only residence recognizer-disagreement cohort review "
                "across existing profiles/variants; no selector or OCR replay."
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
    parser.add_argument("--artifact-018p", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.artifact_018p)
    validate_source(source)
    report = review(source, sha256(args.artifact_018p))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "selectedSubLayer": report["decision"]["selectedSubLayer"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
