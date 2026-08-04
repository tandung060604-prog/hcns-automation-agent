"""Guarded OCR-HO-V2-005 candidate recovery for Vietnamese CCCD fields.

This module is deliberately shadow-only. It ranks OCR candidates already
stored by Phase 11.5, removes bilingual-label/line-merge artifacts, and may
replace a baseline value only when the baseline fails a field-local safety
check and independent recognizer families agree. It never reads Ground Truth,
another document, or a language-model completion.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

from phase11_5_cccd import (
    FIELD_ORDER,
    ascii_text,
    base_key,
    nfc_text,
    validate_field,
)

OCR_HO_V2_005_VERSION = "1.2.0"
OCR_HO_V2_005_POLICY_ID = "ocr-ho-v2-005-guarded-vietnamese-candidate-recovery"
OCR_HO_V2_005_SCOPE = "DEVELOPMENT_ONLY"
OCR_HO_V2_005_ORIENTATION_POLICY = "fixed_0_degree"

_DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
_LABELS: dict[str, tuple[str, ...]] = {
    "fullName": ("ho va ten", "full name", "ful name", "fuil name", "funame"),
    "dateOfBirth": ("ngay sinh", "date of birth", "ngay thang nam sinh", "nam sinh"),
    "placeOfOrigin": ("que quan", "place of origin", "place of orign", "place ofigin"),
    "placeOfResidence": (
        "noi thuong tru",
        "place of residence",
        "place of residen",
        "place of residenc",
    ),
}


def _label_text(value: Any) -> str:
    """Return a stable, punctuation-free ASCII label view for boundary checks."""

    return re.sub(r"[^a-z0-9]+", " ", ascii_text(value).casefold()).strip()


def _find_label(text: str, labels: tuple[str, ...]) -> int:
    normalized = ascii_text(text).casefold()
    positions: list[int] = []
    for label in labels:
        tokens = [re.escape(token) for token in label.split()]
        pattern = r"\b" + r"\W*".join(tokens) + r"\b"
        match = re.search(pattern, normalized)
        if match:
            positions.append(match.start())
    return min(positions) if positions else -1


def clean_candidate_value(field_name: str, raw_value: Any) -> str:
    """Remove field labels and neighboring labels without inventing text."""

    text = nfc_text(raw_value)

    def strip_prefix(pattern: str) -> None:
        nonlocal text
        match = re.search(pattern, ascii_text(text), flags=re.IGNORECASE)
        if match and match.start() <= 2:
            text = text[match.end() :]

    if field_name == "fullName":
        strip_prefix(
            r"(?:ho\s+va\s+ten)\s*[:/|;.-]*\s*"
            r"(?:full\s*name|ful\s*name|fuil\s*name)?\s*[:/|;.-]*"
        )
        strip_prefix(r"(?:full\s*name|ful\s*name|fuil\s*name)\s*[:/|;.-]*")
        boundary = _find_label(text, _LABELS["dateOfBirth"])
        if boundary >= 0:
            text = text[:boundary]
        text = _DATE_RE.split(text, maxsplit=1)[0]
        normalized = _label_text(text)
        if any(label in normalized for label in _LABELS["dateOfBirth"]):
            return ""
        if len(text.split()) < 2 or len(text.split()) > 6 or any(
            character.isdigit() for character in text
        ):
            return ""

    elif field_name == "placeOfOrigin":
        strip_prefix(
            r"(?:que\s+quan)\s*[:/|;.-]*\s*"
            r"(?:place\s+of\s+(?:origin|orign|igin))?\s*[:/|;.-]*"
        )
        strip_prefix(
            r"(?:place\s+of\s+(?:origin|orign|igin))\s*[:/|;.-]*"
        )
        boundary = _find_label(text, _LABELS["placeOfResidence"])
        if boundary >= 0:
            text = text[:boundary]

    elif field_name == "placeOfResidence":
        strip_prefix(
            r"(?:noi\s+thuong\s+tru)\s*[:/|;.-]*\s*"
            r"(?:place\s+of\s+residen\w*)?\s*[:/|;.-]*"
        )
        strip_prefix(r"(?:place\s+of\s+residen\w*)\s*[:/|;.-]*")
        if _find_label(text, _LABELS["placeOfOrigin"]) >= 0:
            # A residence field that only contains the origin label is a
            # region mismatch, not a value that can be safely promoted.
            return ""

    elif field_name == "dateOfExpiry":
        match = _DATE_RE.search(text)
        text = match.group(0) if match else ""

    text = nfc_text(text).strip(" :;/|.-")
    if field_name in {"placeOfOrigin", "placeOfResidence"}:
        text = _DATE_RE.sub("", text)
        text = nfc_text(text).strip(" :;/|.-")
        if len(text.split()) < 2:
            return ""
    return text


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
    if "vietocr_vgg_seq2seq" in normalized:
        return 3
    if "vietocr_vgg_transformer" in normalized or "paddle" in normalized:
        return 2
    if "easyocr" in normalized:
        return 1
    return 0


def _candidate_safety(field_name: str, value: str) -> tuple[bool, str]:
    valid, rule = validate_field(field_name, value)
    if not valid:
        return False, rule
    labels = _LABELS.get(field_name, ())
    normalized = _label_text(value)
    if field_name == "fullName" and any(label in normalized for label in _LABELS["dateOfBirth"]):
        return False, "label_contamination"
    if field_name in {"placeOfOrigin", "placeOfResidence"}:
        all_labels = (
            _LABELS["fullName"]
            + _LABELS["dateOfBirth"]
            + _LABELS["placeOfOrigin"]
            + _LABELS["placeOfResidence"]
        )
        if any(label in normalized for label in all_labels):
            return False, "label_contamination"
    if labels and any(label in normalized for label in labels):
        return False, "label_contamination"
    return True, rule


def _select_recommendation(
    field_name: str,
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    usable: list[dict[str, Any]] = []
    for raw in candidates:
        value = clean_candidate_value(field_name, raw.get("value") or raw.get("rawValue"))
        if not value:
            continue
        safe, validation_rule = _candidate_safety(field_name, value)
        if not safe:
            continue
        item = dict(raw)
        item.update(
            {
                "value": value,
                "profile": str(raw.get("profile") or raw.get("engine") or "unknown"),
                "validationRule": validation_rule,
                "family": _family(raw.get("profile") or raw.get("engine")),
                "profileWeight": _profile_weight(raw.get("profile") or raw.get("engine")),
            }
        )
        usable.append(item)
    if not usable:
        return None, "no_safe_candidate"

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in usable:
        groups[base_key(candidate["value"])].append(candidate)

    def rank(group: tuple[str, list[dict[str, Any]]]) -> tuple[int, int, int, int, float]:
        _, members = group
        families = {member["family"] for member in members}
        confidence = sum(
            float(member.get("confidence") or 0.0) for member in members
        ) / len(members)
        return (
            len(families),
            len(members),
            sum(member["profileWeight"] for member in members),
            int(any(member["family"] == "vietocr" for member in members)),
            confidence,
        )

    base_key_value, members = max(groups.items(), key=rank)
    families = {member["family"] for member in members}
    if not base_key_value or len(members) < 2 or len(families) < 2:
        return None, "insufficient_independent_support"

    selected = max(
        members,
        key=lambda member: (
            member["profileWeight"],
            float(member.get("confidence") or 0.0),
            sum(character != ascii_text(character) for character in member["value"]),
        ),
    )
    return selected, "independent_family_consensus"


def _baseline_needs_recovery(field_name: str, baseline: dict[str, Any]) -> bool:
    value = nfc_text(baseline.get("value"))
    if not value:
        return True
    safe, _ = _candidate_safety(field_name, value)
    return not safe


def recover_field(
    field_name: str,
    baseline: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a guarded field result and retain a non-promoting review status."""

    output = copy.deepcopy(baseline)
    recommendation, recommendation_reason = _select_recommendation(field_name, candidates)
    promoted = bool(recommendation and _baseline_needs_recovery(field_name, baseline))
    if promoted and recommendation:
        output["value"] = nfc_text(recommendation["value"])
        output["asciiValue"] = ascii_text(recommendation["value"])
        output["selectionMode"] = "v2_005_guarded_recovery"
        output["confidence"] = round(float(recommendation.get("confidence") or 0.0), 6)
        output["validation"] = {
            "valid": True,
            "rule": str(recommendation.get("validationRule") or "field_local"),
            "supportingRecognizerFamilyCount": len(
                {
                    _family(member.get("profile") or member.get("engine"))
                    for member in (candidates or [])
                }
            ),
        }
    # Candidate OCR remains review-only regardless of baseline status.
    output["status"] = "needs_review" if output.get("value") else "not_found"
    output["asciiStatus"] = "needs_review"
    output["policyVersion"] = OCR_HO_V2_005_VERSION
    output["policyMode"] = "SHADOW_REVIEW_ONLY"
    output["shadowRecovery"] = {
        "candidateCount": len(candidates),
        "candidateAvailable": recommendation is not None,
        "candidateReason": recommendation_reason,
        "baselineRecoveryRequired": _baseline_needs_recovery(field_name, baseline),
        "guardedRecoveryApplied": promoted,
        "source": "phase11_5_ocr_evidence_only",
    }
    return output


