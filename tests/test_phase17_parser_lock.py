from __future__ import annotations

from scripts.validate_phase17_parser_lock import validate_lock


def test_phase17_parser_lock_is_current_and_review_only() -> None:
    lock = validate_lock()

    assert lock["parserVersion"] == "phase17-structured-hr-parser/2.0.0"
    assert lock["mode"] == "SHADOW_REVIEW_ONLY"
    assert lock["automaticFallbackEnabled"] is False
    assert lock["sensitiveOcrAutoAccept"] is False
    assert lock["timesheetContract"]["predictionTablesRequired"] is True
