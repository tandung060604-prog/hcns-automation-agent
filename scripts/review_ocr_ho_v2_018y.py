#!/usr/bin/env python3
"""Review class distribution and select at most one bounded non-selector diagnostic."""

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
AUTH_SCHEMA = "ocr-ho-v2-018y-class-distribution-review-authorization-record/1.0.0"
PROHIBITED_AUTH_KEYS = (
    "selectorChangeAuthorized",
    "counterfactualAuthorized",
    "developmentReplayAuthorized",
    "heldoutEvaluationAuthorized",
    "evaluateOnceAuthorized",
    "primaryRuntimeChangeAuthorized",
    "productionPromotionAllowed",
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_authorization(record: dict[str, Any] | None, manifest_digest: str) -> None:
    if record is None:
        raise SystemExit("018Y explicit sealed-manifest authorization required")
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != AUTH_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-018Y"
        or record.get("datasetFamily") != SCOPE["datasetFamily"]
        or record.get("datasetId") != SCOPE["datasetId"]
        or record.get("candidateVersion") != SCOPE["candidateVersion"]
        or record.get("baselineVersion") != SCOPE["baselineVersion"]
        or record.get("containsRawPII") is not False
        or str(record.get("sealedManifestSha256") or "").casefold()
        != manifest_digest.casefold()
        or approval.get("approved") is not True
        or approval.get("approverRole") != "OCR_REVIEW_OWNER"
        or approval.get("localOnly") is not True
        or approval.get("aggregateClassDistributionReviewAuthorized") is not True
    ):
        raise SystemExit("018Y authorization record invalid")
    for key in PROHIBITED_AUTH_KEYS:
        if approval.get(key) is not False:
            raise SystemExit(f"018Y prohibited authorization is not false: {key}")


def validate_018x(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018x-sealed-joint-table-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018X"
    ):
        raise SystemExit("018X source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018X scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018X must remain aggregate-only")
    review = source.get("review", {})
    if (
        review.get("combinationCount") != 16
        or review.get("evaluatedDocumentsPerCombination") != 15
        or review.get("totalProfileVariantDocumentGroups") != 240
        or review.get("rawValuesReviewed") is not False
    ):
        raise SystemExit("018X table scope mismatch")
    classes = review.get("classTotals", {})
    if any(name not in classes for name in ERROR_CLASSES):
        raise SystemExit("018X class schema mismatch")
    if classes.get("RECOGNIZER_DISAGREEMENT") != 116 or classes.get("LINE_ID_MISS") != 81:
        raise SystemExit("018X class distribution mismatch")
    decision = source.get("decision", {})
    if (
        decision.get("profileVariantWinner") is not None
        or decision.get("selectionEligible") is not False
        or decision.get("selectorChanged") is not False
        or decision.get("counterfactualAuthorized") is not False
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
    ):
        raise SystemExit("018X selector boundary mismatch")


def validate_018w(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018w-sealed-joint-residence-profile-variant-error-class-extractor/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018W"
    ):
        raise SystemExit("018W source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018W scope mismatch: {key}")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit("018W must remain aggregate-only")
    rows = source.get("jointEvidence", {}).get("rows", [])
    if len(rows) != 16 or any(row.get("evaluatedDocuments") != 15 for row in rows):
        raise SystemExit("018W row coverage mismatch")
    if any("value" in row or "text" in row for row in rows):
        raise SystemExit("018W raw value field emitted")
    if source.get("decision", {}).get("profileVariantWinner") is not None:
        raise SystemExit("018W winner must remain null")


def review(
    source_018x: dict[str, Any], source_018w: dict[str, Any], digests: dict[str, str]
) -> dict[str, Any]:
    class_totals = source_018x["review"]["classTotals"]
    total_groups = source_018x["review"]["totalProfileVariantDocumentGroups"]
    rows = source_018w["jointEvidence"]["rows"]
    line_id_rows = sum(1 for row in rows if row["classCounts"]["LINE_ID_MISS"] > 0)
    recognizer_share = class_totals["RECOGNIZER_DISAGREEMENT"] / total_groups
    line_id_share = class_totals["LINE_ID_MISS"] / total_groups
    selected = "RESIDENCE_LINE_ID_MISS_BOUNDARY_ATTRIBUTION"
    return {
        "schemaVersion": "ocr-ho-v2-018y-class-distribution-bounded-diagnostic-review/1.0.0",
        "taskId": "OCR-HO-V2-018Y",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "SEALED_CLASS_DISTRIBUTION_BOUNDED_DIAGNOSTIC_SELECTION_ONLY",
        },
        "sourceDigests": digests,
        "distribution": {
            "field": "placeOfResidence",
            "totalProfileVariantDocumentGroups": total_groups,
            "classTotals": {name: class_totals[name] for name in ERROR_CLASSES},
            "recognizerDisagreementShare": round(recognizer_share, 6),
            "lineIdMissShare": round(line_id_share, 6),
            "lineIdMissRows": line_id_rows,
            "rowCount": len(rows),
            "global50PercentThresholdReached": recognizer_share >= 0.5
            or line_id_share >= 0.5,
        },
        "selectionBasis": {
            "selectedDiagnostic": selected,
            "reason": (
                "Recognizer disagreement is the largest class but was already bounded "
                "in 018U. LINE_ID_MISS is the largest uncovered class (`81/240`) and "
                "appears in all 16 profile×variant rows, so the next diagnostic is a "
                "single residence line-ID boundary attribution review. This is not a "
                "profile/variant selector or runtime patch."
            ),
            "previouslyBoundedDiagnostic": "RESIDENCE_RECOGNIZER_ERROR_CLASS_ATTRIBUTION",
            "selectionEligible": False,
        },
        "decision": {
            "status": "BOUNDED_NON_SELECTOR_DIAGNOSTIC_SELECTED_HOLD",
            "selectedDiagnostic": selected,
            "candidateRule": "RESIDENCE_LINE_ID_MISS_BOUNDARY_ATTRIBUTION_ONLY",
            "profileVariantWinner": None,
            "selectionEligible": False,
            "profileSelectorAuthorized": False,
            "variantSelectorAuthorized": False,
            "selectorPathOpen": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "No global class reaches the 50% threshold; the selected line-ID cohort "
                "is bounded for attribution only because it is the largest uncovered "
                "class and spans every joint row."
            ),
            "nextTask": "OCR-HO-V2-018Z",
            "nextAction": (
                "Run one aggregate-only residence line-ID boundary attribution review; "
                "do not change selector, runtime or replay."
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
            "source018xReviewed": True,
            "source018wJointRowsReviewed": True,
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
    parser.add_argument("--artifact-018x", type=Path, required=True)
    parser.add_argument("--artifact-018w", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--sealed-manifest-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_x = load(args.artifact_018x)
    source_w = load(args.artifact_018w)
    authorization = load(args.authorization_record)
    validate_018x(source_x)
    validate_018w(source_w)
    validate_authorization(authorization, args.sealed_manifest_digest)
    report = review(
        source_x,
        source_w,
        {
            "artifact018xSha256": sha256(args.artifact_018x),
            "artifact018wSha256": sha256(args.artifact_018w),
            "sealedManifestDigest": args.sealed_manifest_digest,
            "authorizationRecordSha256": sha256(args.authorization_record),
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
