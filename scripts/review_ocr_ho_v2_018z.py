#!/usr/bin/env python3
"""Aggregate-only residence line-ID boundary attribution for OCR-HO-V2-018Z."""

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
FIELD = "placeOfResidence"
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
AUTH_SCHEMA = "ocr-ho-v2-018z-residence-line-id-boundary-authorization-record/1.0.0"
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


def validate_scope(source: dict[str, Any], schema: str, task_id: str) -> None:
    task_matches = source.get("taskId") == task_id or (
        task_id == "OCR-HO-V2-017H" and source.get("taskId") is None
    )
    if source.get("schemaVersion") != schema or not task_matches:
        raise SystemExit(f"{task_id} source schema mismatch")
    for key, expected in SCOPE.items():
        actual = source.get(key)
        if key == "diagnosticFieldCount" and task_id == "OCR-HO-V2-017H":
            actual = source.get("diagnosticFieldCount", source.get("roiDiagnosticFieldCount"))
        if actual != expected:
            raise SystemExit(f"{task_id} source scope mismatch: {key}")
    if source.get("containsRawPII") is not False:
        raise SystemExit(f"{task_id} must be aggregate-only")
    if source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} prediction must remain sealed")


def validate_sources(
    source_018y: dict[str, Any],
    source_018w: dict[str, Any],
    source_017h: dict[str, Any],
    source_017p: dict[str, Any],
) -> None:
    validate_scope(
        source_018y,
        "ocr-ho-v2-018y-class-distribution-bounded-diagnostic-review/1.0.0",
        "OCR-HO-V2-018Y",
    )
    validate_scope(
        source_018w,
        "ocr-ho-v2-018w-sealed-joint-residence-profile-variant-error-class-extractor/1.0.0",
        "OCR-HO-V2-018W",
    )
    validate_scope(
        source_017h,
        "ocr-ho-v2-017h-roi-boundary-diagnostic/1.0.0",
        "OCR-HO-V2-017H",
    )
    validate_scope(
        source_017p,
        "ocr-ho-v2-017p-residence-geometry-segmentation-boundary-review/1.0.0",
        "OCR-HO-V2-017P",
    )
    if (
        source_018y["decision"]["selectedDiagnostic"]
        != "RESIDENCE_LINE_ID_MISS_BOUNDARY_ATTRIBUTION"
    ):
        raise SystemExit("018Y must select residence line-ID boundary attribution")
    if source_018y["distribution"]["classTotals"]["LINE_ID_MISS"] != 81:
        raise SystemExit("018Y line-ID miss baseline mismatch")
    rows = source_018w["jointEvidence"]["rows"]
    if len(rows) != 16 or any(row.get("evaluatedDocuments") != 15 for row in rows):
        raise SystemExit("018W joint row coverage mismatch")
    if any("value" in row or "text" in row for row in rows):
        raise SystemExit("018W emitted a raw value")
    residence = source_017h["automaticDetector"]["byField"][FIELD]
    if residence.get("boundaryMiss") != 5 or residence.get("autoHit") != 10:
        raise SystemExit("017H residence boundary scope mismatch")
    if source_017p["decision"].get("roiPatchAuthorized") is not False:
        raise SystemExit("017P patch boundary must remain closed")


def validate_authorization(record: dict[str, Any] | None, manifest_digest: str) -> None:
    if record is None:
        raise SystemExit("018Z explicit sealed-manifest authorization required")
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != AUTH_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-018Z"
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
        or approval.get("aggregateResidenceBoundaryAttributionAuthorized") is not True
    ):
        raise SystemExit("018Z authorization record invalid")
    for key in PROHIBITED_AUTH_KEYS:
        if approval.get(key) is not False:
            raise SystemExit(f"018Z prohibited authorization is not false: {key}")


def summarize_residence(source_017h: dict[str, Any]) -> dict[str, Any]:
    entries = [
        entry
        for entry in source_017h["missDetailsAggregateOnly"]
        if entry.get("field") == FIELD
    ]
    counts = Counter(str(entry.get("category") or "unclassified") for entry in entries)
    ranked = sorted(
        ({"category": name, "count": counts.get(name, 0)} for name in BOUNDARY_CLASSES),
        key=lambda item: (-item["count"], item["category"]),
    )
    dominant = ranked[0]
    missing = sum(int(entry.get("missingExpectedLineCount", 0)) for entry in entries)
    selected = sum(int(entry.get("selectedLineCount", 0)) for entry in entries)
    line_sides = source_017h["automaticDetector"]["byField"][FIELD].get("lineSideCounts", {})
    return {
        "boundaryMissCases": len(entries),
        "categoryCounts": {name: counts.get(name, 0) for name in BOUNDARY_CLASSES},
        "rankedCategories": ranked,
        "dominantCategory": dominant["category"],
        "dominantCategoryRate": round(dominant["count"] / max(1, len(entries)), 6),
        "lineSideCounts": {str(name): int(value) for name, value in line_sides.items()},
        "missingExpectedLineCount": missing,
        "selectedLineCount": selected,
        "lineRetentionRate": round(selected / max(1, missing + selected), 6),
    }


