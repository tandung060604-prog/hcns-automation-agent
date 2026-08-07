#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017N automatic line-boundary attribution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
BOUNDARY_CLASSES = (
    "bottom_boundary",
    "line_order",
    "multiple_boundary_sides",
    "top_boundary",
    "left_boundary",
    "expiry_stop",
    "duplicate_line",
    "detector_miss",
    "unclassified",
)
THRESHOLD = 0.5


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_sources(
    source_017h: dict[str, Any], source_017m: dict[str, Any], source_017l: dict[str, Any]
) -> None:
    if (
        source_017h.get("schemaVersion") != "ocr-ho-v2-017h-roi-boundary-diagnostic/1.0.0"
        or source_017h.get("datasetFamily") != "CCCD"
        or source_017h.get("datasetId") != "DATA-HO-014"
        or source_017h.get("documentCount") != 15
        or source_017h.get("evaluatedFieldCount") != 120
        or source_017h.get("roiDiagnosticFieldCount") != 45
    ):
        raise SystemExit("017H source scope/schema mismatch")
    if source_017m.get("taskId") != "OCR-HO-V2-017M":
        raise SystemExit("017M lineage artifact required")
    if source_017l.get("taskId") != "OCR-HO-V2-017L":
        raise SystemExit("017L lineage artifact required")
    for source in (source_017h, source_017m, source_017l):
        if source.get("containsRawPII") is not False:
            raise SystemExit("Lineage artifacts must be aggregate-only")


def ranked_categories(counts: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            {"category": name, "count": int(count)}
            for name, count in counts.items()
            if name in BOUNDARY_CLASSES and int(count) > 0
        ],
        key=lambda row: (-row["count"], row["category"]),
    )


def summarize_field(field_data: dict[str, Any]) -> dict[str, Any]:
    boundary_miss = int(field_data.get("boundaryMiss", 0))
    ranked = ranked_categories(field_data.get("categoryCounts", {}))
    dominant = ranked[0] if ranked else {"category": None, "count": 0}
    return {
        "evaluated": int(field_data.get("evaluated", 0)),
        "autoHit": int(field_data.get("autoHit", 0)),
        "boundaryMiss": boundary_miss,
        "detectorMiss": int(field_data.get("detectorMiss", 0)),
        "cropMiss": int(field_data.get("cropMiss", 0)),
        "categoryCounts": {
            name: int(field_data.get("categoryCounts", {}).get(name, 0))
            for name in BOUNDARY_CLASSES
        },
        "rankedCategories": ranked,
        "dominantCategory": dominant["category"],
        "dominantCategoryRate": round(dominant["count"] / max(1, boundary_miss), 6),
        "meets50PercentThreshold": dominant["count"] / max(1, boundary_miss) >= THRESHOLD,
    }


def review(
    source_017h: dict[str, Any],
    source_017m: dict[str, Any],
    source_017l: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    automatic = source_017h["automaticDetector"]
    aggregate = summarize_field(automatic["aggregate"])
    by_field = {field: summarize_field(automatic["byField"][field]) for field in FIELDS}
    residence = by_field["placeOfResidence"]
    residence_candidate = {
        "field": "placeOfResidence",
        "category": residence["dominantCategory"],
        "count": residence["rankedCategories"][0]["count"] if residence["rankedCategories"] else 0,
        "boundaryMiss": residence["boundaryMiss"],
        "rate": residence["dominantCategoryRate"],
        "meets50PercentThreshold": residence["meets50PercentThreshold"],
    }
    return {
        "schemaVersion": "ocr-ho-v2-017n-auto-line-mapping-boundary-attribution/1.0.0",
        "taskId": "OCR-HO-V2-017N",
        "candidateVersion": source_017h["candidateVersion"],
        "baselineVersion": source_017h["baselineVersion"],
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AUTO_LINE_MAPPING_BOUNDARY_ATTRIBUTION_ONLY",
        },
        "sourceDigests": digests,
        "evidence": {
            "automaticDetectorAggregate": aggregate,
            "automaticDetectorByField": by_field,
            "lineSideCounts": automatic["aggregate"].get("lineSideCounts", {}),
            "cohortCorroboration": {
                "autoRegionMissLineIdMissRate": source_017m["separation"]["autoRegionMiss"][
                    "lineIdMissRate"
                ],
                "autoRegionHitRecognizerDisagreementRate": source_017m["separation"][
                    "autoRegionHit"
                ]["recognizerDisagreementRate"],
            },
        },
        "candidateRule": {
            "globalBoundaryDominantCategory": aggregate["dominantCategory"],
            "globalBoundaryDominantRate": aggregate["dominantCategoryRate"],
            "globalMeets50PercentThreshold": aggregate["meets50PercentThreshold"],
            "residenceFieldCandidate": residence_candidate,
            "status": "CANDIDATE_ONLY_NO_RUNTIME_PATCH",
            "counterfactualAuthorized": False,
        },
        "decision": {
            "status": "BOUNDARY_ATTRIBUTION_HOLD",
            "recommendedNextTask": "OCR-HO-V2-017O",
            "recommendedNextDiagnostic": "RESIDENCE_BOTTOM_BOUNDARY_ATTRIBUTION",
            "reason": (
                "Global bottom-boundary misses are 8/18 = 44.44%, below the patch threshold. "
                "Residence bottom-boundary misses are 3/5 = 60%, so record a residence-only "
                "candidate rule for a separately approved diagnostic; do not patch runtime."
            ),
            "runtimeChanged": False,
            "counterfactualAuthorized": False,
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
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-017h", type=Path, required=True)
    parser.add_argument("--artifact-017m", type=Path, required=True)
    parser.add_argument("--artifact-017l", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_017h = load(args.artifact_017h)
    source_017m = load(args.artifact_017m)
    source_017l = load(args.artifact_017l)
    validate_sources(source_017h, source_017m, source_017l)
    report = review(
        source_017h,
        source_017m,
        source_017l,
        {
            "artifact017h": sha256(args.artifact_017h),
            "artifact017m": sha256(args.artifact_017m),
            "artifact017l": sha256(args.artifact_017l),
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
                "globalDominantRate": report["candidateRule"]["globalBoundaryDominantRate"],
                "residenceCandidateRate": report["candidateRule"]["residenceFieldCandidate"][
                    "rate"
                ],
                "nextTask": "OCR-HO-V2-017O",
                "counterfactualAuthorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
