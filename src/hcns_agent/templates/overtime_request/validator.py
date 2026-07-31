"""Business validation for overtime-request-v1."""

from __future__ import annotations

from datetime import date, datetime

from hcns_agent.templates.model import (
    ParsedTemplate,
    RecommendedAction,
    TemplateDetection,
    TemplateValidation,
)

_NON_FIELD_KEYS = frozenset(
    {
        "documentId",
        "documentType",
        "templateId",
        "templateVersion",
        "documentTitle",
        "sourceFile",
    }
)


class OvertimeRequestValidator:
    def validate(
        self,
        parsed: ParsedTemplate,
        detection: TemplateDetection,
        required_fields: tuple[str, ...],
    ) -> TemplateValidation:
        data = parsed.data
        missing = tuple(
            sorted(
                name
                for name, value in data.items()
                if name not in _NON_FIELD_KEYS and value in (None, "")
            )
        )
        missing_required = tuple(
            sorted(name for name in required_fields if data.get(name) in (None, ""))
        )
        errors = [f"MULTIPLE_CANDIDATES:{name}" for name in parsed.conflicting_fields]
        dates: dict[str, date] = {}
        for field_name in ("requestDate", "laborContractDate", "startDate", "endDate"):
            value = data.get(field_name)
            if value is None:
                continue
            try:
                dates[field_name] = date.fromisoformat(str(value))
            except ValueError:
                errors.append(f"INVALID_DATE:{field_name}")
        if (
            dates.get("startDate")
            and dates.get("endDate")
            and dates["startDate"] > dates["endDate"]
        ):
            errors.append("DATE_RANGE_CONFLICT:startDate,endDate")

        per_day = data.get("overtimeHoursPerDay")
        total = data.get("totalOvertimeHours")
        if isinstance(per_day, (int, float)) and per_day <= 0:
            errors.append("OVERTIME_HOURS_PER_DAY_NOT_POSITIVE")
        if isinstance(total, (int, float)) and total <= 0:
            errors.append("TOTAL_OVERTIME_HOURS_NOT_POSITIVE")

        start_time = _parse_time(data.get("overtimeStartTime"))
        end_time = _parse_time(data.get("overtimeEndTime"))
        if start_time is not None and end_time is not None:
            duration = (end_time - start_time).total_seconds() / 3600
            if duration <= 0:
                errors.append("OVERTIME_TIME_RANGE_CONFLICT")
            elif isinstance(per_day, (int, float)) and abs(duration - per_day) > 0.01:
                errors.append("OVERTIME_HOURS_PER_DAY_CONFLICT")
        if (
            isinstance(per_day, (int, float))
            and isinstance(total, (int, float))
            and dates.get("startDate")
            and dates.get("endDate")
            and dates["startDate"] <= dates["endDate"]
        ):
            day_count = (dates["endDate"] - dates["startDate"]).days + 1
            if abs(day_count * per_day - total) > 0.01:
                errors.append("TOTAL_OVERTIME_HOURS_CONFLICT")
        if not detection.is_exact:
            errors.append("TEMPLATE_ANCHOR_PARTIAL")
        action = (
            RecommendedAction.AUTO_CONTINUE
            if not missing_required and not errors
            else RecommendedAction.MANUAL_REVIEW
        )
        confidence = 1.0 if action is RecommendedAction.AUTO_CONTINUE else detection.confidence
        return TemplateValidation(
            missing_fields=missing,
            validation_errors=tuple(dict.fromkeys(errors)),
            confidence=confidence,
            recommended_action=action,
        )


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%H:%M")
    except ValueError:
        return None