def review(
    source_018y: dict[str, Any],
    source_018w: dict[str, Any],
    source_017h: dict[str, Any],
    source_017p: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    residence = summarize_residence(source_017h)
    geometry = source_017p["evidence"]["bottomBoundaryCases"]
    global_boundary = source_017p["evidence"]["priorGlobalBoundaryContext"]
    return {
        "schemaVersion": "ocr-ho-v2-018z-residence-line-id-boundary-attribution/1.0.0",
        "taskId": "OCR-HO-V2-018Z",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "RESIDENCE_LINE_ID_BOUNDARY_ATTRIBUTION_ONLY",
        },
        "sourceDigests": digests,
        "lineage": {
            "selectedBy018Y": source_018y["decision"]["selectedDiagnostic"],
            "jointProfileVariantRows": len(source_018w["jointEvidence"]["rows"]),
            "profileVariantLineIdMissGroups": source_018y["distribution"]["classTotals"][
                "LINE_ID_MISS"
            ],
            "boundaryEvidenceSource": "OCR-HO-V2-017H",
            "geometryCorroborationSource": "OCR-HO-V2-017P",
            "profileVariantBoundaryCrossTabAvailable": False,
        },
        "attribution": {
            "field": FIELD,
            "residenceBoundary": residence,
            "profileVariantLineIdMissGroups": source_018y["distribution"]["classTotals"][
                "LINE_ID_MISS"
            ],
            "profileVariantRows": source_018y["distribution"]["lineIdMissRows"],
            "crossTabAvailable": False,
            "interpretation": (
                "Boundary evidence attributes the five residence boundary cases, while "
                "the 81 profile/variant line-ID miss groups remain a separate aggregate "
                "cohort; no unsupported one-to-one mapping is inferred."
            ),
        },
        "geometryCorroboration": {
            "bottomBoundaryCaseCount": geometry["caseCount"],
            "bottomOverflowCaseCount": geometry["bottomOverflowCaseCount"],
            "bottomOverflowCaseRate": geometry["bottomOverflowCaseRate"],
            "sealedLineIdOverlapRate": geometry["sealedLineIdOverlapRate"],
            "regionSourceCounts": geometry["regionSourceCounts"],
            "globalDominantBoundaryCategory": global_boundary["dominantCategory"],
            "globalDominantBoundaryRate": global_boundary["dominantCategoryRate"],
            "globalPatchThresholdReached": global_boundary["meets50PercentThreshold"],
        },
        "candidateRule": {
            "name": "RESIDENCE_LINE_ID_BOUNDARY_ATTRIBUTION_ONLY",
            "field": FIELD,
            "dominantBoundaryCategory": residence["dominantCategory"],
            "dominantBoundaryRate": residence["dominantCategoryRate"],
            "status": "CANDIDATE_ONLY_NO_RUNTIME_PATCH",
            "patchAuthorized": False,
            "counterfactualAuthorized": False,
            "selectionEligible": False,
        },
        "decision": {
            "status": "RESIDENCE_LINE_ID_BOUNDARY_ATTRIBUTION_HOLD",
            "selectedBoundaryCategory": residence["dominantCategory"],
            "profileVariantWinner": None,
            "selectionEligible": False,
            "selectorChanged": False,
            "runtimeChanged": False,
            "patchAuthorized": False,
            "counterfactualAuthorized": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "Residence bottom-boundary is the dominant field-specific category at "
                "3/5, but the global boundary rate is below 50% and the profile/variant "
                "line-ID cohort has no boundary cross-tab; attribution remains HOLD."
            ),
            "nextTask": "OCR-HO-V2-019A",
            "nextAction": (
                "Review the bounded residence boundary attribution; do not patch, select "
                "a profile/variant, replay or promote."
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
    parser.add_argument("--artifact-018y", type=Path, required=True)
    parser.add_argument("--artifact-018w", type=Path, required=True)
    parser.add_argument("--artifact-017h", type=Path, required=True)
    parser.add_argument("--artifact-017p", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--sealed-manifest-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018y = load(args.artifact_018y)
    source_018w = load(args.artifact_018w)
    source_017h = load(args.artifact_017h)
    source_017p = load(args.artifact_017p)
    authorization = load(args.authorization_record)
    validate_sources(source_018y, source_018w, source_017h, source_017p)
    validate_authorization(authorization, args.sealed_manifest_digest)
    paths = {
        "artifact018ySha256": args.artifact_018y,
        "artifact018wSha256": args.artifact_018w,
        "artifact017hSha256": args.artifact_017h,
        "artifact017pSha256": args.artifact_017p,
        "authorizationRecordSha256": args.authorization_record,
    }
    report = review(
        source_018y,
        source_018w,
        source_017h,
        source_017p,
        {
            **{name: sha256(path) for name, path in paths.items()},
            "sealedManifestDigest": args.sealed_manifest_digest,
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
                "selectedBoundaryCategory": report["decision"]["selectedBoundaryCategory"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
