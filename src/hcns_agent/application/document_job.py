"""Handle an IDP service job without owning long-running process state."""

from __future__ import annotations

from hcns_agent.domain.errors import (
    DocumentIntakeError,
    ErrorKind,
    IntakeErrorCode,
)
from hcns_agent.ports.orchestration import (
    DocumentJobFailure,
    DocumentJobRequest,
    DocumentJobSummary,
    DocumentProcessingPort,
    ProcessOrchestratorPort,
    ResultStore,
    StoredDocumentResult,
)


class DocumentJobHandler:
    def __init__(
        self,
        pipeline: DocumentProcessingPort,
        result_store: ResultStore,
        orchestrator: ProcessOrchestratorPort,
    ) -> None:
        self._pipeline = pipeline
        self._result_store = result_store
        self._orchestrator = orchestrator

    def execute(self, request: DocumentJobRequest) -> DocumentJobSummary:
        existing = self._result_store.find_by_idempotency_key(request.idempotency_key)
        if existing is not None:
            summary = self._summary(request, existing)
            self._orchestrator.complete_document_job(request.job_id, summary)
            return summary

        try:
            result = self._pipeline.execute(request.source)
            stored = self._result_store.save(
                result,
                idempotency_key=request.idempotency_key,
            )
            summary = self._summary(request, stored)
            self._orchestrator.complete_document_job(request.job_id, summary)
            return summary
        except DocumentIntakeError as error:
            self._report_failure(request, error)
            raise
        except Exception as error:
            wrapped = DocumentIntakeError(
                IntakeErrorCode.PARSE_FAILED,
                "Unexpected technical failure while processing document",
                kind=ErrorKind.TECHNICAL,
                retryable=True,
            )
            self._report_failure(request, wrapped)
            raise wrapped from error

    @staticmethod
    def _summary(request: DocumentJobRequest, stored: StoredDocumentResult) -> DocumentJobSummary:
        return DocumentJobSummary(
            document_id=stored.document_id,
            business_key=request.business_key,
            correlation_key=request.correlation_key,
            idempotency_key=request.idempotency_key,
            source_format=stored.source_format,
            document_type=stored.document_type,
            parse_status=stored.parse_status,
            quality_status=stored.quality_status,
            review_required=stored.review_required,
            result_reference=stored.reference,
            schema_version=stored.schema_version,
        )

    def _report_failure(self, request: DocumentJobRequest, error: DocumentIntakeError) -> None:
        self._orchestrator.fail_document_job(
            DocumentJobFailure(
                job_id=request.job_id,
                business_key=request.business_key,
                correlation_key=request.correlation_key,
                idempotency_key=request.idempotency_key,
                error_code=error.code,
                error_kind=error.kind,
                retryable=error.retryable,
            )
        )
