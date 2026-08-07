#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-018F recognizer/token attribution review."""

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
COHORTS = ("AUTO_REGION_HIT", "AUTO_REGION_MISS")
ERROR_CLASSES = (
    "LINE_ID_MISS",
    "LINE_ORDER_MISMATCH",
    "TOKEN_OMISSION",
    "TOKEN_EXTRA",
    "TOKEN_SWAP",
    "DUPLICATE_LINE",
    "RECOGNIZER_DISAGREEMENT",
)
TOKEN_CLASSES = ("TOKEN_OMISSION", "TOKEN_EXTRA", "TOKEN_SWAP", "DUPLICATE_LINE")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_scope(source: dict[str, Any], schema: str, task_id: str) -> None:
    if source.get("schemaVersion") != schema or source.get("taskId") != task_id:
        raise SystemExit(f"{task_id} source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{task_id} source scope mismatch: {key}")
    if source.get("containsRawPII") is not False:
        raise SystemExit(f"{task_id} must be aggregate-only")
    if source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} prediction must remain sealed")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit(f"{task_id} must not use Ground Truth at selection")


def validate_lineage(
    source_017k: dict[str, Any],
    source_017m: dict[str, Any],
    source_018e: dict[str, Any],
) -> None:
    validate_scope(
        source_017k,
        "ocr-ho-v2-017k-line-token-diagnostic/1.0.0",
        "OCR-HO-V2-017K",
    )
    validate_scope(
        source_017m,
        "ocr-ho-v2-017m-line-token-cohort-separation/1.0.0",
        "OCR-HO-V2-017M",
    )
    validate_scope(
        source_018e,
        "ocr-ho-v2-018e-boundary-reconciliation/1.0.0",
        "OCR-HO-V2-018E",
    )
    for source in (source_017k, source_017m, source_018e):
        if source.get("protocol", {}).get("gate") != "AUTO_DETECTOR":
            raise SystemExit("AUTO_DETECTOR gate lineage required")
    if source_017m.get("protocol", {}).get("diagnostic") != "ORACLE_LINE_TOKEN_ATTRIBUTION_ONLY":
        raise SystemExit("017M attribution protocol mismatch")
    if source_018e.get("decision", {}).get("status") != "BOUNDARY_RECONCILED_HOLD":
        raise SystemExit("018E must remain boundary-reconciled HOLD")
    if source_018e.get("decision", {}).get("runtimeChanged") is not False:
        raise SystemExit("018E runtime must remain unchanged")
    if source_018e.get("decision", {}).get("replayExecuted") is not False:
        raise SystemExit("018E replay must remain closed")
    if source_018e.get("gates", {}).get("patchAuthorized") is not False:
        raise SystemExit("018E patch must remain unauthorized")


def summarize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    counts = {name: int(bucket.get("classCounts", {}).get(name, 0)) for name in ERROR_CLASSES}
    error_count = sum(counts.values())
    dominant = max(ERROR_CLASSES, key=lambda name: (counts[name], name))
    dominant_count = counts[dominant]
    token_count = sum(counts[name] for name in TOKEN_CLASSES)
    return {
        "groups": int(bucket.get("groups", 0)),
        "eligibleLineTokenGroups": int(bucket.get("eligibleLineTokenGroups", 0)),
        "classCounts": counts,
        "errorGroupCount": error_count,
        "dominantErrorClass": dominant if dominant_count else None,
        "dominantErrorRate": round(dominant_count / max(1, error_count), 6),
        "tokenMismatchCount": token_count,
        "lineOrderMismatchCount": counts["LINE_ORDER_MISMATCH"],
        "recognizerDisagreementCount": counts["RECOGNIZER_DISAGREEMENT"],
    }


def cohort_rows(cohorts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: summarize_bucket(cohorts[name]) for name in COHORTS}


