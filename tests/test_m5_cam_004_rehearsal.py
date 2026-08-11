from __future__ import annotations

from datetime import datetime, timezone

from scripts.run_m5_cam_004_rehearsal import (
    build_rehearsal_report,
    build_synthetic_authorization,
)


def _preflight() -> dict[str, object]:
    return {
        "passed": True,
        "caseCount": 2,
        "autoContinueCount": 0,
        "rawExposureCount": 0,
        "duplicateResultArtifacts": 0,
        "unreconciledCases": 0,
        "realSideEffectCount": 0,
        "cases": [
            {
                "case_id": "M5-LEAVE-SYNTHETIC",
                "document_type": "LEAVE_REQUEST",
                "reached_user_review": True,
            },
            {
                "case_id": "M5-OVERTIME-SYNTHETIC",
                "document_type": "OVERTIME_REQUEST",
                "reached_user_review": True,
            },
        ],
    }


def test_rehearsal_report_passes_manual_review_and_rollback_gates() -> None:
    report = build_rehearsal_report(
        _preflight(),
        process_start_count=2,
        authorization=build_synthetic_authorization(datetime.now(timezone.utc)),
    )

    assert report["passed"] is True
    assert report["caseCount"] == 2
    assert report["manualReviewCount"] == 2
    assert report["idempotency"]["passed"] is True  # type: ignore[index]
    assert report["rollbackCheck"]["rollbackRequired"] is True  # type: ignore[index]
    assert report["rollbackCheck"]["allowedToComplete"] is False  # type: ignore[index]
    assert report["handoff"]["scalarOnly"] is True  # type: ignore[index]
    assert report["handoff"]["opaqueReferenceOnly"] is True  # type: ignore[index]
    assert report["promotionAllowed"] is False
    assert report["containsRawFieldValues"] is False


def test_rehearsal_report_holds_on_duplicate_case_id() -> None:
    preflight = _preflight()
    cases = preflight["cases"]
    assert isinstance(cases, list)
    cases[1] = dict(cases[0])
    report = build_rehearsal_report(
        preflight,
        process_start_count=2,
        authorization=build_synthetic_authorization(datetime.now(timezone.utc)),
    )

    assert report["passed"] is False
    assert report["idempotency"]["passed"] is False  # type: ignore[index]