def build_shadow_fields(baseline_fields: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build all schema fields from Phase 11.5 evidence without accepting OCR."""

    result: dict[str, dict[str, Any]] = {}
    for field_name in FIELD_ORDER:
        baseline = baseline_fields.get(field_name) or {
            "value": None,
            "status": "not_found",
        }
        candidates = (baseline.get("evidence") or {}).get("candidates", [])
        result[field_name] = recover_field(field_name, baseline, candidates)
    return result


def summarize_recovery(fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return aggregate recovery counters safe to put in a tracked report."""

    by_field: dict[str, dict[str, int]] = {}
    for field_name in FIELD_ORDER:
        shadow = (fields.get(field_name) or {}).get("shadowRecovery") or {}
        by_field[field_name] = {
            "candidateAvailable": int(bool(shadow.get("candidateAvailable"))),
            "guardedRecoveryApplied": int(bool(shadow.get("guardedRecoveryApplied"))),
            "baselineRecoveryRequired": int(bool(shadow.get("baselineRecoveryRequired"))),
        }
    return {
        "candidateAvailableCount": sum(
            row["candidateAvailable"] for row in by_field.values()
        ),
        "guardedRecoveryAppliedCount": sum(
            row["guardedRecoveryApplied"] for row in by_field.values()
        ),
        "baselineRecoveryRequiredCount": sum(
            row["baselineRecoveryRequired"] for row in by_field.values()
        ),
        "byField": by_field,
    }
