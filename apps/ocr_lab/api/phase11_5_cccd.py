"""Phase 11.5 CCCD field recognition policy.

The module is intentionally deterministic: OCR evidence may be ranked and
validated, but Ground Truth and language-model guesses are never inputs.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Any

import cv2
import numpy as np
from phase11_cccd import FIELD_ORDER, FIELD_SPECS, _bounds, _label_score

SCHEMA_VERSION = "11.5.0"
POLICY_ID = "phase11.5-cccd-multirecognizer-consensus"

# Coordinates are relative to the already oriented/canonicalized front side.
# They deliberately include the bilingual label so a recognizer can retain
# layout evidence; field-specific cleaning removes the label afterwards.
FRONT_FIELD_ROIS: dict[str, tuple[float, float, float, float]] = {
    "identityNumber": (0.27, 0.29, 0.86, 0.50),
    "fullName": (0.27, 0.40, 0.90, 0.62),
    "dateOfBirth": (0.27, 0.53, 0.80, 0.70),
    "sex": (0.25, 0.59, 0.63, 0.76),
    "nationality": (0.53, 0.58, 0.99, 0.76),
    "placeOfOrigin": (0.25, 0.66, 0.99, 0.86),
    "placeOfResidence": (0.24, 0.75, 0.99, 0.99),
    "dateOfExpiry": (0.00, 0.76, 0.46, 0.99),
}
ROI_REFINEMENT = {
    "defaultTopPaddingLineRatio": 0.05,
    "expiryTopPaddingLineRatio": 1.55,
    "nextLabelBottomGapLineRatio": 0.05,
}

DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
IDENTITY_RE = re.compile(r"(?<!\d)\d(?:[\s.]?\d){11}(?!\d)")
LABEL_PATTERNS: dict[str, tuple[str, ...]] = {
    "identityNumber": (r"s[ốo]\s*/?\s*no\.?", r"\bno\.?"),
    "fullName": (r"h[ọo]\s+v[aà]\s+t[eê]n", r"full\s*name"),
    "dateOfBirth": (r"ng[aà]y\s+sinh", r"date\s+of\s+birth"),
    "sex": (r"gi[ớo]i\s+t[ií]nh", r"\bsex\b"),
    "nationality": (r"qu[ốo]c\s+t[iị]ch", r"nationality"),
    "placeOfOrigin": (r"qu[eê]\s+qu[aá]n", r"place\s+of\s+origin"),
    "placeOfResidence": (
        r"n[ơo]i\s+th[ưuoờ]ng\s+tr[uú]",
        r"place\s+of\s+residence",
    ),
    "dateOfExpiry": (
        r"c[oó]\s+gi[aá]\s+tr[iị]\s+đ[eế]n",
        r"date\s+of\s+expir(?:y|i)",
    ),
}
NEXT_LABELS: dict[str, tuple[str, ...]] = {
    "fullName": ("dateOfBirth",),
    "dateOfBirth": ("sex", "nationality"),
    "sex": ("nationality", "placeOfOrigin"),
    "nationality": ("placeOfOrigin",),
    "placeOfOrigin": ("placeOfResidence",),
    "placeOfResidence": ("dateOfExpiry",),
}


def nfc_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split())


def ascii_text(value: Any) -> str:
    decomposed = unicodedata.normalize("NFD", nfc_text(value))
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return stripped.translate(str.maketrans({"đ": "d", "Đ": "D"}))


def agreement_key(value: Any) -> str:
    text = nfc_text(value).casefold()
    text = re.sub(r"\s*([,;:])\s*", r"\1", text)
    return " ".join(text.split()).strip(" .;,|")


def base_key(value: Any) -> str:
    return agreement_key(ascii_text(value))


def engine_profile(candidate: dict[str, Any]) -> str:
    return str(candidate.get("profile") or candidate.get("engine") or "unknown")


def recognizer_family(profile: str) -> str:
    normalized = profile.casefold()
    if "vietocr" in normalized:
        return "vietocr"
    if "easyocr" in normalized:
        return "easyocr"
    if "paddle" in normalized:
        return "paddle"
    return normalized


def locate_field_regions(
    pages: list[dict[str, Any]],
    page_sizes: list[tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    """Locate all eight fields without using any Ground Truth.

    Relative front-card coordinates are the primary profile. OCR label anchors
    refine the vertical band only when the anchor overlaps the expected band.
    """

    if not page_sizes:
        return {}
    width, height = page_sizes[0]
    regions: dict[str, dict[str, Any]] = {}
    anchors: dict[str, tuple[dict[str, Any], float]] = {}
    for page in pages:
        page_index = int(page.get("pageIndex", 0))
        for line_index, (text, box) in enumerate(
            zip(
                page.get("recognizedTexts", []),
                page.get("recognizedBoxes", []),
                strict=False,
            )
        ):
            record = {
                "text": str(text),
                "box": box,
                "pageIndex": page_index,
                "lineIndex": line_index,
            }
            for field_name, spec in FIELD_SPECS.items():
                score = max(_label_score(record["text"], label) for label in spec["labels"])
                if score >= float(spec["labelThreshold"]) and (
                    field_name not in anchors or score > anchors[field_name][1]
                ):
                    anchors[field_name] = (record, score)

    for field_name in FIELD_ORDER:
        x0, y0, x1, y1 = FRONT_FIELD_ROIS[field_name]
        bbox = [
            max(0, int(width * x0)),
            max(0, int(height * y0)),
            min(width, int(width * x1)),
            min(height, int(height * y1)),
        ]
        source = "front_card_normalized_template"
        label_score = 0.0
        anchor_pair = anchors.get(field_name)
        if anchor_pair:
            anchor, label_score = anchor_pair
            left, top, right, bottom = _bounds(anchor["box"])
            anchor_center_y = (top + bottom) / 2
            expected_center_y = (bbox[1] + bbox[3]) / 2
            tolerance = max(height * 0.13, bbox[3] - bbox[1])
            if (
                int(anchor["pageIndex"]) == 0
                and abs(anchor_center_y - expected_center_y) <= tolerance
            ):
                line_height = max(10.0, bottom - top)
                bbox[0] = max(0, min(bbox[0], int(left - line_height * 0.8)))
                bbox[1] = max(
                    0,
                    int(
                        top
                        - line_height
                        * (
                            ROI_REFINEMENT["expiryTopPaddingLineRatio"]
                            if field_name == "dateOfExpiry"
                            else ROI_REFINEMENT["defaultTopPaddingLineRatio"]
                        )
                    ),
                )
                next_tops = []
                for next_field in NEXT_LABELS.get(field_name, ()):
                    next_anchor = anchors.get(next_field)
                    if not next_anchor:
                        continue
                    next_record = next_anchor[0]
                    next_top = _bounds(next_record["box"])[1]
                    if int(next_record["pageIndex"]) == 0 and next_top > bottom + line_height * 0.4:
                        next_tops.append(next_top)
                if next_tops:
                    bbox[3] = min(
                        bbox[3],
                        int(
                            min(next_tops)
                            - line_height * ROI_REFINEMENT["nextLabelBottomGapLineRatio"]
                        ),
                    )
                else:
                    bbox[3] = min(
                        height,
                        max(bbox[3], int(bottom + line_height * 2.4)),
                    )
                source = "front_card_template_refined_by_label"
        regions[field_name] = {
            "pageIndex": 0,
            "bbox": bbox,
            "normalizedBbox": [x0, y0, x1, y1],
            "regionSource": source,
            "labelMatchScore": round(float(label_score), 6),
        }
    return regions


def build_crop_variants(
    page_image: np.ndarray,
    bbox: list[int],
) -> dict[str, dict[str, Any]]:
    """Create four non-destructive crop views that preserve small accents."""

    height, width = page_image.shape[:2]
    x0, y0, x1, y1 = [int(value) for value in bbox]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    crop = page_image[y0:y1, x0:x1]
    if crop.size == 0:
        return {}
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    lanczos = cv2.resize(
        crop,
        None,
        fx=2.5,
        fy=2.5,
        interpolation=cv2.INTER_LANCZOS4,
    )
    pad_x = max(12, int(crop.shape[1] * 0.08))
    pad_y = max(10, int(crop.shape[0] * 0.12))
    padded = cv2.copyMakeBorder(
        crop,
        pad_y,
        pad_y,
        pad_x,
        pad_x,
        cv2.BORDER_REPLICATE,
    )
    return {
        "color_original": {"image": crop, "scale": 1.0, "padding": [0, 0]},
        "grayscale_clahe": {
            "image": cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR),
            "scale": 1.0,
            "padding": [0, 0],
        },
        "lanczos_upscale": {
            "image": lanczos,
            "scale": 2.5,
            "padding": [0, 0],
        },
        "balanced_padding": {
            "image": padded,
            "scale": 1.0,
            "padding": [pad_x, pad_y],
        },
    }


def _remove_labels(field_name: str, value: str) -> str:
    text = nfc_text(value)
    for next_field in NEXT_LABELS.get(field_name, ()):
        for pattern in LABEL_PATTERNS[next_field]:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                text = text[: match.start()]
    for pattern in LABEL_PATTERNS[field_name]:
        text = re.sub(
            rf"^.*?{pattern}\s*[/|:;.\-]*\s*",
            "",
            text,
            flags=re.IGNORECASE,
            count=1,
        )
    text = re.sub(
        r"^(?:full\s*name|place\s+of\s+(?:origin|residence)|"
        r"date\s+of\s+(?:birth|expir(?:y|i))|nationality|sex)\s*[:/.\-]*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return nfc_text(text).strip(" :;/|.-")


def field_candidate(field_name: str, raw_text: Any) -> str:
    """Extract one field value from a field-only ROI recognition."""

    text = _remove_labels(field_name, nfc_text(raw_text))
    if field_name == "fullName":
        date_match = DATE_RE.search(text)
        if date_match:
            text = nfc_text(text[: date_match.start()])
    if field_name == "identityNumber":
        match = IDENTITY_RE.search(text)
        return re.sub(r"\D", "", match.group(0)) if match else ""
    if field_name in {"dateOfBirth", "dateOfExpiry"}:
        match = DATE_RE.search(text)
        if not match:
            return ""
        value = match.group(0).replace(".", "/").replace("-", "/")
        parts = value.split("/")
        if len(parts[-1]) == 2:
            parts[-1] = f"20{parts[-1]}"
        return "/".join(part.zfill(2) if index < 2 else part for index, part in enumerate(parts))
    if field_name == "sex":
        key = base_key(text)
        if key == "nu":
            return "Nữ" if agreement_key(text) == agreement_key("Nữ") else text
        if key == "nam":
            return "Nam"
        return ""
    if field_name == "nationality":
        match = re.search(r"\bvi[ệe]t\s+nam\b", text, flags=re.IGNORECASE)
        if not match:
            return text
        matched_value = nfc_text(match.group(0))
        return (
            "Việt Nam"
            if agreement_key(matched_value) == agreement_key("Việt Nam")
            else matched_value
        )
    return text


def validate_field(
    field_name: str,
    value: str,
    *,
    date_of_birth: str | None = None,
) -> tuple[bool, str]:
    value = nfc_text(value)
    if not value:
        return False, "empty"
    if field_name == "identityNumber":
        return bool(re.fullmatch(r"\d{12}", value)), "twelve_digits"
    if field_name in {"dateOfBirth", "dateOfExpiry"}:
        try:
            parsed = datetime.strptime(value, "%d/%m/%Y")
        except ValueError:
            return False, "valid_calendar_date"
        if field_name == "dateOfExpiry" and date_of_birth:
            try:
                birth = datetime.strptime(date_of_birth, "%d/%m/%Y")
            except ValueError:
                birth = None
            if birth and (parsed <= birth or parsed.year - birth.year < 10):
                return False, "expiry_after_birth"
        return True, "valid_calendar_date"
    if field_name == "sex":
        return value in {"Nam", "Nữ"}, "known_enum"
    if field_name == "nationality":
        return (
            agreement_key(value) == agreement_key("Việt Nam"),
            "known_nationality",
        )
    words = [word for word in value.split() if any(ch.isalpha() for ch in word)]
    if field_name == "fullName":
        return len(words) >= 2 and not any(ch.isdigit() for ch in value), "person_name_shape"
    return len(words) >= 2 and not DATE_RE.search(value), "address_shape"


def infer_error_signals(
    candidates: list[dict[str, Any]],
    field_name: str | None = None,
) -> list[str]:
    texts = [nfc_text(candidate.get("value")) for candidate in candidates]
    texts = [text for text in texts if text]
    signals: list[str] = []
    raw_texts = [
        nfc_text(candidate.get("rawValue") or candidate.get("value")) for candidate in candidates
    ]
    if field_name and any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for text in raw_texts
        for next_field in NEXT_LABELS.get(field_name, ())
        for pattern in LABEL_PATTERNS[next_field]
    ):
        signals.append("region_or_line_merge")
    if len(texts) < 2:
        return signals
    exact = {agreement_key(text) for text in texts}
    bases = {base_key(text) for text in texts}
    if len(exact) > 1 and len(bases) == 1:
        signals.append("diacritic_disagreement")
    base_values = list(bases)

    def subsequence(shorter: str, longer: str) -> bool:
        characters = iter(longer.replace(" ", ""))
        return all(character in characters for character in shorter.replace(" ", ""))

    if any(
        left != right and (subsequence(left, right) or subsequence(right, left))
        for index, left in enumerate(base_values)
        for right in base_values[index + 1 :]
    ):
        signals.append("character_omission")
    contaminated = any(
        any(
            re.search(pattern, text, flags=re.IGNORECASE)
            for patterns in LABEL_PATTERNS.values()
            for pattern in patterns
        )
        for text in texts
    )
    if contaminated:
        signals.append("label_contamination")
    if len(bases) > 1 and not signals:
        signals.append("character_substitution")
    return list(dict.fromkeys(signals))


def select_field_candidate(
    field_name: str,
    candidates: list[dict[str, Any]],
    *,
    bbox: list[int] | None,
    page_index: int = 0,
    date_of_birth: str | None = None,
) -> dict[str, Any]:
    usable: list[dict[str, Any]] = []
    for raw_candidate in candidates:
        value = field_candidate(field_name, raw_candidate.get("value"))
        if not value:
            continue
        candidate = dict(raw_candidate)
        candidate["value"] = nfc_text(value)
        candidate["profile"] = engine_profile(candidate)
        raw_confidence = float(candidate.get("confidence") or 0.0)
        candidate["confidence"] = round(
            max(0.0, min(1.0, raw_confidence)) if math.isfinite(raw_confidence) else 0.0,
            6,
        )
        usable.append(candidate)
    if not usable:
        return {
            "value": None,
            "asciiValue": None,
            "status": "not_found",
            "asciiStatus": "not_found",
            "confidence": 0.0,
            "errorSignals": ["not_found"],
            "selectionMode": "single_candidate",
            "evidence": {
                "pageIndex": page_index,
                "bbox": bbox or [],
                "candidates": [],
            },
        }

    exact_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    base_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in usable:
        exact_groups[agreement_key(candidate["value"])].append(candidate)
        base_groups[base_key(candidate["value"])].append(candidate)

    def rank_group(
        item: tuple[str, list[dict[str, Any]]],
    ) -> tuple[int, int, int, int, float]:
        _, members = item
        profiles = {engine_profile(member) for member in members}
        families = {recognizer_family(profile) for profile in profiles}
        validation_pass = any(
            validate_field(
                field_name,
                str(member["value"]),
                date_of_birth=date_of_birth,
            )[0]
            for member in members
        )
        confidence = sum(float(member["confidence"]) for member in members) / len(members)
        return int(validation_pass), len(profiles), len(members), len(families), confidence

    _, exact_winner = max(exact_groups.items(), key=rank_group)
    base_winner_key, base_winner = max(base_groups.items(), key=rank_group)
    exact_profiles = {engine_profile(item) for item in exact_winner}
    base_profiles = {engine_profile(item) for item in base_winner}
    exact_families = {recognizer_family(profile) for profile in exact_profiles}
    base_families = {recognizer_family(profile) for profile in base_profiles}
    exact_consensus = len(exact_profiles) >= 2
    base_consensus = len(base_profiles) >= 2
    selected_pool = exact_winner if exact_consensus else base_winner

    def candidate_rank(item: dict[str, Any]) -> tuple[int, float]:
        text = nfc_text(item["value"])
        diacritic_count = sum(character != ascii_text(character) for character in text)
        return diacritic_count, float(item["confidence"])

    selected = max(
        selected_pool,
        key=((lambda item: float(item["confidence"])) if exact_consensus else candidate_rank),
    )
    valid, validation_rule = validate_field(
        field_name,
        selected["value"],
        date_of_birth=date_of_birth,
    )
    signals = infer_error_signals(usable, field_name)
    if exact_consensus:
        selection_mode = "exact_consensus"
    elif base_consensus:
        selection_mode = "base_text_consensus"
        if "diacritic_disagreement" not in signals:
            signals.append("diacritic_disagreement")
    else:
        selection_mode = "single_candidate"
    unicode_evidence_required = field_name in {
        "fullName",
        "nationality",
        "placeOfOrigin",
        "placeOfResidence",
    }
    has_unicode_evidence = ascii_text(selected["value"]) != selected["value"]
    unsafe_signal = any(
        signal in {"label_contamination", "region_or_line_merge"} for signal in signals
    ) or (field_name == "nationality" and bool(signals))
    accepted = (
        exact_consensus
        and len(exact_families) >= 2
        and valid
        and not unsafe_signal
        and (not unicode_evidence_required or has_unicode_evidence)
    )
    ascii_verified = base_consensus and len(base_families) >= 2 and bool(base_winner_key)
    supporting = exact_winner if exact_consensus else base_winner
    return {
        "value": nfc_text(selected["value"]),
        "asciiValue": (
            (
                ascii_text(selected["value"]).upper()
                if field_name == "fullName"
                else ascii_text(selected["value"])
            )
            if ascii_verified
            else ascii_text(selected["value"]) or None
        ),
        "status": "accepted" if accepted else "needs_review",
        "asciiStatus": ("verified_base_text" if ascii_verified else "needs_review"),
        "confidence": round(
            min(float(candidate["confidence"]) for candidate in supporting),
            6,
        ),
        "errorSignals": signals,
        "selectionMode": selection_mode,
        "validation": {
            "valid": valid,
            "rule": validation_rule,
            "unicodeEvidenceRequired": unicode_evidence_required,
            "unicodeEvidencePresent": has_unicode_evidence,
            "supportingRecognizerCount": len({engine_profile(item) for item in supporting}),
            "supportingRecognizerFamilyCount": len(
                {recognizer_family(engine_profile(item)) for item in supporting}
            ),
        },
        "evidence": {
            "pageIndex": page_index,
            "bbox": bbox or [],
            "candidates": usable,
        },
    }


def build_identity_card(
    candidates_by_field: dict[str, list[dict[str, Any]]],
    regions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    fields: dict[str, dict[str, Any]] = {}
    for field_name in FIELD_ORDER:
        region = regions.get(field_name, {})
        fields[field_name] = select_field_candidate(
            field_name,
            candidates_by_field.get(field_name, []),
            bbox=region.get("bbox"),
            page_index=int(region.get("pageIndex", 0)),
            date_of_birth=(
                fields.get("dateOfBirth", {}).get("value") if field_name == "dateOfExpiry" else None
            ),
        )
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


def business_values(identity_card: dict[str, Any]) -> dict[str, Any]:
    """Expose only accepted Unicode values; ASCII remains review metadata."""

    return {
        name: (field.get("value") if field.get("status") == "accepted" else None)
        for name, field in identity_card.get("fields", {}).items()
    }
