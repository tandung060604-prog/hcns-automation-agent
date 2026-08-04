from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from jsonschema import validate
from synthetic_fixtures import administrative_image_bytes, scanned_pdf_bytes
from test_template_first import docx_bytes, leave_lines, overtime_lines

from hcns_agent.adapters.camunda7.client import (
    Camunda7RestConfig,
    ExternalTask,
    TopicSubscription,
)
from hcns_agent.adapters.camunda7.contract import (
    DMN_QUALITY_INPUT_VARIABLES,
    CamundaQualityAction,
    ProcessVariables,
    QualityRoutingInputs,
    route_quality,
)
from hcns_agent.adapters.camunda7.handlers import (
    ALL_EXTERNAL_TASK_TOPICS,
    DOCUMENT_STAGE_TOPICS,
    build_m4_shadow_handlers,
)
from hcns_agent.adapters.camunda7.review import (
    JsonFileCorrectionStore,
    JsonFileReviewAuditStore,
)
from hcns_agent.adapters.camunda7.runtime import (
    JsonFileTemplateResultStore,
    LocalSessionDocumentSourceStore,
    M4CamundaRuntimeConfig,
    M4TemplateStageOperations,
    TemplatePipeline,
    build_m4_worker,
)
from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.bootstrap import build_default_intake
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.templates.model import TemplateProcessingResult
from hcns_agent.templates.registry import build_default_template_registry
from hcns_agent.templates.service import (
    TemplateProcessingService,
    TemplateTechnicalError,
    build_default_template_processing_service,
)

_ROOT = Path(__file__).resolve().parents[1]


class _QueueClient:
    def __init__(
        self,
        tasks: list[ExternalTask],
        *,
        result_store: JsonFileTemplateResultStore | None = None,
    ) -> None:
        self.tasks = tasks
        self.result_store = result_store
        self.subscriptions: list[tuple[TopicSubscription, ...]] = []
        self.completed: list[ProcessVariables] = []
        self.failures: list[dict[str, object]] = []
        self.business_errors: list[dict[str, object]] = []
        self.events: list[tuple[str, str]] = []

    def fetch_and_lock(
        self,
        subscriptions: tuple[TopicSubscription, ...],
        *,
        max_tasks: int = 1,
        async_response_timeout_ms: int = 10_000,
    ) -> tuple[ExternalTask, ...]:
        self.subscriptions.append(subscriptions)
        if not self.tasks:
            return ()
        return (self.tasks.pop(0),)

    def complete(self, task_id: str, variables: ProcessVariables) -> None:
        reference = variables.get("resultReference")
        if self.result_store is not None and isinstance(reference, str):
            self.result_store.load(reference)
        self.events.append(("complete", task_id))
        self.completed.append(variables)

    def handle_failure(
        self,
        task_id: str,
        *,
        error_message: str,
        retries: int,
        retry_timeout_ms: int,
        error_details: str | None = None,
    ) -> None:
        self.failures.append(
            {
                "taskId": task_id,
                "message": error_message,
                "retries": retries,
                "retryTimeout": retry_timeout_ms,
                "details": error_details,
            }
        )

    def handle_bpmn_error(
        self,
        task_id: str,
        *,
        error_code: str,
        error_message: str,
        variables: ProcessVariables | None = None,
    ) -> None:
        self.business_errors.append(
            {
                "taskId": task_id,
                "code": error_code,
                "message": error_message,
                "variables": variables or {},
            }
        )

    def extend_lock(self, task_id: str, new_duration_ms: int) -> None:
        self.events.append(("extend", task_id))


@dataclass
class _CountingPipeline:
    delegate: TemplateProcessingService
    calls: int = 0

    def process(
        self,
        source: DocumentSource,
        *,
        result_reference: str | None = None,
    ) -> TemplateProcessingResult:
        self.calls += 1
        return self.delegate.process(source, result_reference=result_reference)

    def apply_corrections(
        self,
        stored_payload: dict[str, object],
        corrections: dict[str, object],
    ) -> TemplateProcessingResult:
        return self.delegate.apply_corrections(stored_payload, corrections)


class _TechnicalPipeline:
    def process(
        self,
        source: DocumentSource,
        *,
        result_reference: str | None = None,
    ) -> TemplateProcessingResult:
        raise TemplateTechnicalError("OCR_RUNTIME_UNAVAILABLE")


