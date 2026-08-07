#!/usr/bin/env python3
"""Aggregate-only review of OCR-HO-V2-017K evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DOMINANCE_THRESHOLD = 0.5
NEXT_TASK = "OCR-HO-V2-017M"
NEXT_DIAGNOSTIC = "LINE_TOKEN_COHORT_SEPARATION"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(source: dict[str, Any]) -> None:
    required = {
        "schemaVersion": "ocr-ho-v2-017k-line-token-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-017K",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
    }
    if any(source.get(key) != value for key, value in required.items()):
        raise SystemExit("017K source scope/schema mismatch")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit("017K must be aggregate-only with prediction sealed")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit("017K must not use Ground Truth at selection")


def dominant_classes(source: dict[str, Any]) -> list[dict[str, Any]]:
    aggregate = source["aggregate"]
    counts = aggregate["classCounts"]
    eligible_failures = int(aggregate["eligibleFailureCount"])
    rows = [
        {
            "class": name,
            "count": int(count),
            "rate": round(int(count) / max(1, eligible_failures), 6),
        }
        for name, count in counts.items()
        if name != "UNCLASSIFIED" and int(count) > 0
    ]
    return sorted(rows, key=lambda row: (-row["count"], row["class"]))


def review(source: dict[str, Any], source_digest: str) -> dict[str, Any]:
    classes = dominant_classes(source)
    aggregate = source["aggregate"]
    threshold_hits = [row for row in classes if row["rate"] >= DOMINANCE_THRESHOLD]
    if threshold_hits:
        raise SystemExit("017K has a dominant class; 017L must not select a new layer")

    return {
        "schemaVersion": "ocr-ho-v2-017l-next-diagnostic-review/1.0.0",
        "taskId": "OCR-HO-V2-017L",
        "candidateVersion": source["candidateVersion"],
        "baselineVersion": source["baselineVersion"],
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "protocol": "AGGREGATE_EVIDENCE_REVIEW_ONLY",
        "sourceDigests": {"artifact017k": source_digest},
        "evidence": {
            "aggregate": {
                "groups": aggregate["groups"],
                "eligibleLineTokenGroups": aggregate["eligibleLineTokenGroups"],
                "eligibleFailureCount": aggregate["eligibleFailureCount"],
                "classCounts": aggregate["classCounts"],
                "dominantCategory": aggregate["dominantCategory"],
                "dominantCategoryRate": aggregate["dominantCategoryRate"],
            },
            "automaticRegion": source["automaticRegion"],
            "rankedClasses": classes,
            "dominanceRule": {
                "threshold": DOMINANCE_THRESHOLD,
                "thresholdClassCount": len(threshold_hits),
                "dominantClassFound": False,
            },
            "byField": source["byField"],
        },
        "selectedNextDiagnostic": {
            "taskId": NEXT_TASK,
            "name": NEXT_DIAGNOSTIC,
            "status": "PROPOSED_NOT_AUTHORIZED",
            "purpose": (
                "Separate automatic line-id/region misses from oracle token and recognizer "
                "disagreement by field, profile and variant cohort."
            ),
            "protocolGate": "AUTO_DETECTOR",
            "protocolDiagnostic": "ORACLE_LINE_TOKEN_ATTRIBUTION_ONLY",
            "aggregateOnly": True,
            "runtimeChange": False,
            "selectorChange": False,
            "counterfactualAuthorized": False,
            "heldoutOrEvaluateOnce": False,
            "acceptanceCriteria": [
                "Emit aggregate cohort counts without raw OCR or field values",
                "Keep automatic mapping separate from oracle attribution",
                "Do not modify selector, parser, recognizer, normalization or runtime",
                "Keep all CCCD fields MANUAL_REVIEW and gates HOLD",
            ],
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
            "status": "NEXT_DIAGNOSTIC_PROPOSED_HOLD",
            "reason": (
                "No 017K error class reaches the 50% dominance threshold; the two largest "
                "classes must be separated before any selector or runtime consideration."
            ),
            "nextAction": (
                "Obtain explicit approval for 017M cohort separation; do not run a selector "
                "counterfactual or development replay in 017L."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-017k", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.artifact_017k)
    validate_source(source)
    report = review(source, sha256(args.artifact_017k))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "nextTask": NEXT_TASK,
                "counterfactualAuthorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
