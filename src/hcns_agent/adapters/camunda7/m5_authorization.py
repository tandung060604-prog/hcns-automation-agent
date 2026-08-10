"""Fail-closed authorization and rollback checks for the M5 synthetic pilot."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SYNTHETIC_FAMILIES = frozenset({"LEAVE_REQUEST", "OVERTIME_REQUEST"})
_REQUIRED_ROLLBACK_TRIGGERS = frozenset(
    {
        "autoContinueCount > 0",
        "rawExposureCount > 0",
        "duplicateResultArtifacts > 0",
        "unreconciledCases > 0",
        "realSideEffectCount > 0",
        "any_case_not_MANUAL_REVIEW",
        "case_duration_seconds > 60",
    }
)


class M5AuthorizationError(ValueError):
    """M5 authorization is missing, expired or unsafe for execution."""


@dataclass(frozen=True, slots=True)
class M5SyntheticAuthorization:
    authorization_id: str
    owner_id: str
    reviewer_ids: tuple[str, ...]
    families: frozenset[str]
    start: datetime
    end: datetime
    retain_until: datetime
    deletion_owner_id: str
    rollback_authority_id: str
    rollback_triggers: frozenset[str]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> M5SyntheticAuthorization:
        if payload.get("status") != "AUTHORIZED_SYNTHETIC_ONLY":
            raise M5AuthorizationError("M5 authorization is not synthetic-only authorized")
        authorization_id = _opaque(payload, "authorizationId")
        owner_id = _opaque(payload, "ownerId")
        reviewer_ids = _opaque_sequence(payload.get("reviewerIds"), "reviewerIds")

        scope = _mapping(payload, "scope")
        if scope.get("kind") != "SYNTHETIC_ONLY" or scope.get("realCohortAllowed") is not False:
            raise M5AuthorizationError("M5 authorization permits a real cohort")
        families = _string_set(scope.get("families"), "scope.families")
        if not families or not families <= _SYNTHETIC_FAMILIES:
            raise M5AuthorizationError("M5 synthetic family scope is unsupported")
        if scope.get("caseCount") != 2:
            raise M5AuthorizationError("M5 synthetic authorization must cover two cases")

        window = _mapping(payload, "timeWindow")
        start = _timestamp(window, "start")
        end = _timestamp(window, "end")
        if end <= start:
            raise M5AuthorizationError("M5 authorization time window is invalid")
        retention = _mapping(payload, "retention")
        retain_until = _timestamp(retention, "retainUntil")
        if retain_until < end:
            raise M5AuthorizationError("M5 retention expires before the time window")
        deletion_owner_id = _opaque(retention, "deletionOwnerId")

        rollback = _mapping(payload, "rollback")
        rollback_authority_id = _opaque(rollback, "authorityId")
        rollback_triggers = _string_set(rollback.get("triggers"), "rollback.triggers")
        if not rollback_triggers >= _REQUIRED_ROLLBACK_TRIGGERS:
            raise M5AuthorizationError("M5 rollback triggers are incomplete")

        policy = _mapping(payload, "policy")
        if (
            policy.get("reviewAction") != "MANUAL_REVIEW"
            or policy.get("autoContinueEnabled") is not False
            or policy.get("realSideEffectsEnabled") is not False
            or policy.get("data24") != "IMMUTABLE_NOT_OPENED"
        ):
            raise M5AuthorizationError("M5 authorization violates locked safety policy")
        return cls(
            authorization_id=authorization_id,
            owner_id=owner_id,
            reviewer_ids=reviewer_ids,
            families=families,
            start=start,
            end=end,
            retain_until=retain_until,
            deletion_owner_id=deletion_owner_id,
            rollback_authority_id=rollback_authority_id,
            rollback_triggers=rollback_triggers,
        )

    def assert_active(self, now: datetime) -> None:
        current = _aware(now)
        if current < self.start:
            raise M5AuthorizationError("M5 authorization time window has not started")
        if current > self.end:
            raise M5AuthorizationError("M5 authorization has expired")

    def evaluate_report(self, report: Mapping[str, object]) -> M5RollbackDecision:
        """Return a fail-closed decision from the existing aggregate gates."""

        triggers: list[str] = []
        if report.get("autoContinueCount") != 0:
            triggers.append("autoContinueCount > 0")
        if report.get("rawExposureCount") != 0:
            triggers.append("rawExposureCount > 0")
        if report.get("duplicateResultArtifacts") != 0:
            triggers.append("duplicateResultArtifacts > 0")
        if report.get("unreconciledCases") != 0:
            triggers.append("unreconciledCases > 0")
        if report.get("realSideEffectCount") != 0:
            triggers.append("realSideEffectCount > 0")
        cases = report.get("cases")
        if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
            triggers.append("any_case_not_MANUAL_REVIEW")
        else:
            for case in cases:
                if not isinstance(case, Mapping) or case.get("reached_user_review") is not True:
                    triggers.append("any_case_not_MANUAL_REVIEW")
                    break
                duration = case.get("duration_seconds")
                if not isinstance(duration, (int, float)) or duration >= 60:
                    triggers.append("case_duration_seconds > 60")
                    break
        if report.get("passed") is not True:
            triggers.append("preflight_report_not_passed")
        unique_triggers = tuple(dict.fromkeys(triggers))
        if unique_triggers:
            return M5RollbackDecision(
                allowed_to_complete=False,
                rollback_required=True,
                trigger_codes=unique_triggers,
                action="STOP_RUN_DELETE_PRIVATE_SYNTHETIC_ARTIFACTS_ESCALATE",
            )
        return M5RollbackDecision(
            allowed_to_complete=True,
            rollback_required=False,
            trigger_codes=(),
            action="COMPLETE_SYNTHETIC_SHADOW_RUN",
        )


@dataclass(frozen=True, slots=True)
class M5RollbackDecision:
    allowed_to_complete: bool
    rollback_required: bool
    trigger_codes: tuple[str, ...]
    action: str


def _mapping(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    if not isinstance(value, Mapping):
        raise M5AuthorizationError(f"M5 authorization field {name} is missing")
    return value


def _opaque(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or _OPAQUE_ID.fullmatch(value) is None:
        raise M5AuthorizationError(f"M5 authorization field {name} is invalid")
    return value


def _opaque_sequence(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise M5AuthorizationError(f"M5 authorization field {name} is invalid")
    result = tuple(item for item in value if isinstance(item, str))
    if len(result) != len(value) or any(_OPAQUE_ID.fullmatch(item) is None for item in result):
        raise M5AuthorizationError(f"M5 authorization field {name} is invalid")
    return result


def _string_set(value: object, name: str) -> frozenset[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise M5AuthorizationError(f"M5 authorization field {name} is invalid")
    result = frozenset(item for item in value if isinstance(item, str))
    if len(result) != len(value):
        raise M5AuthorizationError(f"M5 authorization field {name} is invalid")
    return result


def _timestamp(payload: Mapping[str, object], name: str) -> datetime:
    value = payload.get(name)
    if not isinstance(value, str):
        raise M5AuthorizationError(f"M5 authorization timestamp {name} is missing")
    try:
        return _aware(datetime.fromisoformat(value))
    except ValueError as error:
        raise M5AuthorizationError(f"M5 authorization timestamp {name} is invalid") from error


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise M5AuthorizationError("M5 authorization timestamps must include a timezone")
    return value.astimezone(timezone.utc)
