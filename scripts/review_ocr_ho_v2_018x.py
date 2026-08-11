#!/usr/bin/env python3
"""Review the sealed OCR-HO-V2-018W joint table aggregate-only."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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


def validate_source(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018w-sealed-joint-residence-profile-variant-error-class-extractor/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018W"
    ):
        raise SystemExit("018W source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018W scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018W must remain aggregate-only")
    protocol = source.get("protocol", {})
    if (
        protocol.get("gate") != "AUTO_DETECTOR"
        or protocol.get("diagnostic")
        != "SEALED_JOINT_RESIDENCE_PROFILE_VARIANT_ERROR_CLASS_EXTRACTION_ONLY"
    ):
        raise SystemExit("018W protocol mismatch")
    joint = source.get("jointEvidence", {})
    if (
        joint.get("available") is not True
        or joint.get("combinationCount") != 16
        or joint.get("completeCombinationCount") != 16
        or joint.get("evaluatedDocumentsPerCompleteCombination") != 15
        or joint.get("rawValuesEmitted") is not False
    ):
        raise SystemExit("018W joint evidence mismatch")
    rows = joint.get("rows", [])
    if len(rows) != 16:
        raise SystemExit("018W row count mismatch")
    for row in rows:
        if row.get("evaluatedDocuments") != 15:
            raise SystemExit("018W row evaluation mismatch")
        counts = row.get("classCounts", {})
        if any(name not in counts for name in ERROR_CLASSES):
            raise SystemExit("018W class schema mismatch")
        if sum(counts.values()) != row.get("errorGroupCount"):
            raise SystemExit("018W class total mismatch")
        if "value" in row or "text" in row:
            raise SystemExit("018W raw value field emitted")
    decision = source.get("decision", {})
    if any(
        decision.get(key) is not False
        for key in (
            "selectionEligible",
            "selectorChanged",
            "counterfactualAuthorized",
            "runtimeChanged",
            "replayExecuted",
            "heldoutOpened",
            "promotionAllowed",
        )
    ) or decision.get("profileVariantWinner") is not None:
        raise SystemExit("018W selector boundary mismatch")
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
        raise SystemExit("018W gate mismatch")


def review(source: dict[str, Any], source_digest: str) -> dict[str, Any]:
    rows = source["jointEvidence"]["rows"]
    total_classes = Counter()
    dominant_rows = Counter()
    for row in rows:
        total_classes.update(row["classCounts"])
        dominant_rows[row["dominantErrorClass"]] += 1
    total_groups = sum(row["errorGroupCount"] for row in rows)
    return {
        "schemaVersion": "ocr-ho-v2-018x-sealed-joint-table-review/1.0.0",
        "taskId": "OCR-HO-V2-018X",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "SEALED_JOINT_TABLE_AGGREGATE_REVIEW_ONLY",
        },
        "sourceDigests": {"artifact018wSha256": source_digest},
        "review": {
            "field": "placeOfResidence",
            "combinationCount": len(rows),
            "evaluatedDocumentsPerCombination": 15,
            "totalProfileVariantDocumentGroups": total_groups,
            "classTotals": {name: total_classes.get(name, 0) for name in ERROR_CLASSES},
            "dominantErrorClassByRow": dict(dominant_rows),
            "rowsWithRecognizerDisagreementDominant": dominant_rows.get(
                "RECOGNIZER_DISAGREEMENT", 0
            ),
            "rawValuesReviewed": False,
        },
        "decision": {
            "status": "SEALED_JOINT_TABLE_REVIEW_HOLD",
            "jointEvidenceReviewed": True,
            "profileVariantWinner": None,
            "selectionEligible": False,
            "selectorChanged": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "The 16×15 joint table is complete and aggregate-only. Row dominance "
                "is diagnostic evidence, not a safe profile/variant selector; keep all "
                "promotion and runtime paths closed."
            ),
            "nextTask": "OCR-HO-V2-018Y",
            "nextAction": (
                "Review the aggregate class distribution and choose at most one bounded "
                "non-selector diagnostic; do not run selector or replay."
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
            "source018wSealedJointTable": True,
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
    parser.add_argument("--artifact-018w", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.artifact_018w)
    validate_source(source)
    report = review(source, sha256(args.artifact_018w))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "totalGroups": report["review"]["totalProfileVariantDocumentGroups"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