def _create_session_source(
    private_root: Path,
    reference: str,
    *,
    filename: str = "document.docx",
    content: bytes | None = None,
) -> None:
    input_directory = private_root / "user_uploads" / "sessions" / reference / "input"
    input_directory.mkdir(parents=True)
    (input_directory / filename).write_bytes(
        docx_bytes(leave_lines()) if content is None else content
    )


def _task(
    topic_name: str,
    variables: ProcessVariables,
    *,
    task_id: str = "TASK-SYNTHETIC",
    retries: int | None = 3,
) -> ExternalTask:
    return ExternalTask(
        task_id=task_id,
        topic_name=topic_name,
        retries=retries,
        variables=variables,
    )


def _build_operations(
    private_root: Path,
    pipeline: TemplatePipeline,
) -> tuple[M4TemplateStageOperations, JsonFileTemplateResultStore]:
    result_store = JsonFileTemplateResultStore(private_root / "camunda_m4")
    operations = M4TemplateStageOperations(
        pipeline,
        LocalSessionDocumentSourceStore(private_root),
        result_store,
    )
    return operations, result_store


def _routing_action(projection: ProcessVariables) -> CamundaQualityAction:
    quality_status = projection["qualityStatus"]
    overall_confidence = projection["overallConfidence"]
    assert isinstance(quality_status, str)
    assert isinstance(overall_confidence, (int, float))
    return route_quality(
        QualityRoutingInputs(
            quality_status=quality_status,
            review_required=projection["reviewRequired"] is True,
            sensitive_field_needs_review=(
                projection["sensitiveFieldNeedsReview"] is True
            ),
            missing_critical_field=projection["missingCriticalField"] is True,
            business_inconsistency=projection["businessInconsistency"] is True,
            required_fields_complete=projection["requiredFieldsComplete"] is True,
            overall_confidence=float(overall_confidence),
            auto_continue_enabled=projection["autoContinueEnabled"] is True,
        )
    )


def test_m4_runtime_config_reads_connection_and_private_root_from_environment(
    tmp_path: Path,
) -> None:
    config = M4CamundaRuntimeConfig.from_environment(
        {
            "CAMUNDA_REST_URL": "http://127.0.0.1:8080/engine-rest",
            "CAMUNDA_WORKER_ID": "worker-synthetic",
            "CAMUNDA_BEARER_TOKEN": "synthetic-token",
            "HCNS_CAMUNDA_PRIVATE_ROOT": str(tmp_path.resolve()),
        }
    )

    assert config.private_root == tmp_path.resolve()
    assert config.rest == Camunda7RestConfig(
        base_url="http://127.0.0.1:8080/engine-rest",
        worker_id="worker-synthetic",
        authorization_header="Bearer synthetic-token",
    )
    with pytest.raises(ValueError):
        M4CamundaRuntimeConfig.from_environment(
            {
                "CAMUNDA_REST_URL": "http://127.0.0.1:8080/engine-rest",
                "CAMUNDA_WORKER_ID": "worker-synthetic",
                "HCNS_CAMUNDA_PRIVATE_ROOT": "relative/private",
            }
        )


def test_stage_registry_binds_exactly_six_document_topics_and_fails_closed(
    tmp_path: Path,
) -> None:
    operations, _ = _build_operations(
        tmp_path,
        _CountingPipeline(build_default_template_processing_service()),
    )
    mapping = operations.as_mapping()

    assert set(mapping) == set(DOCUMENT_STAGE_TOPICS)
    build_m4_shadow_handlers(mapping, lambda _: {})
    with pytest.raises(ValueError):
        build_m4_shadow_handlers(
            {
                topic: operation
                for topic, operation in mapping.items()
                if topic != "document_extract"
            },
            lambda _: {},
        )
    with pytest.raises(ValueError):
        build_m4_shadow_handlers(
            {
                **mapping,
                "document_unexpected": lambda _: {},
            },
            lambda _: {},
        )


