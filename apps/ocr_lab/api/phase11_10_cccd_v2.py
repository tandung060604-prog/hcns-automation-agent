"""OCR-HO-V2-014 line-aware shadow candidate.

Only name and address evidence is reconsidered.  The runner supplies one crop
per detected value line; this module joins candidates by recognizer/profile in
reading order and never promotes a value beyond ``needs_review``.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any

import cv2
import numpy as np
import phase11_5_cccd as phase11_5
import phase11_6_cccd as phase11_6
import phase11_9_cccd_v2 as phase11_9
from phase11_cccd import FIELD_ORDER, _bounds, canonicalize_identity_card

CANDIDATE_VERSION = "11.10.0"
SCHEMA_VERSION = phase11_6.SCHEMA_VERSION
POLICY_ID = "phase11.10-v2-line-aware-name-address"
TARGET_FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
PROTECTED_FIELDS = tuple(name for name in FIELD_ORDER if name not in TARGET_FIELDS)
build_crop_variants = phase11_5.build_crop_variants
business_values = phase11_6.business_values
field_candidate = phase11_6.field_candidate


def _line_bbox(box: Any) -> list[int]:
    left, top, right, bottom = _bounds(box)
    return [left, top, right, bottom]


def prepare_line_pages(
    session_dir: Any,
    pages: list[dict[str, Any]],
    images: list[Any],
) -> tuple[list[dict[str, Any]], list[Any]]:
    """Use the existing card rectification and project detector boxes into it."""

    if not images:
        return pages, images
    canonical, metadata = canonicalize_identity_card(images[0])
    transform = metadata.get("perspectiveTransform")
    if not transform:
        return pages, images
    matrix = np.asarray(transform, dtype=np.float32)
    projected = copy.deepcopy(pages)
    for page in projected:
        boxes = []
        for box in page.get("recognizedBoxes", []):
            points = np.asarray(box, dtype=np.float32).reshape(-1, 1, 2)
            mapped = cv2.perspectiveTransform(points, matrix).reshape(-1, 2)
            boxes.append(mapped.round(3).tolist())
        page["recognizedBoxes"] = boxes
    return projected, [canonical]


def _geometry_line_bboxes(
    page: dict[str, Any],
    region: dict[str, Any],
    field_name: str,
    page_size: tuple[int, int],
) -> tuple[list[list[int]], list[int]]:
    width, height = page_size
    fallback = region.get("bbox") or [0, 0, width, height]
    _, region_top, _, region_bottom = (
        int(fallback[0]),
        int(fallback[1]),
        int(fallback[2]),
        int(fallback[3]),
    )
    template_bands = {
        "fullName": (0.42, 0.57),
        "placeOfOrigin": (0.615, 0.745),
        "placeOfResidence": (0.69, 0.875),
    }
    band_top, band_bottom = template_bands[field_name]
    top = max(region_top, int(height * band_top))
    bottom = min(region_bottom, int(height * band_bottom))
    value_left = int(width * (0.47 if field_name != "fullName" else 0.45))
    rows: list[tuple[int, list[int]]] = []
    for line_id, box in enumerate(page.get("recognizedBoxes", [])):
        left, line_top, right, line_bottom = _bounds(box)
        center_y = (line_top + line_bottom) / 2
        if not top <= center_y <= bottom or right <= value_left:
            continue
        rows.append((line_id, [left, line_top, right, line_bottom]))
    rows.sort(key=lambda item: (item[1][1], item[1][0]))
    groups: list[list[tuple[int, list[int]]]] = []
    for item in rows:
        if not groups or item[1][1] - groups[-1][-1][1][3] > max(8, int(height * 0.012)):
            groups.append([item])
        else:
            groups[-1].append(item)
    line_bboxes: list[list[int]] = []
    line_ids: list[int] = []
    for group in groups[: (1 if field_name == "fullName" else 2)]:
        y0 = max(0, min(item[1][1] for item in group) - 2)
        y1 = min(height, max(item[1][3] for item in group) + 2)
        line_bboxes.append([value_left, y0, int(width * 0.985), y1])
        line_ids.append(group[0][0])
    return line_bboxes, line_ids


def locate_field_regions(
    pages: list[dict[str, Any]], page_sizes: list[tuple[int, int]]
) -> dict[str, dict[str, Any]]:
    """Use detected value lines after the relevant label, then a safe fallback."""

    regions = phase11_9.locate_field_regions(pages, page_sizes)
    if not page_sizes:
        return regions
    anchors = phase11_6._label_anchors(pages)
    page = pages[0] if pages else {}
    lines = [
        {"lineId": index, "box": box, "text": str(text)}
        for index, (text, box) in enumerate(
            zip(page.get("recognizedTexts", []), page.get("recognizedBoxes", []), strict=False)
        )
    ]
    next_labels = {
        "fullName": "dateOfBirth",
        "placeOfOrigin": "placeOfResidence",
        "placeOfResidence": "dateOfExpiry",
    }
    for field_name in TARGET_FIELDS:
        anchor = anchors.get(field_name)
        region = regions.get(field_name, {})
        choices = []
        if anchor:
            left, top, right, bottom = _bounds(anchor["box"])
            next_anchor = anchors.get(next_labels[field_name])
            next_top = _bounds(next_anchor["box"])[1] if next_anchor else 10**9
            line_height = max(10, bottom - top)
            for line in lines:
                line_left, line_top, line_right, line_bottom = _bounds(line["box"])
                same_row_value = (
                    top - line_height * 0.35 <= line_top <= bottom + line_height * 0.35
                    and line_left >= right - line_height
                )
                following_value = bottom < line_top < next_top - line_height * 0.08
                if (same_row_value or following_value) and line["lineId"] != anchor["lineIndex"]:
                    choices.append(line)
        choices.sort(key=lambda item: (_bounds(item["box"])[1], _bounds(item["box"])[0]))
        max_lines = 1 if field_name == "fullName" else 2
        selected = choices[:max_lines]
        geometry_bboxes, geometry_ids = _geometry_line_bboxes(
            page,
            region,
            field_name,
            (page_sizes[0][0], page_sizes[0][1]),
        )
        if selected:
            region["lineBboxes"] = [_line_bbox(item["box"]) for item in selected]
            region["lineIds"] = [item["lineId"] for item in selected]
            region["regionSource"] = "phase11_10_detector_lines"
        elif geometry_bboxes:
            region["lineBboxes"] = geometry_bboxes
            region["lineIds"] = geometry_ids
            region["regionSource"] = "phase11_10_geometry_line_segmentation"
        region["regionSource"] = (
            "phase11_10_detector_lines" if selected else region.get("regionSource")
        )
        regions[field_name] = region
    return regions


def assemble_line_candidates(
    candidates_by_field: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Join same recognizer/variant line predictions without inventing tokens."""

    assembled: dict[str, list[dict[str, Any]]] = {}
    for field_name, candidates in candidates_by_field.items():
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for candidate in candidates:
            groups[(str(candidate.get("profile")), str(candidate.get("variant")))].append(candidate)
        values: list[dict[str, Any]] = []
        for (_, _), members in groups.items():
            members.sort(key=lambda item: int(item.get("lineOrder", 0)))
            value = " ".join(str(item.get("value") or "").strip() for item in members).strip()
            raw = " ".join(str(item.get("rawValue") or "").strip() for item in members).strip()
            if not value:
                continue
            merged = dict(members[0])
            merged.update(
                {
                    "value": value,
                    "rawValue": raw,
                    "lineIds": [item.get("lineId") for item in members],
                }
            )
            values.append(merged)
        assembled[field_name] = values
    return assembled


