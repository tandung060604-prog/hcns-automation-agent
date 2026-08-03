#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clean-room CCCD orientation, canonicalization, extraction, and metrics.

This module deliberately contains no third-party repository code or model weights.
All extraction is evidence-based: a value must be present in an OCR line and every
returned value keeps its source line and bounding box.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np


ORIENTATIONS = (0, 90, 180, 270)
# OCR-HO-V2-004 keeps runtime orientation conservative while the new
# field-recovery policy is evaluated. Rotation helpers remain available for
# historical diagnostics, but v1.1 only runs the original image orientation.
OCR_HO_V2_VERSION = "1.1.0"
ORIENTATION_POLICY = "fixed_0_degree"
SUPPORTED_ORIENTATIONS = (0,)
CARD_ASPECT_RATIO = 85.60 / 53.98
CANONICAL_MIN_WIDTH = 2000
CANONICAL_MAX_WIDTH = 3200

IDENTITY_ANCHORS = {
    "can cuoc cong dan": 4.0,
    "citizen identity card": 3.0,
    "so no": 1.5,
    "ho va ten": 1.5,
    "full name": 1.0,
    "ngay sinh": 1.0,
    "date of birth": 1.0,
    "gioi tinh": 0.8,
    "nationality": 0.8,
    "que quan": 0.8,
    "place of origin": 0.8,
    "noi thuong tru": 0.8,
    "place of residence": 0.8,
    "co gia tri den": 0.8,
    "date of expiry": 0.8,
}

IDENTITY_LAYOUT_GROUPS = (
    (
        "cong hoa xa hoi chu nghia viet nam",
        "socialist republic of viet nam",
        "can cuoc cong dan",
        "citizen identity card",
    ),
    ("so no", "identity number"),
    ("ho va ten", "full name"),
    (
        "ngay sinh",
        "date of birth",
        "gioi tinh",
        "sex",
        "quoc tich",
        "nationality",
    ),
    ("que quan", "place of origin"),
    ("noi thuong tru", "place of residence"),
    ("co gia tri den", "date of expiry"),
)

FIELD_ORDER = (
    "identityNumber",
    "fullName",
    "dateOfBirth",
    "sex",
    "nationality",
    "placeOfOrigin",
    "placeOfResidence",
    "dateOfExpiry",
)

FIELD_SPECS: dict[str, dict[str, Any]] = {
    "identityNumber": {
        "labels": ("so no", "so can cuoc", "identity number"),
        "labelThreshold": 0.60,
        "threshold": 0.90,
        "multiline": False,
    },
    "fullName": {
        "labels": ("ho va ten full name", "ho va ten", "full name"),
        "labelThreshold": 0.72,
        "threshold": 0.86,
        "multiline": False,
    },
    "dateOfBirth": {
        "labels": ("ngay sinh date of birth", "ngay sinh", "date of birth"),
        "labelThreshold": 0.60,
        "threshold": 0.86,
        "multiline": False,
    },
    "sex": {
        "labels": ("gioi tinh sex", "gioi tinh", "sex"),
        "labelThreshold": 0.60,
        "threshold": 0.82,
        "multiline": False,
    },
    "nationality": {
        "labels": ("quoc tich nationality", "quoc tich", "nationality"),
        "labelThreshold": 0.55,
        "threshold": 0.82,
        "multiline": False,
    },
    "placeOfOrigin": {
        "labels": (
            "que quan place of origin",
            "que quan place of ongin",
            "que quan place of orgin",
            "que quan",
            "place of origin",
            "place of ongin",
            "place of orgin",
            "place of qrigin",
        ),
        "labelThreshold": 0.65,
        "threshold": 0.82,
        "multiline": True,
    },
    "placeOfResidence": {
        "labels": (
            "noi thuong tru place of residence",
            "noi thuong tru",
            "no thuong tru",
            "no thuong trul",
            "place of residence",
            "placeof residence",
            "placeof resdece",
        ),
        "labelThreshold": 0.60,
        "threshold": 0.82,
        "multiline": True,
    },
    "dateOfExpiry": {
        "labels": ("co gia tri den date of expiry", "co gia tri den", "date of expiry"),
        "labelThreshold": 0.60,
        "threshold": 0.86,
        "multiline": False,
    },
}

# OCR often renders bilingual labels with a separator or a single character
# substitution (for example ``Piace`` for ``Place``). These aliases are only
# used to remove label prefixes from evidence; they never synthesize values.
FIELD_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "identityNumber": ("so no", "so can cuoc", "identity number"),
    "fullName": ("ho va ten full name", "ho va ten", "full name"),
    "dateOfBirth": ("ngay sinh date of birth", "ngay sinh", "date of birth"),
    "sex": ("gioi tinh sex", "gioi tinh", "sex"),
    "nationality": ("quoc tich nationality", "quoc tich", "nationality"),
    "placeOfOrigin": (
        "que quan place of origin",
        "que quan",
        "place of origin",
        "place of ongin",
        "place of orgin",
        "place of qrigin",
    ),
    "placeOfResidence": (
        "noi thuong tru place of residence",
        "noi thuong tru",
        "no thuong tru",
        "no thuong trul",
        "place of residence",
        "placeof residence",
        "placeof resdece",
        "piace of residence",
    ),
    "dateOfExpiry": (
        "co gia tri den date of expiry",
        "co gia tri den",
        "date of expiry",
    ),
}

DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
IDENTITY_NUMBER_RE = re.compile(r"(?<!\d)(?:\d[\s.]*){12}(?!\d)")


def accent_key(value: str) -> str:
    """Normalize only for label lookup; never use this value as extracted output."""
    normalized = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    plain = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def rotate_image(image: np.ndarray, degrees: int) -> np.ndarray:
    if degrees == 0:
        return image.copy()
    if degrees == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"Unsupported rotation: {degrees}")


