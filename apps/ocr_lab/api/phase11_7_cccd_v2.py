"""OCR-HO-V2-007 address ROI and Vietnamese Unicode recovery candidate.

This is a shadow-only development policy.  It tightens the two address bands
around the label line (including values that begin on the same line), repairs
only reversible mojibake, and prefers independently supported Unicode OCR
evidence.  No value is created from Ground Truth, a directory, or a sibling
document; all output remains ``MANUAL_REVIEW``.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

import phase11_5_cccd as phase11_5
import phase11_6_cccd as phase11_6
from phase11_cccd import FIELD_ORDER, _bounds

CANDIDATE_VERSION = "11.7.1"
SCHEMA_VERSION = phase11_6.SCHEMA_VERSION
POLICY_ID = "phase11.7-v2-address-roi-unicode-recovery"
TARGET_FIELDS = ("placeOfOrigin", "placeOfResidence")
PROTECTED_FIELDS = tuple(name for name in FIELD_ORDER if name not in TARGET_FIELDS)

ADDRESS_FALLBACK_ROIS = {
    **phase11_6.PHASE11_6_ROIS,
    # Used only when neither address label can be found.  The label-aware
    # bands below take precedence and are intentionally non-overlapping.
    "placeOfOrigin": (0.25, 0.60, 0.99, 0.82),
    "placeOfResidence": (0.24, 0.72, 0.99, 0.99),
}

_DATE_RE = phase11_5.DATE_RE
_ADDRESS_LABELS = {
    "placeOfOrigin": (
        "que quan",
        "place of origin",
        "place of orign",
        "place of origi",
    ),
    "placeOfResidence": (
        "noi thuong tru",
        "place of residence",
        "place of residen",
        "place of residenc",
    ),
}
_EXPIRY_LABELS = ("co gia tri den", "date of expiry", "date of expiri")
_MOJIBAKE_MARKERS = ("Ã", "Â", "Ä", "Æ", "á»", "â")


def build_crop_variants(page_image: Any, bbox: list[int]) -> dict[str, dict[str, Any]]:
    return phase11_5.build_crop_variants(page_image, bbox)


def _marker_count(value: str) -> int:
    return sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)


def repair_unicode(value: Any) -> str:
    """Repair only a reversible UTF-8/Latin-1 decoding artifact."""

    text = phase11_5.nfc_text(value)
    for _ in range(2):
        if _marker_count(text) == 0:
            break
        try:
            repaired = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if _marker_count(repaired) >= _marker_count(text):
            break
        text = phase11_5.nfc_text(repaired)
    return text


def _label_view(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", phase11_5.ascii_text(value).casefold()).strip()


def _find_label_span(
    text: str,
    labels: tuple[str, ...],
    start: int = 0,
) -> tuple[int, int] | None:
    view = phase11_5.ascii_text(text).casefold()
    matches: list[tuple[int, int]] = []
    for label in labels:
        tokens = [re.escape(token) for token in label.split()]
        pattern = r"\b" + r"\W+".join(tokens) + r"\b"
        match = re.search(pattern, view[start:], flags=re.IGNORECASE)
        if match:
            matches.append((start + match.start(), start + match.end()))
    return min(matches) if matches else None


def _strip_address_labels(field_name: str, value: str) -> str:
    text = repair_unicode(value)
    if field_name == "placeOfResidence":
        origin_span = _find_label_span(text, _ADDRESS_LABELS["placeOfOrigin"])
        residence_span = _find_label_span(text, _ADDRESS_LABELS[field_name])
        if origin_span and residence_span and residence_span[0] > origin_span[0]:
            # A crop that began one line too early: discard the origin label
            # and value before the residence label.
            text = text[residence_span[0] :]
    current_span = _find_label_span(text, _ADDRESS_LABELS[field_name])
    if current_span and current_span[0] <= 8:
        text = text[current_span[1] :]
    text = text.lstrip(" :;/|.-")
    current_span = _find_label_span(text, _ADDRESS_LABELS[field_name])
    if current_span and current_span[0] <= 8:
        text = text[current_span[1] :]
    for labels in (_ADDRESS_LABELS["placeOfResidence"], _EXPIRY_LABELS):
        boundary = _find_label_span(text, labels)
        if boundary:
            text = text[: boundary[0]]
    # Remove a current English label if the Vietnamese half was not decoded.
    text = re.sub(
        r"^(?:place\s+of\s+(?:origin|orign|origi|residence|residen\w*))\s*[:/|;.-]*",
        "",
        phase11_5.nfc_text(text),
        flags=re.IGNORECASE,
    )
    text = _DATE_RE.sub("", text)
    return repair_unicode(text).strip(" :;/|.-")


def field_candidate(field_name: str, raw_text: Any) -> str:
    if field_name not in TARGET_FIELDS:
        return phase11_6.field_candidate(field_name, raw_text)
    return _strip_address_labels(field_name, phase11_6.field_candidate(field_name, raw_text))


def _address_bbox(
    field_name: str,
    anchor: dict[str, Any],
    next_anchor: dict[str, Any] | None,
    fallback: list[int],
    *,
    height: int,
) -> list[int]:
    _, top, _, bottom = _bounds(anchor["box"])
    line_height = max(10.0, bottom - top)
    # Values often begin to the right of the bilingual label on the same row.
    start = max(0, int(top - line_height * 0.18))
    maximum = min(height, int(bottom + line_height * 2.8))
    if next_anchor is not None:
        next_top = _bounds(next_anchor["box"])[1]
        if next_top > start:
            maximum = min(maximum, int(next_top - line_height * 0.08))
    return [fallback[0], start, fallback[2], max(start + 1, maximum)]


def locate_field_regions(
    pages: list[dict[str, Any]],
    page_sizes: list[tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    if not page_sizes:
        return {}
    width, height = page_sizes[0]
    regions = phase11_6.locate_field_regions(pages, page_sizes)
    anchors = phase11_6._label_anchors(pages)
    for field_name in TARGET_FIELDS:
        x0, y0, x1, y1 = ADDRESS_FALLBACK_ROIS[field_name]
        fallback = [int(width * x0), int(height * y0), int(width * x1), int(height * y1)]
        anchor = anchors.get(field_name)
        next_name = "placeOfResidence" if field_name == "placeOfOrigin" else "dateOfExpiry"
        # The expiry label is on the left edge and can share the vertical band
        # of a two-line residence value.  It must not truncate that address.
        next_anchor = anchors.get(next_name) if field_name == "placeOfOrigin" else None
        if anchor:
            bbox = _address_bbox(
                field_name,
                anchor,
                next_anchor,
                fallback,
                height=height,
            )
            source = "phase11_7_address_label_band"
        elif field_name == "placeOfOrigin" and anchors.get("placeOfResidence"):
            # If OCR missed the origin label, the residence anchor still gives
            # a reliable vertical reference for the preceding address line.
            residence = anchors["placeOfResidence"]
            _, residence_top, _, residence_bottom = _bounds(residence["box"])
            line_height = max(10.0, residence_bottom - residence_top)
            bbox = [
                fallback[0],
                max(0, int(residence_top - line_height * 1.65)),
                fallback[2],
                min(height, int(residence_top + line_height * 0.12)),
            ]
            source = "phase11_7_origin_inferred_from_residence"
        elif field_name == "placeOfResidence" and anchors.get("placeOfOrigin"):
            origin = anchors["placeOfOrigin"]
            _, origin_top, _, origin_bottom = _bounds(origin["box"])
            line_height = max(10.0, origin_bottom - origin_top)
            start = int(origin_bottom + line_height * 0.65)
            bbox = [
                fallback[0],
                min(height - 1, start),
                fallback[2],
                min(height, int(start + line_height * 3.2)),
            ]
            source = "phase11_7_residence_inferred_from_origin"
        else:
            bbox = fallback
            source = "phase11_7_address_normalized_fallback"
        regions[field_name] = {
            "pageIndex": 0,
            "bbox": bbox,
            "normalizedBbox": [x0, y0, x1, y1],
            "regionSource": source,
            "labelMatchScore": 1.0 if anchor else 0.0,
            "maxValueLines": 2,
        }
    return regions


def _family(profile: Any) -> str:
    normalized = str(profile or "").casefold()
    if "vietocr" in normalized:
        return "vietocr"
    if "easyocr" in normalized:
        return "easyocr"
    if "paddle" in normalized:
        return "paddle"
    return normalized or "unknown"


def _profile_weight(profile: Any) -> int:
    normalized = str(profile or "").casefold()
    if "vietocr_vgg_transformer" in normalized:
        return 4
    if "vietocr_vgg_seq2seq" in normalized:
        return 3
    if "paddle" in normalized:
        return 2
    if "easyocr" in normalized:
        return 1
    return 0


def _address_key(value: str) -> str:
    return re.sub(r"[\s,;:./-]+", " ", phase11_5.base_key(value)).strip()


def _safe_address(value: str) -> tuple[bool, str]:
    valid, rule = phase11_5.validate_field("placeOfOrigin", value)
    if not valid:
        valid, rule = phase11_5.validate_field("placeOfResidence", value)
    if not valid:
        return False, rule
    normalized = _label_view(value)
    if any(
        label in normalized
        for labels in (_ADDRESS_LABELS["placeOfOrigin"], _ADDRESS_LABELS["placeOfResidence"])
        for label in labels
    ):
        return False, "label_contamination"
    return True, rule


def select_address_candidate(
    field_name: str,
    candidates: list[dict[str, Any]],
    *,
    bbox: list[int] | None,
    page_index: int = 0,
) -> dict[str, Any]:
    usable: list[dict[str, Any]] = []
    for raw in candidates:
        cleaned = field_candidate(field_name, raw.get("rawValue") or raw.get("value"))
        if not cleaned:
            continue
        safe, rule = _safe_address(cleaned)
        if not safe:
            continue
        item = dict(raw)
        item.update(
            {
                "value": cleaned,
                "rawValue": raw.get("rawValue") or raw.get("value"),
                "profile": str(raw.get("profile") or raw.get("engine") or "unknown"),
                "family": _family(raw.get("profile") or raw.get("engine")),
                "profileWeight": _profile_weight(raw.get("profile") or raw.get("engine")),
                "validationRule": rule,
                "unicodeEvidence": phase11_5.ascii_text(cleaned) != cleaned,
            }
        )
        usable.append(item)
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
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in usable:
        groups[_address_key(item["value"])].append(item)

    def rank(group: tuple[str, list[dict[str, Any]]]) -> tuple[int, int, int, int, float]:
        _, members = group
        families = {member["family"] for member in members}
        unicode_count = sum(bool(member["unicodeEvidence"]) for member in members)
        confidence = sum(
            float(member.get("confidence") or 0.0) for member in members
        ) / len(members)
        return (
            len(families),
            unicode_count,
            len(members),
            sum(member["profileWeight"] for member in members),
            confidence,
        )

    key, members = max(groups.items(), key=rank)
    families = {member["family"] for member in members}
    if not key or len(members) < 2 or len(families) < 2:
        return {
            "value": None,
            "asciiValue": None,
            "status": "not_found",
            "asciiStatus": "not_found",
            "confidence": 0.0,
            "errorSignals": ["insufficient_independent_support"],
            "selectionMode": "phase11_7_insufficient_consensus",
            "evidence": {"pageIndex": page_index, "bbox": bbox or [], "candidates": usable},
        }
    selected = max(
        members,
        key=lambda item: (
            bool(item["unicodeEvidence"]),
            sum(char != phase11_5.ascii_text(char) for char in item["value"]),
            item["profileWeight"],
            float(item.get("confidence") or 0.0),
        ),
    )
    return {
        "value": repair_unicode(selected["value"]),
        "asciiValue": phase11_5.ascii_text(selected["value"]),
        "status": "needs_review",
        "asciiStatus": "verified_base_text" if len(families) >= 2 else "needs_review",
        "confidence": round(
            min(float(item.get("confidence") or 0.0) for item in members),
            6,
        ),
        "errorSignals": [],
        "selectionMode": "phase11_7_address_unicode_consensus",
        "validation": {
            "valid": True,
            "rule": "address_shape",
            "unicodeEvidenceRequired": True,
            "unicodeEvidencePresent": bool(selected["unicodeEvidence"]),
            "supportingRecognizerCount": len({str(item["profile"]) for item in members}),
            "supportingRecognizerFamilyCount": len(families),
        },
        "evidence": {"pageIndex": page_index, "bbox": bbox or [], "candidates": usable},
    }


def _baseline_needs_recovery(
    field_name: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    value = repair_unicode(baseline.get("value"))
    if not value:
        return True
    if any(
        signal in {"label_contamination", "region_or_line_merge"}
        for signal in baseline.get("errorSignals", [])
    ):
        return True
    safe, _ = _safe_address(value)
    if not safe:
        return True
    return bool(
        candidate.get("validation", {}).get("unicodeEvidencePresent")
        and phase11_5.ascii_text(value) == value
    )


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
                fields[field_name] = _manual_field(
                    candidate,
                    "phase11_6_single_candidate",
                )
                fields[field_name]["policyVersion"] = CANDIDATE_VERSION
                fields[field_name]["policyMode"] = "SHADOW_REVIEW_ONLY"
                continue
            if baseline.get("value") is not None:
                baseline["phase11_7Candidate"] = candidate
                fields[field_name] = _manual_field(
                    baseline,
                    "phase11_6_baseline_preserved",
                )
                continue
            fields[field_name] = _manual_field(
                candidate,
                "phase11_6_single_candidate",
            )
            continue
        fields[field_name] = _manual_field(
            baseline,
            "phase11_6_baseline_preserved",
        )
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
