"""Phase 11.6 CCCD ROI refinement for names and two-line addresses.

This module deliberately reuses Phase 11.5 recognition and validation rules.
It only narrows regions with label evidence and ranks existing OCR candidates;
it never creates text, accents, or an accepted value from a directory lookup.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

import phase11_5_cccd as phase11_5
from phase11_cccd import FIELD_ORDER, FIELD_SPECS, _bounds, _label_score

FRONT_FIELD_ROIS = phase11_5.FRONT_FIELD_ROIS
build_crop_variants = phase11_5.build_crop_variants
business_values = phase11_5.business_values
nfc_text = phase11_5.nfc_text
phase11_5_field_candidate = phase11_5.field_candidate
phase11_5_select_field_candidate = phase11_5.select_field_candidate

SCHEMA_VERSION = "11.6.0"
POLICY_ID = "phase11.6-cccd-address-lines-name-selection"
TARGET_FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
PROTECTED_FIELDS = tuple(name for name in FIELD_ORDER if name not in TARGET_FIELDS)

# The old template bands overlapped two different address fields.  These are
# only fallbacks: a detected label and the following label take precedence.
PHASE11_6_ROIS = {
    **FRONT_FIELD_ROIS,
    "fullName": (0.27, 0.45, 0.90, 0.55),
    "placeOfOrigin": (0.25, 0.71, 0.99, 0.81),
    "placeOfResidence": (0.24, 0.82, 0.99, 0.97),
}


def _label_anchors(pages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    anchors: dict[str, tuple[dict[str, Any], float]] = {}
    english_labels = {
        "fullName": "full name",
        "dateOfBirth": "date of birth",
        "placeOfOrigin": "place of origin",
        "placeOfResidence": "place of residence",
        "dateOfExpiry": "date of expiry",
    }
    for page in pages:
        for line_index, (text, box) in enumerate(
            zip(page.get("recognizedTexts", []), page.get("recognizedBoxes", []), strict=False)
        ):
            record = {
                "text": str(text),
                "box": box,
                "pageIndex": int(page.get("pageIndex", 0)),
                "lineIndex": line_index,
            }
            exact_english = [
                name
                for name, label in english_labels.items()
                if label in record["text"].casefold()
            ]
            fields_to_check = (
                ((name, FIELD_SPECS[name]) for name in exact_english)
                if exact_english
                else FIELD_SPECS.items()
            )
            for field_name, spec in fields_to_check:
                score = max(_label_score(record["text"], label) for label in spec["labels"])
                if any(
                    re.search(pattern, record["text"], flags=re.IGNORECASE)
                    for pattern in phase11_5.LABEL_PATTERNS.get(field_name, ())
                ):
                    score = max(score, 1.0)
                if english_labels.get(field_name, "") in record["text"].casefold():
                    score = max(score, 1.0)
                if score >= float(spec["labelThreshold"]) and (
                    field_name not in anchors or score > anchors[field_name][1]
                ):
                    anchors[field_name] = (record, score)
    return {name: record for name, (record, _) in anchors.items()}


def _line_bbox(
    anchor: dict[str, Any],
    next_anchor: dict[str, Any] | None,
    fallback: list[int],
    *,
    height: int,
    max_value_lines: int,
) -> list[int]:
    _, top, _, bottom = _bounds(anchor["box"])
    line_height = max(10.0, bottom - top)
    # CCCD labels sit above their values. Excluding the label row makes the
    # recognizers see one logical field instead of a bilingual paragraph.
    start = max(0, int(bottom + line_height * 0.05))
    maximum = min(
        height,
        int(bottom + line_height * (1.75 if max_value_lines == 1 else 3.05)),
    )
    if next_anchor is not None:
        next_top = _bounds(next_anchor["box"])[1]
        if next_top > start + line_height * 0.55:
            maximum = min(
                maximum,
                max(start + int(line_height * 0.75), int(next_top - line_height * 0.12)),
            )
    return [fallback[0], start, fallback[2], max(start + 1, maximum)]


def locate_field_regions(
    pages: list[dict[str, Any]],
    page_sizes: list[tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    """Use non-overlapping label-to-next-label bands for name/address fields."""
    if not page_sizes:
        return {}
    width, height = page_sizes[0]
    anchors = _label_anchors(pages)
    regions: dict[str, dict[str, Any]] = {}
    following = {
        "fullName": "dateOfBirth",
        "placeOfOrigin": "placeOfResidence",
    }
    for field_name in FIELD_ORDER:
        x0, y0, x1, y1 = PHASE11_6_ROIS[field_name]
        fallback = [int(width * x0), int(height * y0), int(width * x1), int(height * y1)]
        anchor = anchors.get(field_name)
        next_anchor = anchors.get(following.get(field_name, ""))
        _, anchor_top, _, anchor_bottom = (
            _bounds(anchor["box"]) if anchor else (0, 0, 0, 0)
        )
        anchor_center = (anchor_top + anchor_bottom) / 2
        fallback_center = (fallback[1] + fallback[3]) / 2
        use_anchor = (
            anchor is not None
            and int(anchor["pageIndex"]) == 0
            and abs(anchor_center - fallback_center)
            <= max(height * 0.12, fallback[3] - fallback[1])
        )
        max_value_lines = 2 if field_name in {"placeOfOrigin", "placeOfResidence"} else 1
        bbox = (
            _line_bbox(
                anchor,
                next_anchor,
                fallback,
                height=height,
                max_value_lines=max_value_lines,
            )
            if use_anchor
            else fallback
        )
        regions[field_name] = {
            "pageIndex": 0,
            "bbox": bbox,
            "normalizedBbox": [x0, y0, x1, y1],
            "regionSource": (
                "phase11_6_label_line_band" if use_anchor else "phase11_6_template_fallback"
            ),
            "labelMatchScore": 1.0 if use_anchor else 0.0,
            "maxValueLines": max_value_lines,
        }
    return regions


def field_candidate(field_name: str, raw_text: Any) -> str:
    value = phase11_5_field_candidate(field_name, raw_text)
    if field_name in {"placeOfOrigin", "placeOfResidence"}:
        # Do not retain a trailing label if a recognizer merged the next line.
        trailing_label = (
            r"\b(?:nơi\s+thường\s+trú|place\s+of\s+residence|"
            r"có\s+giá\s+trị\s+đến|date\s+of\s+expiry)\b"
        )
        value = re.split(trailing_label, value, flags=re.IGNORECASE)[0]
    return nfc_text(value).strip(" ,;|/-")


def _selection_confidence(field_name: str, candidate: dict[str, Any]) -> dict[str, Any]:
    updated = dict(candidate)
    raw = nfc_text(updated.get("rawValue") or updated.get("value"))
    value = field_candidate(field_name, updated.get("value"))
    confidence = float(updated.get("confidence") or 0.0)
    word_count = len(
        [word for word in value.split() if any(char.isalpha() for char in word)]
    )
    contaminated = bool(
        re.search(
            r"\b(?:full\s*name|họ\s+và\s+tên|date\s+of\s+birth|ngày\s+sinh)\b",
            raw,
            re.I,
        )
    )
    if field_name == "fullName":
        confidence += 0.12 if 2 <= word_count <= 5 and not contaminated else -0.18
    if field_name in {"placeOfOrigin", "placeOfResidence"}:
        is_date_like = bool(re.search(r"\d{1,2}[/-]\d{1,2}", value))
        confidence += 0.08 if 2 <= word_count <= 16 and not is_date_like else -0.12
    updated["value"] = value
    updated["confidence"] = max(0.0, min(1.0, confidence))
    return updated


def select_field_candidate(
    field_name: str,
    candidates: list[dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    selected = phase11_5_select_field_candidate(
        field_name,
        [_selection_confidence(field_name, candidate) for candidate in candidates],
        **kwargs,
    )
    selected["selectionMode"] = f"phase11_6_{selected['selectionMode']}"
    return selected


def build_identity_card(
    candidates_by_field: dict[str, list[dict[str, Any]]],
    regions: dict[str, dict[str, Any]],
    *,
    baseline_fields: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    fields: dict[str, dict[str, Any]] = {}
    for field_name in FIELD_ORDER:
        region = regions.get(field_name, {})
        candidate = select_field_candidate(
            field_name,
            candidates_by_field.get(field_name, []),
            bbox=region.get("bbox"),
            page_index=int(region.get("pageIndex", 0)),
            date_of_birth=(
                fields.get("dateOfBirth", {}).get("value")
                if field_name == "dateOfExpiry"
                else None
            ),
        )
        baseline = deepcopy((baseline_fields or {}).get(field_name) or {})
        baseline_value = nfc_text(baseline.get("value")) or None
        candidate_value = nfc_text(candidate.get("value")) or None
        if baseline_value:
            if candidate_value == baseline_value and candidate["status"] == "accepted":
                fields[field_name] = candidate
            else:
                baseline["selectionMode"] = "phase11_6_baseline_preserved"
                baseline["phase11_6Candidate"] = candidate
                fields[field_name] = baseline
        elif candidate_value:
            # A newly found value remains review-only until it survives held-out
            # evaluation; exact OCR consensus alone does not override an empty
            # baseline during this development replay.
            candidate["status"] = "needs_review"
            fields[field_name] = candidate
        else:
            fields[field_name] = candidate
    present = sum(field["value"] is not None for field in fields.values())
    accepted = sum(field["status"] == "accepted" for field in fields.values())
    review = sum(field["status"] == "needs_review" for field in fields.values())
    missing = sum(field["status"] == "not_found" for field in fields.values())
    sensitive = ("identityNumber", "dateOfBirth", "sex", "dateOfExpiry")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": "VIETNAM_CITIZEN_ID_FRONT",
        "extractionPolicy": POLICY_ID,
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
            "readyForAutomaticUse": bool(
                all(fields[name]["status"] == "accepted" for name in sensitive)
                and accepted == len(FIELD_ORDER)
            ),
        },
    }