def _bounds(box: Any) -> tuple[float, float, float, float]:
    if not isinstance(box, list) or not box:
        return 0.0, 0.0, 0.0, 0.0
    xs = [float(point[0]) for point in box if isinstance(point, (list, tuple))]
    ys = [float(point[1]) for point in box if isinstance(point, (list, tuple))]
    if not xs or not ys:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def _box_union(lines: Iterable[dict[str, Any]]) -> list[list[float]] | None:
    bounds = [_bounds(line.get("box", [])) for line in lines]
    valid = [bound for bound in bounds if bound[2] > bound[0] and bound[3] > bound[1]]
    if not valid:
        return None
    left = min(bound[0] for bound in valid)
    top = min(bound[1] for bound in valid)
    right = max(bound[2] for bound in valid)
    bottom = max(bound[3] for bound in valid)
    return [
        [round(left, 3), round(top, 3)],
        [round(right, 3), round(top, 3)],
        [round(right, 3), round(bottom, 3)],
        [round(left, 3), round(bottom, 3)],
    ]


def _identity_layout_score(
    texts: list[str],
    boxes: list[Any],
    image_height: int,
) -> dict[str, Any]:
    """Score whether recognized CCCD anchors follow an upright front-card layout."""
    if image_height <= 0:
        return {
            "score": 0.0,
            "pairAgreement": None,
            "evidenceCount": 0,
        }

    positions: dict[int, list[float]] = {}
    for index, text in enumerate(texts):
        if index >= len(boxes):
            continue
        left, top, right, bottom = _bounds(boxes[index])
        if right <= left or bottom <= top:
            continue
        normalized = accent_key(text)
        matched_groups = {
            group_index
            for group_index, patterns in enumerate(IDENTITY_LAYOUT_GROUPS)
            if any(pattern in normalized for pattern in patterns)
        }
        if IDENTITY_NUMBER_RE.search(text):
            matched_groups.add(1)
        center_y = ((top + bottom) / 2.0) / float(image_height)
        for group_index in matched_groups:
            positions.setdefault(group_index, []).append(center_y)

    group_positions = {
        group_index: float(np.median(values))
        for group_index, values in positions.items()
        if values
    }
    ordered_groups = sorted(group_positions)
    correct_pairs = 0
    inverted_pairs = 0
    for left_index, left_group in enumerate(ordered_groups):
        for right_group in ordered_groups[left_index + 1 :]:
            left_y = group_positions[left_group]
            right_y = group_positions[right_group]
            if left_y + 0.015 < right_y:
                correct_pairs += 1
            elif right_y + 0.015 < left_y:
                inverted_pairs += 1

    compared_pairs = correct_pairs + inverted_pairs
    pair_agreement = (
        (correct_pairs - inverted_pairs) / compared_pairs
        if compared_pairs
        else None
    )
    score = (pair_agreement or 0.0) * 4.0

    top_position = group_positions.get(0)
    if top_position is not None:
        score += 2.0 if top_position <= 0.45 else -2.0
    for lower_group in (4, 5):
        lower_position = group_positions.get(lower_group)
        if lower_position is not None:
            score += 0.75 if lower_position >= 0.45 else -0.75
    expiry_position = group_positions.get(6)
    if expiry_position is not None:
        score += 0.5 if expiry_position >= 0.55 else -0.5

    return {
        "score": round(score, 6),
        "pairAgreement": (
            round(pair_agreement, 6)
            if pair_agreement is not None
            else None
        ),
        "evidenceCount": len(group_positions),
    }


def orientation_diagnostics(
    page: dict[str, Any],
    rotation_degrees: int,
    image_size: tuple[int, int] | list[int],
) -> dict[str, Any]:
    texts = [
        str(text)
        for text in page.get("recognizedTexts", [])
        if str(text).strip()
    ]
    scores = [
        float(score)
        for score in page.get("recognitionScores", [])
        if score is not None
    ]
    boxes = page.get("recognizedBoxes", [])
    key = accent_key("\n".join(texts))
    anchor_hits = [
        anchor for anchor in IDENTITY_ANCHORS if anchor in key
    ]
    anchor_score = sum(IDENTITY_ANCHORS[anchor] for anchor in anchor_hits)
    identity_number_count = len(IDENTITY_NUMBER_RE.findall("\n".join(texts)))
    date_count = len(DATE_RE.findall("\n".join(texts)))
    horizontal_count = 0
    valid_box_count = 0
    for box in boxes:
        left, top, right, bottom = _bounds(box)
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            continue
        valid_box_count += 1
        horizontal_count += width >= height * 1.15
    horizontal_ratio = horizontal_count / valid_box_count if valid_box_count else 0.0
    width, height = int(image_size[0]), int(image_size[1])
    landscape_bonus = 0.25 if width >= height else 0.0
    mean_confidence = sum(scores) / len(scores) if scores else 0.0
    layout = _identity_layout_score(texts, boxes, height)
    total_score = (
        anchor_score
        + identity_number_count * 2.0
        + min(2, date_count) * 0.35
        + mean_confidence * 0.50
        + horizontal_ratio * 0.50
        + landscape_bonus
        + float(layout["score"])
    )
    return {
        "rotationDegrees": rotation_degrees,
        "score": round(total_score, 6),
        "identityAnchorHits": anchor_hits,
        "identityAnchorScore": round(anchor_score, 3),
        "identityNumberCandidateCount": identity_number_count,
        "dateCandidateCount": date_count,
        "meanConfidence": round(mean_confidence, 6) if scores else None,
        "lineCount": len(texts),
        "horizontalBoxRatio": round(horizontal_ratio, 6),
        "layoutScore": layout["score"],
        "layoutPairAgreement": layout["pairAgreement"],
        "layoutEvidenceCount": layout["evidenceCount"],
        "imageSize": [width, height],
    }