def _key(value: str, ascii_only: bool) -> str:
    value = phase11_5.nfc_text(value)
    return phase11_5.ascii_text(value).casefold() if ascii_only else value.casefold()


def _select_name(candidates: list[dict[str, Any]], bbox: list[int]) -> dict[str, Any]:
    usable = [
        dict(item, value=phase11_6.field_candidate("fullName", item.get("value")))
        for item in candidates
    ]
    usable = [item for item in usable if phase11_5.validate_field("fullName", item["value"])[0]]
    for ascii_only in (False, True):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in usable:
            groups[_key(item["value"], ascii_only)].append(item)
        supported = [
            items
            for items in groups.values()
            if len({str(item.get("profile", "")) for item in items}) >= 2
        ]
        if supported:
            members = max(supported, key=len)
            selected = max(
                members,
                key=lambda item: (
                    sum(char != phase11_5.ascii_text(char) for char in item["value"]),
                    float(item.get("confidence") or 0),
                ),
            )
            return {
                "value": selected["value"],
                "asciiValue": phase11_5.ascii_text(selected["value"]),
                "status": "needs_review",
                "asciiStatus": "needs_review",
                "confidence": min(float(item.get("confidence") or 0) for item in members),
                "errorSignals": ["diacritic_disagreement"] if ascii_only else [],
                "selectionMode": "phase11_10_name_ascii_consensus"
                if ascii_only
                else "phase11_10_name_unicode_consensus",
                "evidence": {"pageIndex": 0, "bbox": bbox, "candidates": usable},
            }
    return {
        "value": None,
        "asciiValue": None,
        "status": "not_found",
        "asciiStatus": "not_found",
        "confidence": 0.0,
        "errorSignals": ["insufficient_independent_support"],
        "selectionMode": "phase11_10_no_name_consensus",
        "evidence": {"pageIndex": 0, "bbox": bbox, "candidates": usable},
    }


