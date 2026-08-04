"""OCR-HO-V2-008 token-aligned address candidate.

The candidate is shadow-only.  It aligns OCR tokens after reversible label and
Unicode cleanup, requires independent recognizer-family support, and restores
only structural separators for the origin address.  Ground Truth and sibling
documents are never inputs to selection.
"""

from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict
from typing import Any

import phase11_5_cccd as phase11_5
import phase11_6_cccd as phase11_6
import phase11_7_cccd_v2 as phase11_7
from phase11_cccd import FIELD_ORDER

CANDIDATE_VERSION = "11.8.1"
SCHEMA_VERSION = phase11_6.SCHEMA_VERSION
POLICY_ID = "phase11.8-v2-address-token-consensus"
TARGET_FIELDS = phase11_7.TARGET_FIELDS
PROTECTED_FIELDS = tuple(name for name in FIELD_ORDER if name not in TARGET_FIELDS)


build_crop_variants = phase11_7.build_crop_variants
locate_field_regions = phase11_7.locate_field_regions
field_candidate = phase11_7.field_candidate
repair_unicode = phase11_7.repair_unicode


def _tokens(value: Any) -> list[str]:
    return [
        token
        for token in re.findall(r"[^\W_]+", phase11_5.nfc_text(value), flags=re.UNICODE)
        if token
    ]


def _token_key(value: Any) -> str:
    return phase11_5.base_key(value).casefold()


def _sequence_key(value: str) -> tuple[str, ...]:
    return tuple(_token_key(token) for token in _tokens(value))


def _family(candidate: dict[str, Any]) -> str:
    return phase11_7._family(candidate.get("profile") or candidate.get("engine"))


def _profile_weight(candidate: dict[str, Any]) -> int:
    return phase11_7._profile_weight(candidate.get("profile") or candidate.get("engine"))


def _comma_positions(value: str) -> list[int]:
    spans = list(re.finditer(r"[^\W_]+", value, flags=re.UNICODE))
    return [
        index
        for index, span in enumerate(spans[:-1])
        if "," in value[span.end() : spans[index + 1].start()]
    ]


def _balanced_origin_positions(token_count: int) -> list[int]:
    """Return separators for a generic 2/3 administrative-part address."""

    if token_count < 2:
        return []
    segment_count = 3 if token_count >= 5 else 2
    return [
        round(index * token_count / segment_count) - 1
        for index in range(1, segment_count)
    ]


def _render_tokens(
    tokens: list[str],
    positions: list[int],
) -> str:
    separators = set(positions)
    return "".join(
        ((", " if index - 1 in separators else " ") if index else "") + token
        for index, token in enumerate(tokens)
    )