def test_parse_persists_before_complete_and_replay_reuses_reference(
    tmp_path: Path,
) -> None:
    document_reference = "SESSION-SYNTHETIC"
    _create_session_source(tmp_path, document_reference)
    pipeline = _CountingPipeline(build_default_template_processing_service())
    result_store = JsonFileTemplateResultStore(tmp_path / "camunda_m4")
    variables: ProcessVariables = {
        "documentReference": document_reference,
        "idempotencyKey": "IDEMPOTENCY-SYNTHETIC",
    }
    client = _QueueClient(
        [
            _task("document_parse_content", variables, task_id="TASK-1"),
            _task("document_parse_content", variables, task_id="TASK-2"),
        ],
        result_store=result_store,
    )
    worker = build_m4_worker(
        client=client,
        pipeline=pipeline,
        source_store=LocalSessionDocumentSourceStore(tmp_path),
        result_store=result_store,
    )

    assert worker.run_once() == 1
    assert worker.run_once() == 1

    assert pipeline.calls == 1
    assert client.completed[0]["resultReference"] == client.completed[1]["resultReference"]
    assert client.events == [
        ("extend", "TASK-1"),
        ("complete", "TASK-1"),
        ("extend", "TASK-2"),
        ("complete", "TASK-2"),
    ]
    assert set(DOCUMENT_STAGE_TOPICS).issubset(
        {subscription.topic_name for subscription in client.subscriptions[0]}
    )
    assert {subscription.topic_name for subscription in client.subscriptions[0]} == set(
        ALL_EXTERNAL_TASK_TOPICS
    )
    assert all(
        value is None or isinstance(value, (str, int, float, bool))
        for result in client.completed
        for value in result.values()
    )
    assert "NHÂN VIÊN SYNTHETIC" not in str(client.completed)


