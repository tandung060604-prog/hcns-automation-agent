"""Validation and review-aware quality gate for extracted business fields."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.domain.documents import DocumentType, ParseStatus
from hcns_agent.domain.models import FieldStatus
from hcns_agent.domain.understanding import (
    BusinessField,
    DocumentClassification,
    QualityReport,
    QualityStatus,
    ValidationIssue,
    ValidationSeverity,
)


def _required_fields() -> dict[DocumentType, frozenset[str]]:
    return {
        DocumentType.CV: frozenset({"full_name", "skills"}),
        DocumentType.EMPLOYMENT_CONTRACT: frozenset(
            {"contract_number", "employee_name", "start_date"}
        ),
        DocumentType.LEAVE_REQUEST: frozenset(
            {"employee_name", "start_date", "end_date", "reason"}
        ),
    }


@dataclass(frozen=True, slots=True)
class QualityGatePolicy:
    minimum_classification_confidence: float = 0.65
    minimum_field_confidence: float = 0.85
    rejection_score_threshold: float = 0.25
    required_fields: dict[DocumentType, frozenset[str]] = field(default_factory=_required_fields)


class ValidationQualityGate:
    def __init__(self, policy: QualityGatePolicy | None = None) -> None:
        self._policy = policy or QualityGatePolicy()

    def evaluate(
        self,
        document: CanonicalDocument,
        classification: DocumentClassification,
        fields: tuple[BusinessField, ...],
        *,
        extractor_available: bool,
    ) -> tuple[tuple[BusinessField, ...], QualityReport]:
        issues: list[ValidationIssue] = []
        reasons: list[str] = []
        invalid_fields: set[str] = set()

        if document.parse_status in {ParseStatus.FAILED, ParseStatus.REJECTED}:
            issues.append(
                ValidationIssue(
                    code="PARSE_NOT_USABLE",
                    message="Canonical parse result is not usable",
                    severity=ValidationSeverity.ERROR,
                )
            )
            reasons.append("Parse result is not usable")
        elif document.parse_status is ParseStatus.PARTIAL:
            issues.append(
                ValidationIssue(
                    code="PARTIAL_PARSE",
                    message="Document parser returned a partial result",
                    severity=ValidationSeverity.WARNING,
                )
            )
            reasons.append("Partial parse requires review")

        for warning in document.warnings:
            issues.append(
                ValidationIssue(
                    code=f"PARSER_{warning.code}",
                    message=warning.message,
                    severity=ValidationSeverity.WARNING,
                    source=warning.source,
                )
            )
        if document.warnings:
            reasons.append("Parser warnings require review")

        if classification.document_type is DocumentType.UNKNOWN:
            issues.append(
                ValidationIssue(
                    code="UNKNOWN_DOCUMENT_TYPE",
                    message="Document type could not be classified",
                    severity=ValidationSeverity.WARNING,
                )
            )
            reasons.append("Unknown document type")
        elif classification.confidence < self._policy.minimum_classification_confidence:
            issues.append(
                ValidationIssue(
                    code="LOW_CLASSIFICATION_CONFIDENCE",
                    message="Document classification confidence is below policy",
                    severity=ValidationSeverity.WARNING,
                )
            )
            reasons.append("Low classification confidence")

        if _is_ambiguous(classification):
            issues.append(
                ValidationIssue(
                    code="AMBIGUOUS_DOCUMENT_TYPE",
                    message="Top document type candidates are too close",
                    severity=ValidationSeverity.WARNING,
                )
            )
            reasons.append("Ambiguous document type")

        if not extractor_available:
            issues.append(
                ValidationIssue(
                    code="NO_FIELD_EXTRACTOR",
                    message="No approved field extractor exists for this document type",
                    severity=ValidationSeverity.WARNING,
                )
            )
            reasons.append("No approved extractor")

        fields_by_name: dict[str, list[BusinessField]] = {}
        for extracted_field in fields:
            fields_by_name.setdefault(extracted_field.name, []).append(extracted_field)

        required = self._policy.required_fields.get(classification.document_type, frozenset())
        for missing_name in sorted(required - fields_by_name.keys()):
            issues.append(
                ValidationIssue(
                    code="REQUIRED_FIELD_MISSING",
                    message="Required field was not extracted",
                    severity=ValidationSeverity.ERROR,
                    field_name=missing_name,
                )
            )
            reasons.append("Required fields are missing")

        for field_name, candidates in fields_by_name.items():
            distinct_values = {str(candidate.value) for candidate in candidates}
            if len(distinct_values) > 1:
                invalid_fields.add(field_name)
                issues.append(
                    ValidationIssue(
                        code="FIELD_CONFLICT",
                        message="Multiple conflicting values were extracted for one field",
                        severity=ValidationSeverity.ERROR,
                        field_name=field_name,
                        source=candidates[0].evidence[0].source if candidates[0].evidence else None,
                    )
                )
                reasons.append("Conflicting field values require review")

        invalid_fields.update(self._validate_dates(fields_by_name, issues, reasons))

        validated_fields: list[BusinessField] = []
        for extracted_field in fields:
            field_status = FieldStatus.ACCEPTED
            if extracted_field.name in invalid_fields:
                field_status = FieldStatus.INVALID
            elif (
                extracted_field.sensitive
                or extracted_field.confidence < self._policy.minimum_field_confidence
            ):
                field_status = FieldStatus.NEEDS_REVIEW
            if extracted_field.sensitive:
                reasons.append("Sensitive fields require human confirmation")
            if extracted_field.confidence < self._policy.minimum_field_confidence:
                issues.append(
                    ValidationIssue(
                        code="LOW_FIELD_CONFIDENCE",
                        message="Extracted field confidence is below policy",
                        severity=ValidationSeverity.WARNING,
                        field_name=extracted_field.name,
                        source=extracted_field.evidence[0].source
                        if extracted_field.evidence
                        else None,
                    )
                )
                reasons.append("Low-confidence fields require review")
            validated_fields.append(replace(extracted_field, status=field_status))

        score = _quality_score(classification.confidence, issues)
        if document.parse_status in {ParseStatus.FAILED, ParseStatus.REJECTED} or (
            score < self._policy.rejection_score_threshold
            and any(issue.severity is ValidationSeverity.ERROR for issue in issues)
        ):
            quality_status = QualityStatus.REJECTED
            review_required = True
        elif reasons or issues:
            quality_status = QualityStatus.REVIEW_REQUIRED
            review_required = True
        else:
            quality_status = QualityStatus.PASS
            review_required = False

        return tuple(validated_fields), QualityReport(
            score=score,
            status=quality_status,
            review_required=review_required,
            reasons=tuple(dict.fromkeys(reasons)),
            issues=tuple(issues),
        )

    @staticmethod
    def _validate_dates(
        fields_by_name: dict[str, list[BusinessField]],
        issues: list[ValidationIssue],
        reasons: list[str],
    ) -> set[str]:
        invalid_fields: set[str] = set()
        parsed_dates: dict[str, date] = {}
        for field_name in ("start_date", "end_date"):
            candidates = fields_by_name.get(field_name, [])
            if not candidates:
                continue
            try:
                parsed_dates[field_name] = date.fromisoformat(str(candidates[0].value))
            except ValueError:
                invalid_fields.add(field_name)
                issues.append(
                    ValidationIssue(
                        code="INVALID_DATE",
                        message="Date field is not a valid ISO date",
                        severity=ValidationSeverity.ERROR,
                        field_name=field_name,
                        source=candidates[0].evidence[0].source if candidates[0].evidence else None,
                    )
                )
                reasons.append("Invalid dates require review")
        if (
            "start_date" in parsed_dates
            and "end_date" in parsed_dates
            and parsed_dates["end_date"] < parsed_dates["start_date"]
        ):
            invalid_fields.update({"start_date", "end_date"})
            issues.append(
                ValidationIssue(
                    code="DATE_RANGE_CONFLICT",
                    message="End date is earlier than start date",
                    severity=ValidationSeverity.ERROR,
                )
            )
            reasons.append("Conflicting dates require review")
        return invalid_fields


def _is_ambiguous(classification: DocumentClassification) -> bool:
    if len(classification.candidates) < 2:
        return False
    first, second = classification.candidates[:2]
    return second.confidence >= 0.50 and first.confidence - second.confidence <= 0.08


def _quality_score(
    classification_confidence: float,
    issues: list[ValidationIssue],
) -> float:
    score = 0.4 + 0.6 * classification_confidence
    penalties = {
        ValidationSeverity.INFO: 0.01,
        ValidationSeverity.WARNING: 0.06,
        ValidationSeverity.ERROR: 0.16,
    }
    score -= sum(penalties[issue.severity] for issue in issues)
    return round(max(0.0, min(1.0, score)), 4)