def select_orientation(
    candidates: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (OCR page, diagnostic) without exposing candidate OCR text."""
    if not candidates:
        raise ValueError("At least one orientation candidate is required")
    ranked = sorted(
        candidates,
        key=lambda item: (
            float(item[1]["score"]),
            -ORIENTATIONS.index(int(item[1]["rotationDegrees"])),
        ),
        reverse=True,
    )
    return ranked[0]


def is_identity_likely(diagnostic: dict[str, Any]) -> bool:
    return bool(
        float(diagnostic.get("identityAnchorScore", 0.0)) >= 3.0
        or (
            int(diagnostic.get("identityNumberCandidateCount", 0)) > 0
            and float(diagnostic.get("identityAnchorScore", 0.0)) >= 1.0
        )
    )


def _order_points(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(diffs)]
    ordered[3] = points[np.argmax(diffs)]
    return ordered


def canonicalize_identity_card(
    image: np.ndarray,
    min_width: int = CANONICAL_MIN_WIDTH,
    max_width: int = CANONICAL_MAX_WIDTH,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Perspective-normalize a visible card while retaining OCR-friendly pixels."""
    if image is None or image.size == 0:
        raise ValueError("Identity image is empty")
    source_height, source_width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 140)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    page_area = float(source_width * source_height)
    candidates: list[tuple[float, np.ndarray]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < page_area * 0.18 or area > page_area * 0.985:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        candidates.append((area, polygon.reshape(4, 2).astype(np.float32)))

    perspective_corrected = False
    detected_width = source_width
    resolution_capped = False
    if candidates:
        points = _order_points(max(candidates, key=lambda item: item[0])[1])
        top_left, top_right, bottom_right, bottom_left = points
        measured_width = max(
            np.linalg.norm(bottom_right - bottom_left),
            np.linalg.norm(top_right - top_left),
        )
        measured_height = max(
            np.linalg.norm(top_right - bottom_right),
            np.linalg.norm(top_left - bottom_left),
        )
        if measured_width >= 300 and measured_height >= 180:
            detected_width = int(round(measured_width))
            output_width = max(min_width, detected_width)
            if output_width > max_width:
                output_width = max_width
                resolution_capped = True
            output_height = int(round(output_width / CARD_ASPECT_RATIO))
            destination = np.array(
                [
                    [0, 0],
                    [output_width - 1, 0],
                    [output_width - 1, output_height - 1],
                    [0, output_height - 1],
                ],
                dtype=np.float32,
            )
            matrix = cv2.getPerspectiveTransform(points, destination)
            image = cv2.warpPerspective(
                image,
                matrix,
                (output_width, output_height),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
            perspective_corrected = True

    if not perspective_corrected and image.shape[1] < min_width:
        scale = min_width / image.shape[1]
        image = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    luminance, channel_a, channel_b = cv2.split(lab)
    luminance = cv2.createCLAHE(clipLimit=1.4, tileGridSize=(8, 8)).apply(luminance)
    enhanced = cv2.cvtColor(
        cv2.merge((luminance, channel_a, channel_b)),
        cv2.COLOR_LAB2BGR,
    )
    blurred_enhanced = cv2.GaussianBlur(enhanced, (0, 0), 0.8)
    enhanced = cv2.addWeighted(enhanced, 1.25, blurred_enhanced, -0.25, 0)
    return enhanced, {
        "perspectiveCorrected": perspective_corrected,
        "sourceSize": [source_width, source_height],
        "canonicalSize": [int(enhanced.shape[1]), int(enhanced.shape[0])],
        "detectedCardWidth": detected_width,
        "targetAspectRatio": round(CARD_ASPECT_RATIO, 6),
        "minimumWidth": min_width,
        "maximumWidth": max_width,
        "resolutionCapped": resolution_capped,
        "claheClipLimit": 1.4,
        "unsharp": True,
    }


def prepare_identity_card_page(
    source_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Cannot read identity-card page")
    canonical, metadata = canonicalize_identity_card(image)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), canonical):
        raise OSError("Cannot write canonical identity-card page")
    return metadata


def _line_records(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    global_index = 0
    for page_position, page in enumerate(pages):
        page_index = int(page.get("pageIndex", page_position))
        source_lines = page.get("lines")
        if isinstance(source_lines, list):
            for line_position, line in enumerate(source_lines):
                text = str(
                    line.get("rawText", line.get("text", line.get("correctedText", "")))
                ).strip()
                if not text:
                    continue
                box = line.get("box", [])
                if not box:
                    top = float(line_position * 12)
                    box = [[0.0, top], [100.0, top], [100.0, top + 10], [0.0, top + 10]]
                records.append(
                    {
                        "globalIndex": global_index,
                        "pageIndex": page_index,
                        "lineIndex": int(
                            line.get(
                                "outputIndex",
                                line.get("sourceIndex", line_position),
                            )
                        ),
                        "text": text,
                        "confidence": (
                            float(line["confidence"])
                            if line.get("confidence") is not None
                            else None
                        ),
                        "box": box,
                    }
                )
                global_index += 1
            continue
        texts = page.get("recognizedTexts", [])
        scores = page.get("recognitionScores", [])
        boxes = page.get("recognizedBoxes", [])
        for line_position, text_value in enumerate(texts):
            text = str(text_value).strip()
            if not text:
                continue
            top = float(line_position * 12)
            box = (
                boxes[line_position]
                if line_position < len(boxes)
                else [[0.0, top], [100.0, top], [100.0, top + 10], [0.0, top + 10]]
            )
            records.append(
                {
                    "globalIndex": global_index,
                    "pageIndex": page_index,
                    "lineIndex": line_position,
                    "text": text,
                    "confidence": (
                        float(scores[line_position])
                        if line_position < len(scores)
                        else None
                    ),
                    "box": box,
                }
            )
            global_index += 1
    return records


def _label_score(text: str, label: str) -> float:
    text_key = accent_key(text)
    if not text_key:
        return 0.0
    if label in text_key:
        return 1.0
    if len(label) < 5:
        return 0.0
    sequence_score = difflib.SequenceMatcher(None, text_key, label).ratio()
    label_tokens = set(label.split())
    text_tokens = set(text_key.split())
    coverage = len(label_tokens & text_tokens) / max(1, len(label_tokens))
    return max(sequence_score, coverage * 0.92)


def _best_field_label(line: dict[str, Any]) -> tuple[str | None, float]:
    best_field = None
    best_score = 0.0
    for field_name, spec in FIELD_SPECS.items():
        score = max(
            _label_score(line["text"], label)
            for label in spec["labels"]
        )
        if score > best_score:
            best_field = field_name
            best_score = score
    return best_field, best_score


def _after_colon(text: str) -> str:
    if ":" not in text:
        return ""
    return " ".join(text.rsplit(":", 1)[1].split()).strip(" .;-")


def _normalized_source_map(value: str) -> tuple[str, list[int]]:
    normalized: list[str] = []
    source_indices: list[int] = []
    pending_separator: int | None = None
    for source_index, source_character in enumerate(value):
        folded = source_character.casefold().replace("đ", "d")
        decomposed = unicodedata.normalize("NFD", folded)
        ascii_characters = [
            character
            for character in decomposed
            if unicodedata.category(character) != "Mn"
            and (character.isascii() and character.isalnum())
        ]
        if not ascii_characters:
            pending_separator = source_index
            continue
        if normalized and pending_separator is not None and normalized[-1] != " ":
            normalized.append(" ")
            source_indices.append(pending_separator)
        pending_separator = None
        for character in ascii_characters:
            normalized.append(character)
            source_indices.append(source_index)
    return "".join(normalized).strip(), source_indices[: len(normalized)]


def _exact_label_spans(text: str) -> list[dict[str, Any]]:
    normalized, source_indices = _normalized_source_map(text)
    spans: list[dict[str, Any]] = []
    if not normalized or not source_indices:
        return spans
    for field_name, spec in FIELD_SPECS.items():
        for label in spec["labels"]:
            start = normalized.find(label)
            if start < 0:
                continue
            end = start + len(label)
            if end > len(source_indices):
                continue
            spans.append(
                {
                    "field": field_name,
                    "label": label,
                    "normalizedStart": start,
                    "normalizedEnd": end,
                    "sourceStart": source_indices[start],
                    "sourceEnd": source_indices[end - 1] + 1,
                }
            )
    return spans


def _remove_normalized_prefix(text: str, prefix: str) -> tuple[str, bool]:
    normalized, source_indices = _normalized_source_map(text)
    if not normalized.startswith(prefix) or len(source_indices) < len(prefix):
        return text, False
    source_end = source_indices[len(prefix) - 1] + 1
    return text[source_end:], True


def _clean_field_value_fragment(field_name: str, text: str) -> str:
    """Remove OCR label contamination from a field evidence fragment."""
    cleaned = " ".join(str(text).split()).strip(" \t\r\n/:;,.|-")
    # A fragment returned after a Vietnamese label may still begin with the
    # OCR rendering of the bilingual separator (``I``/``l``).
    cleaned = re.sub(r"^\s*[iIl|]\s+", "", cleaned, count=1)
    aliases = tuple(
        sorted(
            (accent_key(alias) for alias in FIELD_LABEL_ALIASES[field_name]),
            key=len,
            reverse=True,
        )
    )
    removed_label = False
    for _ in range(4):
        normalized, _ = _normalized_source_map(cleaned)
        matched = next(
            (
                alias
                for alias in aliases
                if normalized == alias or normalized.startswith(alias + " ")
            ),
            None,
        )
        if matched is None:
            break
        cleaned, _ = _remove_normalized_prefix(cleaned, matched)
        cleaned = re.sub(r"^\s*[/|:;,.\\-]+\s*", "", cleaned)
        # OCR sometimes renders the slash between Vietnamese and English as a
        # standalone capital I/l. Remove it only after a label was removed.
        cleaned = re.sub(r"^\s*[iIl|]\s+", "", cleaned, count=1)
        removed_label = True

    # Stop before a later confidently recognized schema label in the same OCR
    # line. This is important for the two multiline address fields.
    later_spans = [
        span
        for span in _exact_label_spans(cleaned)
        if span["field"] != field_name and int(span["sourceStart"]) > 0
    ]
    if later_spans:
        boundary = min(int(span["sourceStart"]) for span in later_spans)
        cleaned = cleaned[:boundary]

    if removed_label:
        cleaned = cleaned.strip(" \t\r\n/:;,.|-")
    return " ".join(cleaned.split())


def _labeled_segment(field_name: str, text: str) -> str:
    spans = [
        span for span in _exact_label_spans(text) if span["field"] == field_name
    ]
    if not spans:
        return ""
    current = max(
        spans,
        key=lambda span: (
            len(span["label"]),
            -int(span["normalizedStart"]),
        ),
    )
    later_spans = [
        span
        for span in _exact_label_spans(text)
        if span["field"] != field_name
        and int(span["sourceStart"]) >= int(current["sourceEnd"])
    ]
    segment_end = (
        min(int(span["sourceStart"]) for span in later_spans)
        if later_spans
        else len(text)
    )
    segment = " ".join(
        text[int(current["sourceEnd"]) : segment_end].split()
    ).strip(" \t\r\n/:;,.|-_")
    return _clean_field_value_fragment(field_name, segment)


def _canonical_sex(value: str) -> str:
    key = accent_key(value)
    tokens = key.split()
    cutoff = min(
        (
            tokens.index(token)
            for token in ("quoc", "nationality")
            if token in tokens
        ),
        default=len(tokens),
    )
    candidate_tokens = tokens[:cutoff]
    if "female" in candidate_tokens or "nu" in candidate_tokens:
        return "Nữ"
    if "male" in candidate_tokens or "nam" in candidate_tokens:
        return "Nam"
    return ""


def _canonical_nationality(value: str) -> str:
    key = accent_key(value)
    tokens = key.split()
    compact = key.replace(" ", "")
    if "viet nam" in key or "vietnam" in compact:
        return "Việt Nam"
    for start in range(len(tokens)):
        for width in (1, 2):
            candidate = "".join(tokens[start : start + width])
            if (
                len(candidate) in {5, 6, 7, 8}
                and candidate.startswith("v")
                and difflib.SequenceMatcher(None, candidate, "vietnam").ratio()
                >= (0.72 if len(candidate) == 5 else 0.82)
            ):
                return "Việt Nam"
    return ""


def _normalize_field_value(field_name: str, value: str) -> tuple[str, str | None]:
    normalized = unicodedata.normalize(
        "NFC",
        _clean_field_value_fragment(field_name, value),
    )
    normalized = " ".join(normalized.split()).strip(" \t\r\n/:;.|-_")
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    normalized = re.sub(r"\s*;\s*", "; ", normalized)
    normalized = re.sub(r"\s+([.)])", r"\1", normalized)
    method = None
    if field_name in {"dateOfBirth", "dateOfExpiry"}:
        match = DATE_RE.search(normalized)
        if match:
            date_value = re.sub(r"[.-]", "/", match.group(0))
            if date_value != normalized:
                method = "date_separator"
            normalized = date_value
    elif field_name == "sex":
        canonical = _canonical_sex(normalized)
        if canonical:
            method = "controlled_enum" if canonical != normalized else None
            normalized = canonical
    elif field_name == "nationality":
        canonical = _canonical_nationality(normalized)
        if canonical:
            method = "controlled_enum" if canonical != normalized else None
            normalized = canonical
    return normalized, method


def _extract_inline_value(field_name: str, text: str) -> str:
    if field_name == "identityNumber":
        match = IDENTITY_NUMBER_RE.search(text)
        return re.sub(r"\D", "", match.group(0)) if match else ""
    if field_name in {"dateOfBirth", "dateOfExpiry"}:
        match = DATE_RE.search(text)
        return match.group(0) if match else ""
    segment = _labeled_segment(field_name, text)
    if field_name == "sex":
        canonical = _canonical_sex(segment)
        return canonical or ""
    if field_name == "nationality":
        canonical = _canonical_nationality(segment)
        return canonical or ""
    return segment or _after_colon(text)


def _candidate_text_value(field_name: str, text: str) -> str:
    if field_name == "identityNumber":
        match = IDENTITY_NUMBER_RE.search(text)
        return re.sub(r"\D", "", match.group(0)) if match else ""
    if field_name in {"dateOfBirth", "dateOfExpiry"}:
        match = DATE_RE.search(text)
        return match.group(0) if match else ""
    if field_name == "sex":
        segment = _labeled_segment(field_name, text) or text
        return _canonical_sex(segment)
    if field_name == "nationality":
        segment = _labeled_segment(field_name, text) or text
        return _canonical_nationality(segment)
    value, _ = _normalize_field_value(field_name, text)
    key = accent_key(value)
    if any(
        rejected in key
        for rejected in (
            "can cuoc cong dan",
            "citizen identity card",
            "cong hoa xa hoi",
            "socialist republic",
            "doc lap tu do",
        )
    ):
        return ""
    if field_name == "fullName":
        valid, _ = _validate_value(field_name, value)
        return value if valid and len(value) <= 80 else ""
    if field_name in {"placeOfOrigin", "placeOfResidence"}:
        alpha_words = [
            word for word in value.split() if any(character.isalpha() for character in word)
        ]
        if len(alpha_words) < 2 or DATE_RE.search(value):
            return ""
    return value


def _vertical_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    overlap = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    denominator = max(1.0, min(first[3] - first[1], second[3] - second[1]))
    return overlap / denominator


def _candidate_lines(
    anchor: dict[str, Any],
    records: list[dict[str, Any]],
    multiline: bool,
    field_name: str,
    stop_y: float | None = None,
) -> list[dict[str, Any]]:
    anchor_bounds = _bounds(anchor["box"])
    anchor_height = max(8.0, anchor_bounds[3] - anchor_bounds[1])
    same_row: list[tuple[float, dict[str, Any]]] = []
    below: list[tuple[float, dict[str, Any]]] = []
    for candidate in records:
        if (
            candidate["globalIndex"] == anchor["globalIndex"]
            or candidate["pageIndex"] != anchor["pageIndex"]
        ):
            continue
        _, candidate_label_score = _best_field_label(candidate)
        if candidate_label_score >= 0.72:
            continue
        candidate_value = _candidate_text_value(field_name, candidate["text"])
        if not candidate_value:
            continue
        candidate_bounds = _bounds(candidate["box"])
        if stop_y is not None and candidate_bounds[1] >= stop_y:
            continue
        if (
            candidate_bounds[0] >= anchor_bounds[0] + (anchor_bounds[2] - anchor_bounds[0]) * 0.30
            and _vertical_overlap(anchor_bounds, candidate_bounds) >= 0.30
        ):
            distance = max(0.0, candidate_bounds[0] - anchor_bounds[2])
            same_row.append(
                (
                    distance
                    - min(1.0, float(candidate.get("confidence") or 0.0))
                    * anchor_height,
                    candidate,
                )
            )
            continue
        vertical_distance = candidate_bounds[1] - anchor_bounds[3]
        horizontal_tolerance = max(
            anchor_bounds[2] - anchor_bounds[0],
            candidate_bounds[2] - candidate_bounds[0],
        )
        if (
            -anchor_height * 0.20 <= vertical_distance <= anchor_height * 5.0
            and candidate_bounds[2] >= anchor_bounds[0] - horizontal_tolerance * 0.35
            and candidate_bounds[0] <= anchor_bounds[2] + horizontal_tolerance * 0.75
        ):
            x_distance = abs(candidate_bounds[0] - anchor_bounds[0])
            below.append(
                (
                    max(0.0, vertical_distance)
                    + x_distance * 0.05
                    - min(1.0, float(candidate.get("confidence") or 0.0))
                    * anchor_height,
                    candidate,
                )
            )
    if same_row and field_name not in {
        "fullName",
        "placeOfOrigin",
        "placeOfResidence",
    }:
        return [min(same_row, key=lambda item: item[0])[1]]
    ordered_below = [item[1] for item in sorted(below, key=lambda item: item[0])]
    if multiline:
        ordered_below.sort(
            key=lambda candidate: (
                _bounds(candidate["box"])[1],
                _bounds(candidate["box"])[0],
            )
        )
        return ordered_below[:3]
    if ordered_below:
        return ordered_below[:1]
    return [min(same_row, key=lambda item: item[0])[1]] if same_row else []


def _loose_candidate_lines(
    anchor: dict[str, Any],
    records: list[dict[str, Any]],
    multiline: bool,
    stop_y: float | None,
    field_name: str,
) -> list[dict[str, Any]]:
    """Retain nearby OCR evidence as review-only when strict parsing finds none."""
    anchor_bounds = _bounds(anchor["box"])
    anchor_height = max(8.0, anchor_bounds[3] - anchor_bounds[1])
    candidates: list[tuple[float, dict[str, Any]]] = []
    for candidate in records:
        if (
            candidate["globalIndex"] == anchor["globalIndex"]
            or candidate["pageIndex"] != anchor["pageIndex"]
        ):
            continue
        _, candidate_label_score = _best_field_label(candidate)
        if candidate_label_score >= 0.72:
            continue
        text = _candidate_text_value(field_name, candidate["text"])
        if len(text) < 2:
            continue
        candidate_bounds = _bounds(candidate["box"])
        if stop_y is not None and candidate_bounds[1] >= stop_y:
            continue
        same_row = (
            candidate_bounds[0]
            >= anchor_bounds[0] + (anchor_bounds[2] - anchor_bounds[0]) * 0.30
            and _vertical_overlap(anchor_bounds, candidate_bounds) >= 0.30
        )
        vertical_distance = candidate_bounds[1] - anchor_bounds[3]
        below = (
            -anchor_height * 0.20 <= vertical_distance <= anchor_height * 3.2
            and candidate_bounds[2] >= anchor_bounds[0] - anchor_height * 2.0
            and candidate_bounds[0] <= anchor_bounds[2] + anchor_height * 8.0
        )
        if not same_row and not below:
            continue
        distance = (
            abs(candidate_bounds[0] - anchor_bounds[2])
            if same_row
            else max(0.0, vertical_distance)
            + abs(candidate_bounds[0] - anchor_bounds[0]) * 0.05
        )
        candidates.append((distance, candidate))
    ordered = [
        candidate
        for _, candidate in sorted(
            candidates,
            key=lambda item: (
                item[0],
                _bounds(item[1]["box"])[1],
                _bounds(item[1]["box"])[0],
            ),
        )
    ]
    return ordered[:2 if multiline else 1]


def _valid_date(value: str) -> bool:
    for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            datetime.strptime(value, date_format)
            return True
        except ValueError:
            continue
    return False


def _validate_value(field_name: str, value: str) -> tuple[bool, str]:
    normalized = " ".join(value.split()).strip(" .;-")
    if not normalized:
        return False, "empty"
    if field_name == "identityNumber":
        return bool(re.fullmatch(r"\d{12}", normalized)), "twelve_digits"
    if field_name in {"dateOfBirth", "dateOfExpiry"}:
        return _valid_date(normalized), "valid_calendar_date"
    if field_name == "sex":
        return accent_key(normalized) in {"nam", "nu", "male", "female"}, "known_enum"
    if field_name == "nationality":
        return 2 <= len(normalized) <= 40 and not any(ch.isdigit() for ch in normalized), "text"
    if field_name == "fullName":
        words = [word for word in normalized.split() if any(ch.isalpha() for ch in word)]
        return len(words) >= 2 and not any(ch.isdigit() for ch in normalized), "person_name_shape"
    return len(normalized) >= 5, "nonempty_address"


def _field_result(
    field_name: str,
    value: str,
    evidence_lines: list[dict[str, Any]],
    engine: str,
    label_score: float,
    force_review: bool = False,
    selection_mode: str = "strict",
) -> dict[str, Any]:
    raw_value = " ".join(value.split()).strip()
    value, normalization_method = _normalize_field_value(field_name, raw_value)
    confidences = [
        float(line["confidence"])
        for line in evidence_lines
        if line.get("confidence") is not None
    ]
    confidence = min(confidences) if confidences else None
    valid, validation_rule = _validate_value(field_name, value)
    threshold = float(FIELD_SPECS[field_name]["threshold"])
    accepted = (
        valid
        and confidence is not None
        and confidence >= threshold
        and not force_review
    )
    status = "accepted" if accepted else "needs_review"
    return {
        "value": value,
        "confidence": round(confidence, 6) if confidence is not None else None,
        "status": status,
        "validation": {
            "valid": valid,
            "rule": validation_rule,
            "confidenceThreshold": threshold,
            "labelMatchScore": round(label_score, 6),
            "selectionMode": selection_mode,
        },
        "normalization": {
            "applied": normalization_method is not None,
            "method": normalization_method,
        },
        "evidence": {
            "engine": engine,
            "pageIndex": evidence_lines[0]["pageIndex"],
            "lineIndices": [line["lineIndex"] for line in evidence_lines],
            "bbox": _box_union(evidence_lines),
            "texts": [line["text"] for line in evidence_lines],
        },
    }


def extract_cccd_fields(
    pages: list[dict[str, Any]],
    engine: str,
) -> dict[str, Any]:
    records = _line_records(pages)
    anchors: dict[str, tuple[dict[str, Any], float]] = {}
    for record in records:
        for field_name, spec in FIELD_SPECS.items():
            # ``date of birth`` and ``date of expiry`` are close enough for a
            # fuzzy label score to cross-match. Require the expiry-specific
            # Vietnamese or English anchor before considering that field.
            if field_name == "dateOfExpiry":
                record_key = accent_key(record["text"])
                if "co gia tri den" not in record_key and "date of expiry" not in record_key:
                    continue
            score = max(_label_score(record["text"], label) for label in spec["labels"])
            if score >= float(spec["labelThreshold"]) and (
                field_name not in anchors or score > anchors[field_name][1]
            ):
                anchors[field_name] = (record, score)

    fields: dict[str, dict[str, Any]] = {}
    used_value_lines: set[int] = set()
    for field_name in FIELD_ORDER:
        spec = FIELD_SPECS[field_name]
        anchor_pair = anchors.get(field_name)
        value = ""
        evidence_lines: list[dict[str, Any]] = []
        label_score = 0.0
        force_review = False
        selection_mode = "strict"
        stop_y: float | None = None
        if anchor_pair:
            anchor, label_score = anchor_pair
            inline_value = _extract_inline_value(field_name, anchor["text"])
            anchor_bounds = _bounds(anchor["box"])
            stopping_fields = {
                "fullName": {
                    "dateOfBirth",
                    "sex",
                    "nationality",
                    "placeOfOrigin",
                },
                "dateOfBirth": {"sex", "nationality", "placeOfOrigin"},
                "sex": {"nationality", "placeOfOrigin"},
                "nationality": {"placeOfOrigin"},
                "placeOfOrigin": {"placeOfResidence", "dateOfExpiry"},
                "placeOfResidence": {"dateOfExpiry"},
            }.get(field_name, set())
            following_anchor_tops = [
                _bounds(other_anchor["box"])[1]
                for other_field, (other_anchor, _) in anchors.items()
                if other_field in stopping_fields
                and other_anchor["pageIndex"] == anchor["pageIndex"]
                and _bounds(other_anchor["box"])[1]
                > anchor_bounds[3] + max(4.0, anchor_bounds[3] - anchor_bounds[1]) * 0.25
            ]
            stop_y = min(following_anchor_tops) if following_anchor_tops else None
            candidates = [
                candidate
                for candidate in _candidate_lines(
                    anchor,
                    records,
                    bool(spec["multiline"]),
                    field_name,
                    stop_y,
                )
                if candidate["globalIndex"] not in used_value_lines
            ]
            if field_name == "fullName" and candidates:
                evidence_lines = [anchor, candidates[0]]
                value = _candidate_text_value(field_name, candidates[0]["text"])
                used_value_lines.add(candidates[0]["globalIndex"])
            elif inline_value:
                value = inline_value
                evidence_lines = [anchor]
                if bool(spec["multiline"]) and candidates:
                    candidate_values = [
                        _candidate_text_value(field_name, candidate["text"])
                        for candidate in candidates
                    ]
                    candidate_values = [
                        candidate_value
                        for candidate_value in candidate_values
                        if candidate_value
                    ]
                    if candidate_values:
                        value = " ".join([value, *candidate_values])
                        evidence_lines.extend(candidates)
                        used_value_lines.update(
                            candidate["globalIndex"] for candidate in candidates
                        )
            else:
                if candidates:
                    evidence_lines = [anchor, *candidates]
                    value = " ".join(
                        candidate_value
                        for candidate_value in (
                            _candidate_text_value(field_name, candidate["text"])
                            for candidate in candidates
                        )
                        if candidate_value
                    )
                    used_value_lines.update(
                        candidate["globalIndex"] for candidate in candidates
                    )
        if not value and field_name == "identityNumber":
            regex_candidates = [
                record for record in records if IDENTITY_NUMBER_RE.search(record["text"])
            ]
            if regex_candidates:
                candidate = max(
                    regex_candidates,
                    key=lambda line: line.get("confidence") or 0.0,
                )
                match = IDENTITY_NUMBER_RE.search(candidate["text"])
                value = re.sub(r"\D", "", match.group(0)) if match else ""
                evidence_lines = [candidate]
                label_score = 0.0
        if not value and field_name in {"sex", "nationality"}:
            # Do not scan the whole page for an enum: a value from another
            # section (or a bilingual label) is not evidence for this field.
            context_pair = anchors.get(field_name) or anchors.get("dateOfBirth")
            enum_candidates: list[tuple[float, dict[str, Any], str]] = []
            if context_pair:
                context_anchor = context_pair[0]
                context_bounds = _bounds(context_anchor["box"])
                context_height = max(8.0, context_bounds[3] - context_bounds[1])
                for record in records:
                    if (
                        record["globalIndex"] == context_anchor["globalIndex"]
                        or record["pageIndex"] != context_anchor["pageIndex"]
                    ):
                        continue
                    record_bounds = _bounds(record["box"])
                    vertical_distance = record_bounds[1] - context_bounds[3]
                    same_row = _vertical_overlap(context_bounds, record_bounds) >= 0.25
                    nearby_below = (
                        -context_height * 0.20
                        <= vertical_distance
                        <= context_height * 2.5
                        and record_bounds[2]
                        >= context_bounds[0] - context_height * 2.0
                        and record_bounds[0]
                        <= context_bounds[2] + context_height * 2.0
                    )
                    if not same_row and not nearby_below:
                        continue
                    candidate_value = _candidate_text_value(
                        field_name,
                        record["text"],
                    )
                    if not candidate_value:
                        continue
                    enum_candidates.append(
                        (
                            float(record.get("confidence") or 0.0),
                            record,
                            candidate_value,
                        )
                    )
            if enum_candidates:
                _, candidate, value = max(enum_candidates, key=lambda item: item[0])
                evidence_lines = [candidate]
                label_score = context_pair[1] if context_pair else 0.0
                force_review = True
                selection_mode = "context_enum_fallback"
        if (
            not value
            and anchor_pair
            and field_name
            in {"fullName", "placeOfOrigin", "placeOfResidence"}
        ):
            anchor, label_score = anchor_pair
            fallback_candidates = [
                candidate
                for candidate in (
                    _candidate_lines(
                        anchor,
                        records,
                        False,
                        field_name,
                        None,
                    )
                    if field_name == "fullName"
                    else _loose_candidate_lines(
                        anchor,
                        records,
                        bool(spec["multiline"]),
                        stop_y,
                        field_name,
                    )
                )
                if candidate["globalIndex"] not in used_value_lines
            ]
            if fallback_candidates:
                evidence_lines = [anchor, *fallback_candidates]
                value = " ".join(
                    candidate["text"] for candidate in fallback_candidates
                )
                force_review = True
                selection_mode = "loose_spatial_fallback"
        if value and evidence_lines:
            fields[field_name] = _field_result(
                field_name,
                value,
                evidence_lines,
                engine,
                label_score,
                force_review,
                selection_mode,
            )
        else:
            fields[field_name] = {
                "value": None,
                "confidence": None,
                "status": "not_found",
                "validation": {
                    "valid": False,
                    "rule": "no_ocr_evidence",
                    "confidenceThreshold": float(spec["threshold"]),
                    "labelMatchScore": round(label_score, 6),
                },
                "evidence": None,
            }

    present_count = sum(field["value"] is not None for field in fields.values())
    accepted_count = sum(field["status"] == "accepted" for field in fields.values())
    review_count = sum(field["status"] == "needs_review" for field in fields.values())
    not_found_count = sum(field["status"] == "not_found" for field in fields.values())
    return {
        "schemaVersion": OCR_HO_V2_VERSION,
        "recognizerVersion": OCR_HO_V2_VERSION,
        "documentType": "VIETNAM_CITIZEN_ID_FRONT",
        "orientationPolicy": ORIENTATION_POLICY,
        "evaluationScope": "DEVELOPMENT_ONLY",
        "extractionPolicy": (
            "ocr_evidence_with_label_boundary_and_deterministic_normalization"
        ),
        "fields": fields,
        "summary": {
            "expectedFieldCount": len(FIELD_ORDER),
            "presentFieldCount": present_count,
            "acceptedFieldCount": accepted_count,
            "needsReviewFieldCount": review_count,
            "notFoundFieldCount": not_found_count,
            "documentCompleteness": round(present_count / len(FIELD_ORDER), 6),
            "acceptedRate": round(accepted_count / len(FIELD_ORDER), 6),
            "readyForAutomaticUse": False,
            "manualReviewRequired": True,
        },
    }


def _metric_value(field: Any) -> str:
    if isinstance(field, dict):
        value = field.get("value")
    else:
        value = field
    return str(value).strip() if value is not None else ""


def _normalize_metric_value(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def evaluate_field_predictions(
    ground_truth_fields: dict[str, Any],
    predicted_fields: dict[str, Any],
) -> dict[str, Any]:
    """Return PII-free per-field and aggregate metrics."""
    fields = [
        field_name
        for field_name in FIELD_ORDER
        if _metric_value(ground_truth_fields.get(field_name))
    ]
    per_field: dict[str, dict[str, bool]] = {}
    exact_count = 0
    present_count = 0
    for field_name in fields:
        expected = _normalize_metric_value(
            _metric_value(ground_truth_fields.get(field_name))
        )
        predicted = _normalize_metric_value(
            _metric_value(predicted_fields.get(field_name))
        )
        present = bool(predicted)
        exact = present and predicted == expected
        present_count += present
        exact_count += exact
        per_field[field_name] = {
            "present": present,
            "exactMatch": exact,
        }
    count = len(fields)
    return {
        "groundTruthFieldCount": count,
        "exactMatchCount": exact_count,
        "presentFieldCount": present_count,
        "fieldExactMatch": round(exact_count / max(1, count), 6),
        "documentCompleteness": round(present_count / max(1, count), 6),
        "allFieldsExact": bool(count and exact_count == count),
        "allFieldsPresent": bool(count and present_count == count),
        "perField": per_field,
    }
