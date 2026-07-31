"""Business validation for leave-request-v1."""

from __future__ import annotations

from datetime import date

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


class LeaveRequestValidator:
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
        for field_name in ("requestDate", "startDate", "endDate", "expectedReturnDate"):
            value = data.get(field_name)
            if value is None:
                continue
            try:
                dates[field_name] = date.fromisoformat(str(value))
            except ValueError:
                errors.append(f"INVALID_DATE:{field_name}")
        if dates.get("startDate") and dates.get("endDate"):
            if dates["startDate"] > dates["endDate"]:
                errors.append("DATE_RANGE_CONFLICT:startDate,endDate")
            leave_days = data.get("leaveDays")
            if isinstance(leave_days, (int, float)) and leave_days > (
                dates["endDate"] - dates["startDate"]
            ).days + 1:
                errors.append("LEAVE_DAYS_EXCEED_DATE_RANGE")
        expected = dates.get("expectedReturnDate")
        if (
            expected is not None
            and dates.get("endDate") is not None
            and expected <= dates["endDate"]
        ):
            errors.append("EXPECTED_RETURN_NOT_AFTER_END")
        leave_days_value = data.get("leaveDays")
        if isinstance(leave_days_value, (int, float)) and leave_days_value <= 0:
            errors.append("LEAVE_DAYS_NOT_POSITIVE")
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
