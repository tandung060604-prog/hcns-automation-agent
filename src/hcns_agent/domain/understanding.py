"""Document classification, extracted fields, validation, and quality models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from hcns_agent.domain.canonical import CanonicalDocument, ScalarValue, SourceLocation
from hcns_agent.domain.documents import DocumentType
from hcns_agent.domain.models import FieldStatus


class ValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class QualityStatus(str, Enum):
    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ClassificationCandidate:
    document_type: DocumentType
    confidence: float
    matched_markers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class DocumentClassification:
    document_type: DocumentType
    confidence: float
    candidates: tuple[ClassificationCandidate, ...]
    evidence: tuple[SourceLocation, ...]
    classifier_name: str
    classifier_version: str

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)
        if not self.classifier_name.strip() or not self.classifier_version.strip():
            raise ValueError("Classifier name and version must not be empty")


@dataclass(frozen=True, slots=True)
class FieldEvidence:
    source: SourceLocation
    method: str


@dataclass(frozen=True, slots=True)
class BusinessField:
    name: str
    value: ScalarValue
    confidence: float
    status: FieldStatus
    sensitive: bool
    evidence: tuple[FieldEvidence, ...]
    extractor_name: str
    extractor_version: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Field name must not be empty")
        _validate_confidence(self.confidence)
        if not self.extractor_name.strip() or not self.extractor_version.strip():
            raise ValueError("Extractor name and version must not be empty")


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: ValidationSeverity
    field_name: str | None = None
    source: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class QualityReport:
    score: float
    status: QualityStatus
    review_required: bool
    reasons: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]

    def __post_init__(self) -> None:
        _validate_confidence(self.score)
        if self.status is QualityStatus.PASS and self.review_required:
            raise ValueError("PASS quality cannot require review")


@dataclass(frozen=True, slots=True)
class IdpResult:
    canonical_document: CanonicalDocument
    classification: DocumentClassification
    fields: tuple[BusinessField, ...]
    quality: QualityReport
    schema_version: str = "2.0.0"

    def __post_init__(self) -> None:
        if not self.schema_version.strip():
            raise ValueError("schema_version must not be empty")

    @property
    def document_id(self) -> str:
        return self.canonical_document.document_id


def _validate_confidence(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError("Confidence and quality scores must be between 0 and 1")
