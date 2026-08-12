from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from synthetic_fixtures import synthetic_cv_pdf_bytes

from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.adapters.result_store import JsonFileResultStore
from hcns_agent.application.document_job import DocumentJobHandler
from hcns_agent.bootstrap import build_default_pipeline
from hcns_agent.domain.canonical import ResultReference
from hcns_agent.domain.documents import DocumentType, ParseStatus, SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, ErrorKind
from hcns_agent.domain.understanding import IdpResult, QualityStatus
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.orchestration import (
    DocumentJobFailure,
    DocumentJobRequest,
    DocumentJobSummary,
    StoredDocumentResult,
)


class _RecordingStore:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.saved: StoredDocumentResult | None = None
        self.save_count = 0

    def find_by_idempotency_key(self, idempotency_key: str) -> StoredDocumentResult | None:
        return self.saved

    def save(self, result: IdpResult, *, idempotency_key: str) -> StoredDocumentResult:
        self.events.append("save")
        self.save_count += 1
        document = result.canonical_document
        self.saved = StoredDocumentResult(
            reference=ResultReference(
                uri="document-store://synthetic-result",
                checksum_sha256="0" * 64,
                schema_version=result.schema_version,
                storage_version="synthetic-v1",
            ),
            document_id=document.document_id,
            source_format=document.source_format,
            parse_status=document.parse_status,
            document_type=result.classification.document_type,
            quality_status=result.quality.status,
            review_required=result.quality.review_required,
            schema_version=result.schema_version,
        )
        return self.saved


class _RecordingOrchestrator:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.completed: list[DocumentJobSummary] = []
        self.failed: list[DocumentJobFailure] = []

    def complete_document_job(self, job_id: str, summary: DocumentJobSummary) -> None:
        self.events.append("complete")
        self.completed.append(summary)

    def fail_document_job(self, failure: DocumentJobFailure) -> None:
        self.events.append("fail")
        self.failed.append(failure)


class DocumentJobHandlerTests(TestCase):
    def setUp(self) -> None:
        self.events: list[str] = []
        self.store = _RecordingStore(self.events)
        self.orchestrator = _RecordingOrchestrator(self.events)
        self.handler = DocumentJobHandler(
            build_default_pipeline(DeterministicMockOcrEngine()),
            self.store,
            self.orchestrator,
        )

    @staticmethod
    def request(content: bytes | None = None) -> DocumentJobRequest:
        return DocumentJobRequest(
            job_id="JOB-SYNTHETIC-001",
            source=DocumentSource(
                document_id="DOC-SYNTHETIC-001",
                filename="cv.pdf",
                content=content if content is not None else synthetic_cv_pdf_bytes(),
            ),
            business_key="BUSINESS-SYNTHETIC-001",
            correlation_key="CORRELATION-SYNTHETIC-001",
            idempotency_key="IDEMPOTENCY-SYNTHETIC-001",
        )

    def test_result_is_saved_before_job_completion(self) -> None:
        summary = self.handler.execute(self.request())

        self.assertEqual(["save", "complete"], self.events)
        self.assertIs(SourceFormat.PDF_TEXT, summary.source_format)
        self.assertIs(DocumentType.CV, summary.document_type)
        self.assertIs(ParseStatus.SUCCESS, summary.parse_status)
        self.assertIs(QualityStatus.REVIEW_REQUIRED, summary.quality_status)

    def test_retry_reuses_idempotent_result_without_second_save(self) -> None:
        first = self.handler.execute(self.request())
        second = self.handler.execute(self.request())

        self.assertEqual(first.result_reference, second.result_reference)
        self.assertEqual(1, self.store.save_count)
        self.assertEqual(2, len(self.orchestrator.completed))

    def test_business_error_is_reported_without_process_retry_implementation(self) -> None:
        with self.assertRaises(DocumentIntakeError):
            self.handler.execute(self.request(b"unknown synthetic content"))

        self.assertEqual(["fail"], self.events)
        self.assertIs(ErrorKind.BUSINESS, self.orchestrator.failed[0].error_kind)
        self.assertFalse(self.orchestrator.failed[0].retryable)

    def test_json_result_store_persists_opaque_reference_and_idempotency(self) -> None:
        result = build_default_pipeline(DeterministicMockOcrEngine()).execute(self.request().source)
        with TemporaryDirectory() as temporary_directory:
            store = JsonFileResultStore(Path(temporary_directory).resolve())
            first = store.save(result, idempotency_key="SYNTHETIC-KEY")
            second = store.find_by_idempotency_key("SYNTHETIC-KEY")

            self.assertEqual(first, second)
            self.assertTrue(first.reference.uri.startswith("document-store://"))
            self.assertEqual(64, len(first.reference.checksum_sha256))

    def test_json_result_store_concurrent_retries_keep_one_artifact(self) -> None:
        result = build_default_pipeline(DeterministicMockOcrEngine()).execute(
            self.request().source
        )
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            store = JsonFileResultStore(root)
            with ThreadPoolExecutor(max_workers=4) as executor:
                saved = list(
                    executor.map(
                        lambda _: store.save(result, idempotency_key="CONCURRENT-KEY"),
                        range(4),
                    )
                )

            self.assertEqual([saved[0]] * 4, saved)
            self.assertEqual(1, len(list((root / "documents").glob("*.json"))))
            self.assertEqual(1, len(list((root / "idempotency").glob("*.json"))))