def build_identity_card(
    candidates_by_field: dict[str, list[dict[str, Any]]],
    regions: dict[str, dict[str, Any]],
    *,
    baseline_fields: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    baseline_fields = baseline_fields or {}
    candidates_by_field = assemble_line_candidates(candidates_by_field)
    fields: dict[str, dict[str, Any]] = {}
    for field_name in FIELD_ORDER:
        baseline = copy.deepcopy(baseline_fields.get(field_name) or {})
        region = regions.get(field_name, {})
        if field_name == "fullName":
            candidate = _select_name(
                candidates_by_field.get(field_name, []), region.get("bbox", [])
            )
        elif field_name in {"placeOfOrigin", "placeOfResidence"}:
            candidate = phase11_9.select_address_candidate(
                field_name,
                candidates_by_field.get(field_name, []),
                bbox=region.get("bbox"),
                page_index=0,
            )
        else:
            fields[field_name] = baseline
            continue
        if candidate.get("value") and (not baseline.get("value") or baseline.get("errorSignals")):
            candidate["status"] = "needs_review"
            candidate["asciiStatus"] = "needs_review"
            candidate["policyVersion"] = CANDIDATE_VERSION
            fields[field_name] = candidate
        else:
            baseline["selectionMode"] = "phase11_10_baseline_preserved"
            baseline["phase11_10Candidate"] = candidate
            fields[field_name] = baseline
    for field in fields.values():
        field["status"] = "needs_review" if field.get("value") else "not_found"
        field["asciiStatus"] = "needs_review" if field.get("value") else "not_found"
    present = sum(field.get("value") is not None for field in fields.values())
    return {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": "VIETNAM_CITIZEN_ID_FRONT",
        "extractionPolicy": POLICY_ID,
        "policyMode": "SHADOW_REVIEW_ONLY",
        "fields": fields,
        "summary": {
            "expectedFieldCount": len(FIELD_ORDER),
            "presentFieldCount": present,
            "acceptedFieldCount": 0,
            "needsReviewFieldCount": present,
            "notFoundFieldCount": len(FIELD_ORDER) - present,
            "documentCompleteness": round(present / len(FIELD_ORDER), 6),
            "acceptedRate": 0.0,
            "readyForAutomaticUse": False,
            "candidateVersion": CANDIDATE_VERSION,
            "targetFields": list(TARGET_FIELDS),
        },
    }