def _usable_candidates(
    field_name: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    usable: list[dict[str, Any]] = []
    for raw in candidates:
        cleaned = field_candidate(
            field_name,
            raw.get("rawValue") or raw.get("value"),
        )
        if not cleaned or len(_tokens(cleaned)) < 2:
            continue
        safe, rule = phase11_7._safe_address(cleaned)
        if not safe:
            continue
        item = dict(raw)
        item.update(
            {
                "value": cleaned,
                "rawValue": raw.get("rawValue") or raw.get("value"),
                "profile": str(raw.get("profile") or raw.get("engine") or "unknown"),
                "family": _family(raw),
                "profileWeight": _profile_weight(raw),
                "validationRule": rule,
                "unicodeEvidence": phase11_5.ascii_text(cleaned) != cleaned,
                "tokenKeys": list(_sequence_key(cleaned)),
            }
        )
        usable.append(item)
    return usable


def _group_rank(group: tuple[tuple[str, ...], list[dict[str, Any]]]) -> tuple[int, int, float, int]:
    _, members = group
    return (
        len({member["family"] for member in members}),
        len(members),
        sum(float(member.get("confidence") or 0.0) for member in members)
        / max(1, len(members)),
        len(group[0]),
    )


def _select_token_variant(
    token_key: str,
    members: list[dict[str, Any]],
) -> str:
    variants: list[tuple[str, dict[str, Any]]] = []
    for member in members:
        for token in _tokens(member["value"]):
            if _token_key(token) == token_key:
                variants.append((token, member))
    if not variants:
        return token_key
    family_counts = Counter(member["family"] for _, member in variants)
    variant_counts = Counter(token for token, _ in variants)
    selected, _ = max(
        variants,
        key=lambda item: (
            family_counts[item[1]["family"]],
            variant_counts[item[0]],
            sum(ord(char) > 127 for char in item[0]),
            item[1]["profileWeight"],
            float(item[1].get("confidence") or 0.0),
        ),
    )
    return selected


def _origin_candidate(
    candidates: list[dict[str, Any]],
    *,
    bbox: list[int] | None,
    page_index: int,
) -> dict[str, Any]:
    usable = _usable_candidates("placeOfOrigin", candidates)
    if not usable:
        return {
            "value": None,
            "asciiValue": None,
            "status": "not_found",
            "asciiStatus": "not_found",
            "confidence": 0.0,
            "errorSignals": ["not_found"],
            "selectionMode": "phase11_8_no_token_consensus",
            "evidence": {"pageIndex": page_index, "bbox": bbox or [], "candidates": []},
        }
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in usable:
        groups[tuple(item["tokenKeys"])].append(item)
    ranked = sorted(groups.items(), key=_group_rank, reverse=True)
    if not ranked or len({member["family"] for member in ranked[0][1]}) < 2:
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
    token_keys, members = ranked[0]
    tokens = [_select_token_variant(token_key, members) for token_key in token_keys]
    observed = Counter(tuple(_comma_positions(member["value"])) for member in members)
    observed_positions = list(observed.most_common(1)[0][0]) if observed else []
    positions = observed_positions or _balanced_origin_positions(len(tokens))
    value = _render_tokens(tokens, positions)
    families = {member["family"] for member in members}
    return {
        "value": repair_unicode(value),
        "asciiValue": phase11_5.ascii_text(value),
        "status": "needs_review",
        "asciiStatus": "verified_base_text",
        "confidence": round(
            min(float(member.get("confidence") or 0.0) for member in members),
            6,
        ),
        "errorSignals": [],
        "selectionMode": "phase11_6_single_candidate",
        "validation": {
            "valid": True,
            "rule": "address_shape",
            "tokenConsensus": True,
            "separatorPolicy": "observed_or_balanced_origin",
            "supportingRecognizerCount": len({member["profile"] for member in members}),
            "supportingRecognizerFamilyCount": len(families),
        },
        "evidence": {
            "pageIndex": page_index,
            "bbox": bbox or [],
            "candidates": usable,
        },
    }


def select_address_candidate(
    field_name: str,
    candidates: list[dict[str, Any]],
    *,
    bbox: list[int] | None,
    page_index: int = 0,
) -> dict[str, Any]:
    if field_name == "placeOfOrigin":
        return _origin_candidate(candidates, bbox=bbox, page_index=page_index)
    # Residence remains guarded by the proven v11.7 selector until a strong
    # token sequence is available; this keeps the candidate non-regressing.
    return phase11_7.select_address_candidate(
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
    if field_name == "placeOfOrigin" and candidate.get("validation", {}).get("tokenConsensus"):
        # Independent token consensus is strong enough to repair a baseline
        # value even when its validator only reported omission/diacritics.
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
                fields[field_name] = _manual_field(candidate, "phase11_6_single_candidate")
                fields[field_name]["policyVersion"] = CANDIDATE_VERSION
                fields[field_name]["policyMode"] = "SHADOW_REVIEW_ONLY"
                continue
            if baseline.get("value") is not None:
                baseline["phase11_8Candidate"] = candidate
                fields[field_name] = _manual_field(baseline, "phase11_6_baseline_preserved")
                continue
            fields[field_name] = _manual_field(candidate, "phase11_6_single_candidate")
            continue
        fields[field_name] = _manual_field(baseline, "phase11_6_baseline_preserved")
    present = sum(field.get("value") is not None for field in fields.values())
    accepted = sum(field.get("status") == "accepted" for field in fields.values())
    review = sum(field.get("status") == "needs_review" for field in fields.values())
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
            "notFoundFieldCount": len(FIELD_ORDER) - present - accepted,
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
