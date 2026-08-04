"""OCR-HO-V2-011 deterministic address ROI candidate.

This module is a development-only shadow candidate.  It narrows the two
address bands using the observed label anchors and hard vertical boundaries,
then allows a guarded same-profile Paddle consensus when the crop is clean.
It never reads Ground Truth and it never changes the production Phase 11.5
output: every recovered field remains ``MANUAL_REVIEW``.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any

import phase11_5_cccd as phase11_5
import phase11_6_cccd as phase11_6
import phase11_7_cccd_v2 as phase11_7
import phase11_8_cccd_v2 as phase11_8
from phase11_cccd import FIELD_ORDER, _bounds

CANDIDATE_VERSION = "11.9.1"
SCHEMA_VERSION = phase11_6.SCHEMA_VERSION
POLICY_ID = "phase11.9-v2-deterministic-address-roi"
TARGET_FIELDS = phase11_7.TARGET_FIELDS
PROTECTED_FIELDS = tuple(name for name in FIELD_ORDER if name not in TARGET_FIELDS)

ADDRESS_FALLBACK_ROIS = {
    **phase11_6.PHASE11_6_ROIS,
    "placeOfOrigin": (0.28, 0.60, 0.98, 0.76),
    "placeOfResidence": (0.28, 0.70, 0.98, 0.90),
}

build_crop_variants = phase11_7.build_crop_variants
field_candidate = phase11_8.field_candidate
repair_unicode = phase11_8.repair_unicode


def _fallback_bbox(width: int, height: int, field_name: str) -> list[int]:
    x0, y0, x1, y1 = ADDRESS_FALLBACK_ROIS[field_name]
    return [int(width * x0), int(height * y0), int(width * x1), int(height * y1)]


def _anchor_bbox(anchor: dict[str, Any]) -> tuple[int, int, int, int]:
    return _bounds(anchor["box"])


def _label_x0(anchor: dict[str, Any], width: int) -> int:
    left, _, _, _ = _anchor_bbox(anchor)
    # Keep the bilingual label in the crop so the cleaner can use it as a
    # separator, but remove the broad left margin that admitted expiry text.
    return max(0, min(width - 1, int(left - max(8, width * 0.012))))


def locate_field_regions(
    pages: list[dict[str, Any]],
    page_sizes: list[tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    """Build non-overlapping address ROIs from label geometry.

    The origin crop ends just after the residence label so a wrapped second
    origin line is retained while the residence value is removed by the
    label-aware cleaner.  The residence crop ends shortly after its second
    line and before the expiry block.
    """

    if not page_sizes:
        return {}
    width, height = page_sizes[0]
    regions = phase11_6.locate_field_regions(pages, page_sizes)
    anchors = phase11_6._label_anchors(pages)
    residence = anchors.get("placeOfResidence")
    origin = anchors.get("placeOfOrigin")
    expiry = anchors.get("dateOfExpiry")

    if residence:
        residence_left, residence_top, _, residence_bottom = _anchor_bbox(residence)
        line_height = max(12.0, float(residence_bottom - residence_top))
        x0 = _label_x0(residence, width)
        if origin:
            _, origin_top, _, origin_bottom = _anchor_bbox(origin)
            origin_height = max(12.0, float(origin_bottom - origin_top))
            origin_bbox = [
                x0,
                max(0, int(origin_top - origin_height * 0.18)),
                int(width * 0.985),
                min(height, int(residence_top + line_height * 0.28)),
            ]
            origin_source = "phase11_9_label_bounded_origin"
        else:
            # Several cards miss the origin label in full-page OCR.  The
            # residence anchor still provides a stable upper boundary.
            origin_bbox = [
                x0,
                max(0, int(residence_top - line_height * 2.05)),
                int(width * 0.985),
                min(height, int(residence_top + line_height * 0.28)),
            ]
            origin_source = "phase11_9_origin_inferred_from_residence"
        residence_end = (
            _anchor_bbox(expiry)[1] + int(line_height * 0.95)
            if expiry
            else residence_bottom + int(line_height * 1.35)
        )
        residence_bbox = [
            x0,
            max(0, int(residence_top - line_height * 0.16)),
            int(width * 0.985),
            min(height, max(residence_bottom + 1, residence_end)),
        ]
        regions["placeOfOrigin"] = {
            "pageIndex": 0,
            "bbox": origin_bbox,
            "normalizedBbox": [
                origin_bbox[0] / width,
                origin_bbox[1] / height,
                origin_bbox[2] / width,
                origin_bbox[3] / height,
            ],
            "regionSource": origin_source,
            "labelMatchScore": 1.0 if origin else 0.0,
            "maxValueLines": 2,
        }
        regions["placeOfResidence"] = {
            "pageIndex": 0,
            "bbox": residence_bbox,
            "normalizedBbox": [
                residence_bbox[0] / width,
                residence_bbox[1] / height,
                residence_bbox[2] / width,
                residence_bbox[3] / height,
            ],
            "regionSource": "phase11_9_label_bounded_residence",
            "labelMatchScore": 1.0,
            "maxValueLines": 2,
        }
        return regions

    # If no address anchor exists, retain a conservative fixed band rather
    # than expanding into neighbouring fields.
    for field_name in TARGET_FIELDS:
        bbox = _fallback_bbox(width, height, field_name)
        x0, y0, x1, y1 = ADDRESS_FALLBACK_ROIS[field_name]
        regions[field_name] = {
            "pageIndex": 0,
            "bbox": bbox,
            "normalizedBbox": [x0, y0, x1, y1],
            "regionSource": "phase11_9_conservative_fallback",
            "labelMatchScore": 0.0,
            "maxValueLines": 2,
        }
    return regions


def _usable_candidates(
    field_name: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    usable: list[dict[str, Any]] = []
    for raw in candidates:
        cleaned = field_candidate(field_name, raw.get("rawValue") or raw.get("value"))
        if not cleaned or len(phase11_8._tokens(cleaned)) < 2:
            continue
        safe, rule = phase11_7._safe_address(cleaned)
        if not safe:
            continue
        item = dict(raw)
        profile = str(raw.get("profile") or raw.get("engine") or "unknown")
        item.update(
            {
                "value": cleaned,
                "rawValue": raw.get("rawValue") or raw.get("value"),
                "profile": profile,
                "family": phase11_7._family(profile),
                "profileWeight": phase11_7._profile_weight(profile),
                "validationRule": rule,
                "unicodeEvidence": phase11_5.ascii_text(cleaned) != cleaned,
                "tokenKeys": list(phase11_8._sequence_key(cleaned)),
            }
        )
        usable.append(item)
    return usable


def _select_relaxed_consensus(
    field_name: str,
    candidates: list[dict[str, Any]],
    *,
    bbox: list[int] | None,
    page_index: int,
) -> dict[str, Any]:
    usable = _usable_candidates(field_name, candidates)
    if not usable:
        return {
            "value": None,
            "asciiValue": None,
            "status": "not_found",
            "asciiStatus": "not_found",
            "confidence": 0.0,
            "errorSignals": ["not_found"],
            "selectionMode": "phase11_7_no_safe_candidate",
            "evidence": {"pageIndex": page_index, "bbox": bbox or [], "candidates": []},
        }

    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in usable:
        groups[tuple(item["tokenKeys"])].append(item)

    ranked = sorted(
        groups.values(),
        key=lambda members: (
            len(members),
            len({member["family"] for member in members}),
            sum(bool(member["unicodeEvidence"]) for member in members),
            sum(float(member.get("confidence") or 0.0) for member in members)
            / max(1, len(members)),
            len(members[0]["tokenKeys"]),
        ),
        reverse=True,
    )
    members = ranked[0]
    families = {member["family"] for member in members}
    profiles = {member["profile"] for member in members}
    # Same-family support is accepted only for multiple Paddle crop variants;
    # other families must still agree independently.
    same_profile_ok = len(members) >= 2 and families == {"paddle"} and len(profiles) == 1
    independent_ok = len(members) >= 2 and len(families) >= 2
    if not same_profile_ok and not independent_ok:
        return {
            "value": None,
            "asciiValue": None,
            "status": "not_found",
            "asciiStatus": "not_found",
            "confidence": 0.0,
            "errorSignals": ["insufficient_independent_support"],
            "selectionMode": "phase11_8_no_token_consensus",
            "evidence": {"pageIndex": page_index, "bbox": bbox or [], "candidates": usable},
        }

    selected = max(
        members,
        key=lambda item: (
            bool(item["unicodeEvidence"]),
            item["profileWeight"],
            float(item.get("confidence") or 0.0),
        ),
    )
    value = repair_unicode(selected["value"])
    return {
        "value": value,
        "asciiValue": phase11_5.ascii_text(value),
        "status": "needs_review",
        "asciiStatus": "verified_base_text" if independent_ok else "needs_review",
        "confidence": round(
            min(float(item.get("confidence") or 0.0) for item in members),
            6,
        ),
        "errorSignals": [],
        # Keep the locked schema enum used by prior shadow artifacts.
        "selectionMode": "phase11_6_single_candidate",
        "validation": {
            "valid": True,
            "rule": "address_shape",
            "roiPolicy": POLICY_ID,
            "supportingRecognizerCount": len(profiles),
            "supportingRecognizerFamilyCount": len(families),
            "sameProfileVariantConsensus": same_profile_ok,
        },
        "evidence": {"pageIndex": page_index, "bbox": bbox or [], "candidates": usable},
    }


def select_address_candidate(
    field_name: str,
    candidates: list[dict[str, Any]],
    *,
    bbox: list[int] | None,
    page_index: int = 0,
) -> dict[str, Any]:
    candidate = _select_relaxed_consensus(
        field_name,
        candidates,
        bbox=bbox,
        page_index=page_index,
    )
    if candidate.get("value"):
        return candidate
    return phase11_8.select_address_candidate(
        field_name,
        candidates,
        bbox=bbox,
        page_index=page_index,
    )


def _baseline_needs_recovery(
    field_name: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    if candidate.get("value") and any(
        signal in {"label_contamination", "region_or_line_merge", "character_omission"}
        for signal in baseline.get("errorSignals", [])
    ):
        return True
    return phase11_7._baseline_needs_recovery(field_name, baseline, candidate)


def _manual_field(field: dict[str, Any], selection_mode: str) -> dict[str, Any]:
    output = copy.deepcopy(field)
    output.setdefault("value", None)
    output.setdefault("asciiValue", None)
    output.setdefault("confidence", 0.0)
    output.setdefault("errorSignals", ["not_found"] if not output.get("value") else [])
    output.setdefault("evidence", {"pageIndex": 0, "bbox": [], "candidates": []})
    output["status"] = "needs_review" if output.get("value") else "not_found"
    output["asciiStatus"] = "needs_review" if output.get("value") else "not_found"
    output["selectionMode"] = selection_mode
    return output


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
        baseline = copy.deepcopy(baseline_fields.get(field_name) or {})
        if field_name in TARGET_FIELDS:
            region = regions.get(field_name, {})
            candidate = select_address_candidate(
                field_name,
                candidates_by_field.get(field_name, []),
                bbox=region.get("bbox"),
                page_index=int(region.get("pageIndex", 0)),
            )
            available = bool(candidate.get("value"))
            applied = available and _baseline_needs_recovery(field_name, baseline, candidate)
            recovery_counts["available"] += int(available)
            recovery_counts["applied"] += int(applied)
            if applied:
                field = _manual_field(candidate, "phase11_6_single_candidate")
                field["policyVersion"] = CANDIDATE_VERSION
                field["policyMode"] = "SHADOW_REVIEW_ONLY"
                fields[field_name] = field
                continue
            if baseline.get("value") is not None:
                baseline["phase11_9Candidate"] = candidate
                fields[field_name] = _manual_field(
                    baseline,
                    "phase11_6_baseline_preserved",
                )
                continue
            fields[field_name] = _manual_field(candidate, "phase11_6_single_candidate")
            continue
        fields[field_name] = _manual_field(baseline, "phase11_6_baseline_preserved")
    present = sum(field.get("value") is not None for field in fields.values())
    accepted = sum(field.get("status") == "accepted" for field in fields.values())
    review = sum(field.get("status") == "needs_review" for field in fields.values())
    missing = sum(field.get("status") == "not_found" for field in fields.values())
    return {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": "VIETNAM_CITIZEN_ID_FRONT",
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
