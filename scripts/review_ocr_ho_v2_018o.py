#!/usr/bin/env python3
"""Select one bounded non-selector OCR-HO-V2 layer from sealed evidence."""

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


def validate_018n(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018n-selector-path-closure-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018N"
    ):
        raise SystemExit("018N source schema mismatch")
    validate_scope(source, "018N")
    if source.get("decision", {}).get("selectorPathOpen") is not False:
        raise SystemExit("018N selector path must be closed")
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
        raise SystemExit("018N gate invariants mismatch")


def validate_018e(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018e-boundary-reconciliation/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018E"
    ):
        raise SystemExit("018E source schema mismatch")
    validate_scope(source, "018E")
    protocol = source.get("protocol", {})
    if (
        protocol.get("gate") != "AUTO_DETECTOR"
        or protocol.get("diagnostic") != "AGGREGATE_BOUNDARY_RECONCILIATION_ONLY"
    ):
        raise SystemExit("018E protocol mismatch")
    aggregate = source.get("reconciliation", {}).get("automaticBoundary", {}).get(
        "aggregate", {}
    )
    if (
        aggregate.get("evaluated") != 45
        or aggregate.get("autoHit") != 27
        or aggregate.get("boundaryMiss") != 18
        or aggregate.get("detectorMiss") != 0
        or aggregate.get("cropMiss") != 0
        or aggregate.get("meets50PercentThreshold") is not False
    ):
        raise SystemExit("018E detector/crop evidence mismatch")
    gates = source.get("gates", {})
    if (
        gates.get("schemaErrors") != 0
        or gates.get("sensitiveFalseAcceptance") != 0
        or gates.get("acceptedCoverage") != 0
        or gates.get("manualReviewOnly") is not True
        or gates.get("productionPromotionAllowed") is not False
    ):
        raise SystemExit("018E gate invariants mismatch")


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
    attribution = source.get("attribution", {})
    miss = attribution.get("autoRegionMiss", {})
    hit = attribution.get("autoRegionHit", {})
    if (
        miss.get("lineIdMissCount") != 245
        or miss.get("errorGroupCount") != 245
        or hit.get("errorGroupCount") != 375
        or hit.get("recognizerDisagreementCount") != 291
        or hit.get("recognizerDisagreementRate") != 0.776
        or hit.get("lineOrderMismatchCount") != 72
        or hit.get("tokenMismatchCount") != 11
        or hit.get("recognizerDominantAttribution") is not True
    ):
        raise SystemExit("018F recognizer/token evidence mismatch")
    decision = source.get("decision", {})
    if (
        decision.get("selectedLayer") != "RECOGNIZER_TOKEN_ALIGNMENT"
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
        or decision.get("patchAuthorized") is not False
        or decision.get("counterfactualAuthorized") is not False
    ):
        raise SystemExit("018F must remain attribution-only")


def review(
    source_018n: dict[str, Any],
    source_018e: dict[str, Any],
    source_018f: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    boundary = source_018e["reconciliation"]["automaticBoundary"]["aggregate"]
    hit = source_018f["attribution"]["autoRegionHit"]
    selected_layer = "RECOGNIZER_TOKEN_ALIGNMENT"
    return {
        "schemaVersion": "ocr-ho-v2-018o-layer-selection-review/1.0.0",
        "taskId": "OCR-HO-V2-018O",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_LAYER_SELECTION_REVIEW_ONLY",
        },
        "sourceDigests": digests,
        "evidence": {
            "detectorCrop": {
                "evaluated": boundary["evaluated"],
                "autoHit": boundary["autoHit"],
                "boundaryMiss": boundary["boundaryMiss"],
                "detectorMiss": boundary["detectorMiss"],
                "cropMiss": boundary["cropMiss"],
                "dominantCategory": boundary["dominantCategory"],
                "dominantCategoryCount": boundary["categoryCounts"][boundary["dominantCategory"]],
                "dominantCategoryRate": boundary["dominantCategoryRate"],
                "meets50PercentThreshold": boundary["meets50PercentThreshold"],
            },
            "recognizerToken": {
                "autoRegionHitErrorGroups": hit["errorGroupCount"],
                "recognizerDisagreementCount": hit["recognizerDisagreementCount"],
                "recognizerDisagreementRate": hit["recognizerDisagreementRate"],
                "lineOrderMismatchCount": hit["lineOrderMismatchCount"],
                "tokenMismatchCount": hit["tokenMismatchCount"],
                "recognizerDominantAttribution": hit["recognizerDominantAttribution"],
            },
            "selectionRule": {
                "selectedLayer": selected_layer,
                "reason": (
                    "Recognizer disagreement is the dominant eligible AUTO_REGION_HIT "
                    "error class; detector/crop has no direct miss and no global 50% "
                    "boundary category."
                ),
                "selectorEvidenceNotUsedForSelection": True,
            },
        },
        "decision": {
            "status": "NON_SELECTOR_LAYER_SELECTED_HOLD",
            "selectedLayer": selected_layer,
            "selectorPathOpen": False,
            "patchAuthorized": False,
            "replayAuthorized": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "Choose recognizer/token alignment as the single next diagnostic layer; "
                "do not combine it with detector/crop, parser, normalization or selector "
                "changes."
            ),
            "nextTask": "OCR-HO-V2-018P",
            "nextAction": (
                "Run one aggregate-only recognizer/token alignment attribution review "
                "using sealed evidence; no OCR rerun, replay or selector counterfactual."
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
    parser.add_argument("--artifact-018n", type=Path, required=True)
    parser.add_argument("--artifact-018e", type=Path, required=True)
    parser.add_argument("--artifact-018f", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018n = load(args.artifact_018n)
    source_018e = load(args.artifact_018e)
    source_018f = load(args.artifact_018f)
    validate_018n(source_018n)
    validate_018e(source_018e)
    validate_018f(source_018f)
    report = review(
        source_018n,
        source_018e,
        source_018f,
        {
            "artifact018nSha256": sha256(args.artifact_018n),
            "artifact018eSha256": sha256(args.artifact_018e),
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
                "selectedLayer": report["decision"]["selectedLayer"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
