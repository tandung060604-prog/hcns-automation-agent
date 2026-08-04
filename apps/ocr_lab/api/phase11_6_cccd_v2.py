"""OCR-HO-V2-006 ROI candidate using the locked Phase 11.6 recognizers.

The candidate narrows the shared sex/nationality row and reuses the existing
label-bounded name/address bands. It is a private development replay only:
target fields remain ``MANUAL_REVIEW`` and the Phase 11.5 baseline protects
fields that do not have independently safe evidence.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import phase11_5_cccd as phase11_5
import phase11_6_cccd as phase11_6
from phase11_5_cccd_v2 import recover_field
from phase11_cccd import FIELD_ORDER

CANDIDATE_VERSION = "11.6.1"
SCHEMA_VERSION = phase11_6.SCHEMA_VERSION
POLICY_ID = "phase11.6-v2-targeted-roi-guarded-recovery"
TARGET_FIELDS = (
    "fullName",
    "sex",
    "nationality",
    "placeOfOrigin",
    "placeOfResidence",
)
PROTECTED_FIELDS = tuple(name for name in FIELD_ORDER if name not in TARGET_FIELDS)
FRONT_FIELD_ROIS = {
    **phase11_6.PHASE11_6_ROIS,
    # The old bands overlapped. These two value windows split the shared row
    # before recognizer crops are generated.
    "sex": (0.43, 0.59, 0.64, 0.71),
    "nationality": (0.64, 0.59, 0.99, 0.71),
}


def build_crop_variants(page_image: Any, bbox: list[int]) -> dict[str, dict[str, Any]]:
    return phase11_5.build_crop_variants(page_image, bbox)


def field_candidate(field_name: str, raw_text: Any) -> str:
    return phase11_6.field_candidate(field_name, raw_text)


def locate_field_regions(
    pages: list[dict[str, Any]],
    page_sizes: list[tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    regions = phase11_6.locate_field_regions(pages, page_sizes)
    if not page_sizes:
        return regions
    width, height = page_sizes[0]
    for field_name in ("sex", "nationality"):
        x0, y0, x1, y1 = FRONT_FIELD_ROIS[field_name]
        regions[field_name] = {
            "pageIndex": 0,
            "bbox": [
                int(width * x0),
                int(height * y0),
                int(width * x1),
                int(height * y1),
            ],
            "normalizedBbox": [x0, y0, x1, y1],
            "regionSource": "phase11_6_v2_split_shared_row",
            "labelMatchScore": 0.0,
            "maxValueLines": 1,
        }
    return regions


def _manual_field(field: dict[str, Any], selection_mode: str) -> dict[str, Any]:
    output = deepcopy(field)
    output.setdefault("value", None)
    output.setdefault("asciiValue", None)
    output.setdefault("confidence", 0.0)
    output.setdefault("errorSignals", ["not_found"] if not output.get("value") else [])
    output.setdefault(
        "evidence",
        {"pageIndex": 0, "bbox": [], "candidates": []},
    )
    output["status"] = "needs_review" if output.get("value") else "not_found"
    output["asciiStatus"] = "needs_review" if output.get("value") else "not_found"
    output["selectionMode"] = selection_mode
    return output


def _candidate_for_field(
    field_name: str,
    candidates: list[dict[str, Any]],
    regions: dict[str, dict[str, Any]],
    fields: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    region = regions.get(field_name, {})
    return phase11_6.select_field_candidate(
        field_name,
        candidates,
        bbox=region.get("bbox"),
        page_index=int(region.get("pageIndex", 0)),
        date_of_birth=(
            fields.get("dateOfBirth", {}).get("value")
            if field_name == "dateOfExpiry"
            else None
        ),
    )


def build_identity_card(
    candidates_by_field: dict[str, list[dict[str, Any]]],
    regions: dict[str, dict[str, Any]],
    *,
    baseline_fields: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    baseline_fields = baseline_fields or {}
    fields: dict[str, dict[str, Any]] = {}
    recovery_counts = {"available": 0, "applied": 0}
    for field_name in FIELD_ORDER:
        candidates = candidates_by_field.get(field_name, [])
        candidate = _candidate_for_field(field_name, candidates, regions, fields)
        baseline = deepcopy(baseline_fields.get(field_name) or {})
        if field_name in TARGET_FIELDS:
            recovery = recover_field(field_name, baseline, candidates)
            shadow = recovery.get("shadowRecovery") or {}
            recovery_counts["available"] += int(bool(shadow.get("candidateAvailable")))
            recovery_counts["applied"] += int(bool(shadow.get("guardedRecoveryApplied")))
            if shadow.get("guardedRecoveryApplied"):
                recovery["selectionMode"] = "phase11_6_single_candidate"
                recovery["evidence"] = candidate.get("evidence", recovery.get("evidence", {}))
                fields[field_name] = _manual_field(
                    recovery,
                    "phase11_6_single_candidate",
                )
                continue
        if baseline.get("value") is not None:
            baseline["phase11_6Candidate"] = candidate
            fields[field_name] = _manual_field(
                baseline,
                "phase11_6_baseline_preserved",
            )
        else:
            fields[field_name] = _manual_field(
                candidate,
                candidate.get("selectionMode", "phase11_6_single_candidate"),
            )
    present = sum(field.get("value") is not None for field in fields.values())
    accepted = sum(field.get("status") == "accepted" for field in fields.values())
    review = sum(field.get("status") == "needs_review" for field in fields.values())
    missing = sum(field.get("status") == "not_found" for field in fields.values())
    return {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": "VIETNAM_CITIZEN_ID_FRONT",
        # Keep the locked Phase 11.6 schema contract; the candidate policy is
        # carried in the summary and phase result metadata.
        "extractionPolicy": phase11_6.POLICY_ID,
        "policyMode": "SHADOW_REVIEW_ONLY",
        "fields": fields,
        "summary": {
            "expectedFieldCount": len(FIELD_ORDER),
            "presentFieldCount": present,
            "acceptedFieldCount": accepted,
            "needsReviewFieldCount": review,
            "notFoundFieldCount": missing,
            "documentCompleteness": round(present / len(FIELD_ORDER), 6),
            "acceptedRate": round(accepted / len(FIELD_ORDER), 6),
            "readyForAutomaticUse": False,
            "candidateVersion": CANDIDATE_VERSION,
            "targetFields": list(TARGET_FIELDS),
            "guardedRecoveryAvailableCount": recovery_counts["available"],
            "guardedRecoveryAppliedCount": recovery_counts["applied"],
        },
    }


business_values = phase11_6.business_values
