"""Human review helpers for Phase 15 structured HR fields."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

MAX_REVIEW_FIELD_CHARS = 4_000


def apply_phase15_field_review(
    extraction: dict[str, Any],
    submitted_fields: dict[str, Any],
    *,
    reviewed_at: str,
) -> tuple[dict[str, Any], int]:
    """Return a reviewed extraction without mutating the automatic result."""
    source_fields = extraction.get("fields")
    if not isinstance(source_fields, dict) or not source_fields:
        raise ValueError("Phase 15 fields are not available for review")
    if set(submitted_fields) != set(source_fields):
        raise ValueError("Review must contain every Phase 15 field exactly once")

    reviewed = deepcopy(extraction)
    corrected_count = 0
    for field_name, original in source_fields.items():
        submitted = submitted_fields[field_name]
        if submitted is not None and not isinstance(submitted, str):
            raise ValueError(f"Field {field_name} must be text or null")
        value = submitted.strip() if isinstance(submitted, str) else ""
        if len(value) > MAX_REVIEW_FIELD_CHARS:
            raise ValueError(f"Field {field_name} exceeds the review limit")

        original_value = original.get("normalizedValue")
        if original_value is None:
            original_value = original.get("value")
        if value != ("" if original_value is None else str(original_value).strip()):
            corrected_count += 1

        reviewed["fields"][field_name] = {
            **original,
            "value": value or None,
            "normalizedValue": value or None,
            "confidence": 1.0 if value else None,
            "status": "accepted" if value else "not_found",
            "validation": {
                "valid": bool(value),
                "method": "human_review",
            },
            "evidence": {
                "sourceKind": "human_review",
                "reviewedAt": reviewed_at,
                "originalStatus": original.get("status"),
                "originalEvidence": original.get("evidence"),
            },
        }

    fields = reviewed["fields"]
    statuses = [field["status"] for field in fields.values()]
    present = sum(field["value"] is not None for field in fields.values())
    accepted = statuses.count("accepted")
    expected = len(fields)
    reviewed["summary"] = {
        "expectedFieldCount": expected,
        "presentFieldCount": present,
        "acceptedFieldCount": accepted,
        "needsReviewFieldCount": statuses.count("needs_review"),
        "notFoundFieldCount": statuses.count("not_found"),
        "documentCompleteness": round(present / max(1, expected), 6),
        "acceptedCoverage": round(accepted / max(1, expected), 6),
        "readyForAutomaticUse": expected > 0 and accepted == expected,
    }
    return reviewed, corrected_count
