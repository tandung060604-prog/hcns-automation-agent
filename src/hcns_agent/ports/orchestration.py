"""Camunda-neutral job, result storage, and orchestration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from hcns_agent.domain.canonical import ResultReference
from hcns_agent.domain.documents import DocumentType, ParseStatus, SourceFormat
from hcns_agent.domain.errors import ErrorKind, IntakeErrorCode
from hcns_agent.domain.understanding import IdpResult, QualityStatus
from hcns_agent.ports.document_parser import DocumentSource


@dataclass(frozen=True, slots=True)
class DocumentJobRequest:
    job_id: str
    source: DocumentSource
    business_key: str
    correlation_key: str
    idempotency_key: str
    schema_version: str = "2.0.0"
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        required_values = {
            "job_id": self.job_id,
            "business_key": self.business_key,
            "correlation_key": self.correlation_key,
            "idempotency_key": self.idempotency_key,
            "schema_version": self.schema_version,
        }
        for name, value in required_values.items():
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class DocumentJobSummary:
    document_id: str
    business_key: str
    correlation_key: str
    idempotency_key: str
    source_format: SourceFormat
    document_type: DocumentType
    parse_status: ParseStatus
    quality_status: QualityStatus
    review_required: bool
    result_reference: ResultReference
    schema_version: str
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentJobFailure:
    job_id: str
    business_key: str
    correlation_key: str
    idempotency_key: str
    error_code: IntakeErrorCode
    error_kind: ErrorKind
    retryable: bool


@dataclass(frozen=True, slots=True)
class StoredDocumentResult:
    reference: ResultReference
    document_id: str
    source_format: SourceFormat
    parse_status: ParseStatus
    document_type: DocumentType
    quality_status: QualityStatus
    review_required: bool
    schema_version: str


class ResultStore(Protocol):
    def find_by_idempotency_key(self, idempotency_key: str) -> StoredDocumentResult | None:
        """Return an already-persisted result for safe retry."""

    def save(self, result: IdpResult, *, idempotency_key: str) -> StoredDocumentResult:
        """Persist the result durably before job completion."""


class ProcessOrchestratorPort(Protocol):
    def complete_document_job(self, job_id: str, summary: DocumentJobSummary) -> None:
        """Complete a service job with a small routing summary."""

    def fail_document_job(self, failure: DocumentJobFailure) -> None:
        """Report a typed failure without owning process retry policy."""


class HumanReviewPort(Protocol):
    def signal_review_required(self, summary: DocumentJobSummary) -> None:
        """Signal Camunda; this port does not manage User Task state."""


class BusinessEventPublisher(Protocol):
    def publish_document_ready(self, summary: DocumentJobSummary) -> None:
        """Publish a small event containing references, not raw document data."""


class DocumentJobPort(Protocol):
    def execute(self, request: DocumentJobRequest) -> DocumentJobSummary:
        """Process one bounded document job; Camunda owns subsequent workflow state."""


class DocumentProcessingPort(Protocol):
    def execute(self, source: DocumentSource) -> IdpResult:
        """Run intake, classification, extraction, validation, and quality gating."""