def test_persisted_result_drives_reference_only_detect_extract_and_normalize(
    tmp_path: Path,
) -> None:
    document_reference = "SESSION-STAGES"
    idempotency_key = "IDEMPOTENCY-STAGES"
    _create_session_source(tmp_path, document_reference)
    operations, result_store = _build_operations(
        tmp_path,
        _CountingPipeline(build_default_template_processing_service()),
    )
    mapping = operations.as_mapping()
    parsed = mapping["document_parse_content"](
        {
            "documentReference": document_reference,
            "idempotencyKey": idempotency_key,
        }
    )
    reference = parsed["resultReference"]
    assert isinstance(reference, str)
    assert result_store.load(reference).payload["documentType"] == "LEAVE_REQUEST"

    detected = mapping["document_detect_type"](
        {
            "resultReference": reference,
            "declaredDocumentType": "LEAVE_REQUEST",
            "idempotencyKey": idempotency_key,
        }
    )
    mismatch = mapping["document_detect_type"](
        {
            "resultReference": reference,
            "declaredDocumentType": "OVERTIME_REQUEST",
            "idempotencyKey": idempotency_key,
        }
    )
    extracted = mapping["document_extract"](
        {
            "resultReference": reference,
            "workflowDocumentType": "LEAVE_REQUEST",
            "idempotencyKey": idempotency_key,
        }
    )
    normalized = mapping["document_normalize_validate"](
        {"resultReference": reference, "idempotencyKey": idempotency_key}
    )
    stored = result_store.load(reference)
    correction_reference = JsonFileCorrectionStore(
        tmp_path / "camunda_m4"
    ).save(
        result_reference=reference,
        expected_payload_hash=stored.payload_hash,
        changes={"reason": "SYNTHETIC CORRECTED REASON"},
    )
    corrected = mapping["document_apply_corrections"](
        {
            "resultReference": reference,
            "resultPayloadHash": stored.payload_hash,
            "correctionsReference": correction_reference,
            "caseVersion": 1,
            "idempotencyKey": idempotency_key,
        }
    )

    assert detected["classificationStatus"] == "CONFIRMED"
    assert detected["detectedDocumentType"] == "LEAVE_REQUEST"
    assert mismatch["classificationStatus"] == "MISMATCH"
    assert extracted["extractedDataReference"] == reference
    assert {name: normalized[name] for name in DMN_QUALITY_INPUT_VARIABLES} == {
        "qualityStatus": "PASS",
        "reviewRequired": False,
        "sensitiveFieldNeedsReview": False,
        "missingCriticalField": False,
        "businessInconsistency": False,
        "requiredFieldsComplete": True,
        "overallConfidence": 1.0,
        "autoContinueEnabled": False,
    }
    assert normalized["recommendedAction"] == "AUTO_CONTINUE"
    assert normalized["reviewReasonCodes"] == "SHADOW_REVIEW_REQUIRED"
    assert _routing_action(normalized) is CamundaQualityAction.USER_REVIEW
    process_schema = json.loads(
        (_ROOT / "schemas" / "camunda_process_variables.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validate(normalized, process_schema)
    assert corrected["resultReference"] == reference
    assert corrected["caseVersion"] == 2
    assert corrected["resultPayloadHash"] != stored.payload_hash
    assert "NHÂN VIÊN SYNTHETIC" not in str((detected, extracted, normalized, corrected))


def test_review_audit_binds_reviewer_version_and_payload_hash(tmp_path: Path) -> None:
    document_reference = "SESSION-AUDIT"
    idempotency_key = "IDEMPOTENCY-AUDIT"
    _create_session_source(tmp_path, document_reference)
    operations, result_store = _build_operations(
        tmp_path,
        _CountingPipeline(build_default_template_processing_service()),
    )
    parsed = operations.as_mapping()["document_parse_content"](
        {
            "documentReference": document_reference,
            "idempotencyKey": idempotency_key,
        }
    )
    reference = parsed["resultReference"]
    payload_hash = parsed["resultPayloadHash"]
    assert isinstance(reference, str)
    assert isinstance(payload_hash, str)

    result = operations.review_audit_operation(
        {
            "resultReference": reference,
            "resultPayloadHash": payload_hash,
            "reviewStage": "USER",
            "reviewerId": "reviewer-synthetic",
            "reviewedAt": "2026-08-04T10:00:00.123456789Z",
            "caseVersion": 1,
            "idempotencyKey": idempotency_key,
            "userReviewDecision": "CONFIRMED",
            "reviewReasonCodes": "SHADOW_REVIEW_REQUIRED",
        }
    )

    audit_reference = result["reviewAuditReference"]
    assert isinstance(audit_reference, str)
    audit = JsonFileReviewAuditStore(result_store.root).load(audit_reference)
    assert audit["reviewerId"] == "reviewer-synthetic"
    assert audit["caseVersion"] == 1
    assert audit["reviewedPayloadHash"] == payload_hash
    assert "data" not in audit


@pytest.mark.parametrize(
    ("template_label", "lines_factory"),
    [
        ("LEAVE", leave_lines),
        ("OVERTIME", overtime_lines),
    ],
)
@pytest.mark.parametrize(
    ("filename", "content_factory"),
    [
        ("document.png", administrative_image_bytes),
        ("document.pdf", scanned_pdf_bytes),
    ],
)
def test_ocr_projection_is_review_only_and_cannot_auto_continue(
    tmp_path: Path,
    template_label: str,
    lines_factory: Callable[[], list[str]],
    filename: str,
    content_factory: Callable[[], bytes],
) -> None:
    format_label = Path(filename).suffix.removeprefix(".").upper()
    document_reference = f"SESSION-OCR-{template_label}-{format_label}"
    idempotency_key = f"IDEMPOTENCY-OCR-{template_label}-{format_label}"
    _create_session_source(
        tmp_path,
        document_reference,
        filename=filename,
        content=content_factory(),
    )
    ocr = DeterministicMockOcrEngine(
        text="\n".join(lines_factory()),
        confidence=0.93,
    )
    service = TemplateProcessingService(
        intake=build_default_intake(ocr),
        registry=build_default_template_registry(),
        ocr_engine=ocr,
    )
    operations, _ = _build_operations(tmp_path, _CountingPipeline(service))
    mapping = operations.as_mapping()
    parsed = mapping["document_parse_content"](
        {
            "documentReference": document_reference,
            "idempotencyKey": idempotency_key,
        }
    )
    reference = parsed["resultReference"]
    assert isinstance(reference, str)

    projection = mapping["document_normalize_validate"](
        {"resultReference": reference, "idempotencyKey": idempotency_key}
    )

    assert projection["qualityStatus"] == "REVIEW_REQUIRED"
    assert projection["reviewRequired"] is True
    assert projection["sensitiveFieldNeedsReview"] is True
    assert projection["autoContinueEnabled"] is False
    assert _routing_action(projection) is CamundaQualityAction.HR_REVIEW
    assert "AUTO_CONTINUE" not in projection.values()
    assert "NHÂN VIÊN SYNTHETIC" not in str(projection)


def test_missing_required_field_routes_to_reupload(tmp_path: Path) -> None:
    document_reference = "SESSION-MISSING-CRITICAL"
    idempotency_key = "IDEMPOTENCY-MISSING-CRITICAL"
    missing_job_title = [
        line for line in leave_lines() if not line.startswith("Chức vụ:")
    ]
    _create_session_source(
        tmp_path,
        document_reference,
        content=docx_bytes(missing_job_title),
    )
    operations, _ = _build_operations(
        tmp_path,
        _CountingPipeline(build_default_template_processing_service()),
    )
    mapping = operations.as_mapping()
    parsed = mapping["document_parse_content"](
        {
            "documentReference": document_reference,
            "idempotencyKey": idempotency_key,
        }
    )
    reference = parsed["resultReference"]
    assert isinstance(reference, str)

    projection = mapping["document_normalize_validate"](
        {"resultReference": reference, "idempotencyKey": idempotency_key}
    )

    assert projection["missingCriticalField"] is True
    assert projection["requiredFieldsComplete"] is False
    assert projection["autoContinueEnabled"] is False
    assert _routing_action(projection) is CamundaQualityAction.REQUEST_REUPLOAD


def test_business_inconsistency_routes_to_hr_review(tmp_path: Path) -> None:
    document_reference = "SESSION-INCONSISTENT"
    idempotency_key = "IDEMPOTENCY-INCONSISTENT"
    inconsistent = [
        line.replace(
            "tổng thời gian dự kiến là 6 giờ",
            "tổng thời gian dự kiến là 5 giờ",
        )
        for line in overtime_lines()
    ]
    _create_session_source(
        tmp_path,
        document_reference,
        content=docx_bytes(inconsistent),
    )
    operations, result_store = _build_operations(
        tmp_path,
        _CountingPipeline(build_default_template_processing_service()),
    )
    mapping = operations.as_mapping()
    parsed = mapping["document_parse_content"](
        {
            "documentReference": document_reference,
            "idempotencyKey": idempotency_key,
        }
    )
    reference = parsed["resultReference"]
    assert isinstance(reference, str)

    projection = mapping["document_normalize_validate"](
        {"resultReference": reference, "idempotencyKey": idempotency_key}
    )

    assert projection["businessInconsistency"] is True
    assert projection["missingCriticalField"] is False
    assert _routing_action(projection) is CamundaQualityAction.HR_REVIEW

    stored = result_store.load(reference)
    correction_reference = JsonFileCorrectionStore(
        result_store.root
    ).save(
        result_reference=reference,
        expected_payload_hash=stored.payload_hash,
        changes={"totalOvertimeHours": 6.0},
    )
    corrected = mapping["document_apply_corrections"](
        {
            "resultReference": reference,
            "resultPayloadHash": stored.payload_hash,
            "correctionsReference": correction_reference,
            "caseVersion": 1,
            "idempotencyKey": idempotency_key,
        }
    )
    corrected_projection = mapping["document_normalize_validate"](
        {"resultReference": reference, "idempotencyKey": idempotency_key}
    )

    assert corrected["caseVersion"] == 2
    assert corrected_projection["businessInconsistency"] is False
    assert corrected_projection["qualityStatus"] == "PASS"
    assert _routing_action(corrected_projection) is CamundaQualityAction.USER_REVIEW


def test_invalid_input_uses_bpmn_error_and_technical_failure_decrements_retry(
    tmp_path: Path,
) -> None:
    invalid_client = _QueueClient(
        [
            _task(
                "document_validate_file",
                {
                    "applicationId": "APPLICATION-SYNTHETIC",
                    "documentReference": "../outside",
                    "idempotencyKey": "IDEMPOTENCY-INVALID",
                },
            )
        ]
    )
    invalid_worker = build_m4_worker(
        client=invalid_client,
        pipeline=_CountingPipeline(build_default_template_processing_service()),
        source_store=LocalSessionDocumentSourceStore(tmp_path),
        result_store=JsonFileTemplateResultStore(tmp_path / "invalid-results"),
    )

    invalid_worker.run_once()

    assert invalid_client.business_errors[0]["code"] == "DOCUMENT_INPUT_INVALID"
    assert not invalid_client.failures

    document_reference = "SESSION-TECHNICAL"
    _create_session_source(tmp_path, document_reference)
    technical_client = _QueueClient(
        [
            _task(
                "document_parse_content",
                {
                    "documentReference": document_reference,
                    "idempotencyKey": "IDEMPOTENCY-TECHNICAL",
                },
                retries=2,
            )
        ]
    )
    technical_worker = build_m4_worker(
        client=technical_client,
        pipeline=_TechnicalPipeline(),
        source_store=LocalSessionDocumentSourceStore(tmp_path),
        result_store=JsonFileTemplateResultStore(tmp_path / "technical-results"),
    )

    technical_worker.run_once()

    assert technical_client.failures[0]["retries"] == 1
    assert technical_client.failures[0]["message"] == "Template processing failed"
    assert not technical_client.completed
    assert not technical_client.business_errors
