"""Minimal review-first parsers for the four newly scoped templates."""

from __future__ import annotations

from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.templates.common import document_text, ocr_line_value, strip_terminal
from hcns_agent.templates.model import (
    ParsedTemplate,
    RecommendedAction,
    TemplateDetection,
    TemplateValidation,
)


class ReviewOnlyParser:
    version = "1.0.0"

    def __init__(self, field_labels: dict[str, tuple[str, ...]]) -> None:
        self._field_labels = field_labels

    def parse(
        self,
        document: CanonicalDocument,
        detection: TemplateDetection,
    ) -> ParsedTemplate:
        lines = tuple(line.strip() for line in document_text(document).splitlines() if line.strip())
        data: dict[str, object] = {
            "documentId": document.document_id,
            "documentType": detection.definition.document_type.value,
            "templateId": detection.definition.template_id,
            "templateVersion": detection.definition.version,
            "sourceFile": document.source.filename,
        }
        for field_name, labels in self._field_labels.items():
            data[field_name] = _line_value(lines, labels)
        return ParsedTemplate(data=data)


class ReviewOnlyValidator:
    def validate(
        self,
        parsed: ParsedTemplate,
        detection: TemplateDetection,
        required_fields: tuple[str, ...],
    ) -> TemplateValidation:
        missing = tuple(
            sorted(field for field in required_fields if parsed.data.get(field) in (None, ""))
        )
        errors = ["REVIEW_FIRST_REQUIRED"]
        if not detection.is_exact:
            errors.append("TEMPLATE_ANCHOR_PARTIAL")
        errors.extend(f"MULTIPLE_CANDIDATES:{field}" for field in parsed.conflicting_fields)
        return TemplateValidation(
            missing_fields=missing,
            validation_errors=tuple(dict.fromkeys(errors)),
            confidence=min(0.8, detection.confidence),
            recommended_action=RecommendedAction.MANUAL_REVIEW,
        )


def _line_value(lines: tuple[str, ...], labels: tuple[str, ...]) -> str | None:
    for index, line in enumerate(lines):
        value = ocr_line_value(line, labels)
        if value:
            return strip_terminal(value)
        if (
            any(label.casefold() in line.casefold() for label in labels)
            and index + 1 < len(lines)
            and ":" not in lines[index + 1]
        ):
            return strip_terminal(lines[index + 1])
    return None
