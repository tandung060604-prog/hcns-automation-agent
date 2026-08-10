from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from hcns_agent.adapters.camunda7.m5_authorization import (
    M5AuthorizationError,
    M5SyntheticAuthorization,
)
from hcns_agent.adapters.camunda7.shadow_preflight import (
    Camunda7ShadowPreflightGateway,
    run_shadow_preflight,
)


def _payload() -> dict[str, object]:
    return {
        "authorizationId": "synthetic-auth-01",
        "status": "AUTHORIZED_SYNTHETIC_ONLY",
        "ownerId": "synthetic-owner",
        "reviewerIds": ["synthetic-reviewer"],
        "scope": {
            "kind": "SYNTHETIC_ONLY",
            "families": ["LEAVE_REQUEST", "OVERTIME_REQUEST"],
            "caseCount": 2,
            "realCohortAllowed": False,
        },
        "timeWindow": {
            "start": "2026-08-10T15:55:00+07:00",
            "end": "2026-08-10T18:00:00+07:00",
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "retention": {
            "retainUntil": "2026-08-17T23:59:59+07:00",
            "deletionOwnerId": "synthetic-owner",
            "storage": "private-local-only",
        },
        "rollback": {
            "authorityId": "synthetic-owner",
            "triggers": [
                "autoContinueCount > 0",
                "rawExposureCount > 0",
                "duplicateResultArtifacts > 0",
                "unreconciledCases > 0",
                "realSideEffectCount > 0",
                "any_case_not_MANUAL_REVIEW",
                "case_duration_seconds > 60",
            ],
        },
        "policy": {
            "reviewAction": "MANUAL_REVIEW",
            "autoContinueEnabled": False,
            "realSideEffectsEnabled": False,
            "data24": "IMMUTABLE_NOT_OPENED",
        },
    }


def _report(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "passed": True,
        "caseCount": 2,
        "autoContinueCount": 0,
        "rawExposureCount": 0,
        "duplicateResultArtifacts": 0,
        "unreconciledCases": 0,
        "realSideEffectCount": 0,
        "cases": [
            {"reached_user_review": True, "duration_seconds": 1.0},
            {"reached_user_review": True, "duration_seconds": 2.0},
        ],
    }
    result.update(overrides)
    return result


def test_active_authorization_and_pass_report_are_allowed() -> None:
    authorization = M5SyntheticAuthorization.from_mapping(_payload())
    authorization.assert_active(datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc))

    decision = authorization.evaluate_report(_report())

    assert decision.allowed_to_complete is True
    assert decision.rollback_required is False
    assert decision.trigger_codes == ()


def test_expired_authorization_is_rejected() -> None:
    payload = _payload()
    window = cast(dict[str, object], payload["timeWindow"])
    window["start"] = "2026-08-09T15:55:00+07:00"
    window["end"] = "2026-08-09T18:00:00+07:00"
    authorization = M5SyntheticAuthorization.from_mapping(payload)

    with pytest.raises(M5AuthorizationError, match="expired"):
        authorization.assert_active(datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc))


def test_expired_authorization_refuses_before_camunda_process_start(tmp_path: Path) -> None:
    payload = _payload()
    window = cast(dict[str, object], payload["timeWindow"])
    window["start"] = "2026-08-09T15:55:00+07:00"
    window["end"] = "2026-08-09T18:00:00+07:00"
    authorization = M5SyntheticAuthorization.from_mapping(payload)

    with pytest.raises(M5AuthorizationError, match="expired"):
        run_shadow_preflight(
            gateway=cast(Camunda7ShadowPreflightGateway, object()),
            private_root=tmp_path,
            repository_root=Path("C:/synthetic-repository"),
            worker_id="synthetic-worker",
            authorization=authorization,
            authorization_now=lambda: datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc),
        )

    assert list(tmp_path.iterdir()) == []


def test_safety_gate_violation_requires_fail_closed_rollback() -> None:
    authorization = M5SyntheticAuthorization.from_mapping(_payload())
    violation = deepcopy(_report())
    violation["autoContinueCount"] = 1

    decision = authorization.evaluate_report(violation)

    assert decision.allowed_to_complete is False
    assert decision.rollback_required is True
    assert "autoContinueCount > 0" in decision.trigger_codes
    assert decision.action == "STOP_RUN_DELETE_PRIVATE_SYNTHETIC_ARTIFACTS_ESCALATE"


def test_unsafe_policy_cannot_be_loaded() -> None:
    payload = _payload()
    policy = cast(dict[str, object], payload["policy"])
    policy["realSideEffectsEnabled"] = True

    with pytest.raises(M5AuthorizationError, match="locked safety policy"):
        M5SyntheticAuthorization.from_mapping(payload)
