"""Atomic persistence and resume helpers for Phase 14 line reviews."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


def load_line_reviews(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schemaVersion": "14.4.0-private",
            "containsRealPII": True,
            "reviews": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("reviews"), dict):
        raise ValueError("Invalid Phase 14 review store")
    return payload


def save_line_review(
    path: Path,
    *,
    case_id: str,
    ground_truth: str,
    reviewed_at: str,
) -> dict[str, Any]:
    payload = load_line_reviews(path)
    payload["containsRealPII"] = True
    payload["reviews"][case_id] = {
        "groundTruth": ground_truth,
        "reviewedAt": reviewed_at,
        "comparedWithCrop": True,
        "allTextChecked": True,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def pending_case_ids(
    cases: list[dict[str, Any]],
    reviews: dict[str, Any],
) -> list[str]:
    reviewed = reviews.get("reviews", {})
    return [
        str(case["caseId"])
        for case in cases
        if str(case["caseId"]) not in reviewed
    ]