def summarize_dimensions(source_017m: dict[str, Any], dimension: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, cohorts in sorted(source_017m["cohorts"][dimension].items()):
        hit = summarize_bucket(cohorts["AUTO_REGION_HIT"])
        output[name] = {
            "autoRegionHit": hit,
            "autoRegionMiss": summarize_bucket(cohorts["AUTO_REGION_MISS"]),
            "recognizerDisagreementRateAmongHitErrors": round(
                hit["recognizerDisagreementCount"] / max(1, hit["errorGroupCount"]), 6
            ),
        }
    return output


def review(
    source_017k: dict[str, Any],
    source_017m: dict[str, Any],
    source_018e: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    cohorts = cohort_rows(source_017m["cohorts"]["aggregate"])
    hit = cohorts["AUTO_REGION_HIT"]
    miss = cohorts["AUTO_REGION_MISS"]
    token_mismatch = sum(hit["classCounts"][name] for name in TOKEN_CLASSES)
    recognizer_rate = round(
        hit["recognizerDisagreementCount"] / max(1, hit["errorGroupCount"]), 6
    )
    profile_rows = summarize_dimensions(source_017m, "byProfile")
    variant_rows = summarize_dimensions(source_017m, "byVariant")
    recognizer_dominant = recognizer_rate >= 0.5
    return {
        "schemaVersion": "ocr-ho-v2-018f-recognizer-token-attribution/1.0.0",
        "taskId": "OCR-HO-V2-018F",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "ORACLE_LINE_TOKEN_ATTRIBUTION_ONLY",
        },
        "sourceDigests": digests,
        "lineage": {
            "boundaryReconciliationStatus": source_018e["decision"]["status"],
            "automaticRoiReconciled": source_018e["reconciliation"]["roiConsistency"][
                "allFieldsConsistent"
            ],
            "boundaryPatchAuthorized": source_018e["gates"]["patchAuthorized"],
            "replayExecuted": source_018e["decision"]["replayExecuted"],
        },
        "tokenDefinition": "NFC-normalized whitespace-delimited tokens; no model token IDs",
        "cohorts": cohorts,
        "byField": {
            field: summarize_bucket(source_017m["cohorts"]["byField"][field]["AUTO_REGION_HIT"])
            for field in ("fullName", "placeOfOrigin", "placeOfResidence")
        },
        "byProfile": profile_rows,
        "byVariant": variant_rows,
        "attribution": {
            "autoRegionMiss": {
                "lineIdMissCount": miss["classCounts"]["LINE_ID_MISS"],
                "errorGroupCount": miss["errorGroupCount"],
                "lineIdMissRate": round(
                    miss["classCounts"]["LINE_ID_MISS"] / max(1, miss["errorGroupCount"]), 6
                ),
                "interpretation": "Automatic mapping remains a separate detector/crop cohort.",
            },
            "autoRegionHit": {
                "errorGroupCount": hit["errorGroupCount"],
                "recognizerDisagreementCount": hit["recognizerDisagreementCount"],
                "recognizerDisagreementRate": recognizer_rate,
                "lineOrderMismatchCount": hit["lineOrderMismatchCount"],
                "tokenMismatchCount": token_mismatch,
                "parserContaminationSignalCountFrom017K": int(
                    source_017k["aggregate"]["classCounts"]["PARSER_CONTAMINATION"]
                ),
                "recognizerDominantAttribution": recognizer_dominant,
                "interpretation": (
                    "When automatic region mapping hits, recognizer disagreement is the "
                    "largest observed error class; this is attribution, not selector evidence."
                ),
            },
        },
        "candidateRule": {
            "name": "RECOGNIZER_TOKEN_COHORT_REVIEW_ONLY",
            "scope": "AUTO_REGION_HIT",
            "trigger": "RECOGNIZER_DISAGREEMENT_DOMINANT",
            "threshold": 0.5,
            "observedRate": recognizer_rate,
            "selectionEligible": False,
            "counterfactualAuthorized": False,
            "runtimeChangeAuthorized": False,
            "reason": (
                "Profile/variant counts do not establish a safe legal-value selector or "
                "quality improvement."
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
            "status": "RECOGNIZER_TOKEN_ATTRIBUTION_HOLD",
            "selectedLayer": "RECOGNIZER_TOKEN_ALIGNMENT",
            "dominantCohort": "AUTO_REGION_HIT",
            "reason": (
                "After boundary reconciliation, AUTO_REGION_HIT errors contain recognizer "
                "disagreement at 291/375 (77.6%); token omission/extra/swap/duplicate totals "
                f"{token_mismatch} and line-order mismatch is 72. This does not authorize a "
                "profile selector, counterfactual or runtime change."
            ),
            "nextAction": (
                "Keep selector and runtime closed; require a separately approved review if a "
                "profile/variant counterfactual is desired."
            ),
            "runtimeChanged": False,
            "replayExecuted": False,
            "patchAuthorized": False,
            "counterfactualAuthorized": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-017k", type=Path, required=True)
    parser.add_argument("--artifact-017m", type=Path, required=True)
    parser.add_argument("--artifact-018e", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_017k = load(args.artifact_017k)
    source_017m = load(args.artifact_017m)
    source_018e = load(args.artifact_018e)
    validate_lineage(source_017k, source_017m, source_018e)
    report = review(
        source_017k,
        source_017m,
        source_018e,
        {
            "artifact017kSha256": sha256(args.artifact_017k),
            "artifact017mSha256": sha256(args.artifact_017m),
            "artifact018eSha256": sha256(args.artifact_018e),
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
                "recognizerDisagreementRate": report["attribution"]["autoRegionHit"][
                    "recognizerDisagreementRate"
                ],
                "counterfactualAuthorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
