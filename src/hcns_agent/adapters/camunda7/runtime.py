"""Local M4 composition root for Template-first Camunda 7 workers."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast

from hcns_agent.adapters.camunda7.client import (
    Camunda7ExternalTaskClient,
    Camunda7RestConfig,
    CamundaExternalTaskClient,
)
from hcns_agent.adapters.camunda7.contract import (
    DMN_QUALITY_INPUT_VARIABLES,
    M4_CLOSED_SET_WORKFLOW_DOCUMENT_TYPES,
    M4_SHADOW_POLICY,
    ProcessValue,
    ProcessVariables,
    map_document_type,
    validate_dmn_quality_variables,
)
from hcns_agent.adapters.camunda7.handlers import (
    DOCUMENT_STAGE_TOPICS,
    StageOperation,
    build_m4_shadow_handlers,
)
from hcns_agent.adapters.camunda7.review import (
    JsonFileCorrectionStore,
    JsonFileReviewAuditStore,
    ReviewArtifactStoreError,
)
from hcns_agent.adapters.camunda7.worker import (
    Camunda7ExternalTaskWorker,
    CamundaBusinessError,
    CamundaTechnicalError,
    LockExtensionPolicy,
)
from hcns_agent.domain.documents import DocumentType
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.templates.model import RecommendedAction, TemplateProcessingResult
from hcns_agent.templates.service import (
    TemplateTechnicalError,
    TemplateUnsupportedError,
    build_local_template_processing_service,
)

_DOCUMENT_REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_RESULT_REFERENCE_PATTERN = re.compile(r"camunda-m4://result/([0-9a-f]{64})")
_SUPPORTED_SOURCE_SUFFIXES = frozenset({".docx", ".pdf", ".png", ".jpg", ".jpeg"})
_SOURCE_MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
_PRIVATE_DMN_PROJECTION_KEY = "_m4DmnQualityVariables"
_PRIVATE_CORRECTION_APPLICATION_KEY = "_m4CorrectionApplication"
_REVIEW_ONLY_VALIDATION_CODES = frozenset(
    {
        "OCR_REVIEW_REQUIRED",
        "TEMPLATE_ANCHOR_PARTIAL",
    }
)
_SENSITIVE_FIELDS_BY_TEMPLATE = {
    "leave-request-v1": frozenset(
        {"employeeName", "employeeId", "phone", "address", "reason"}
    ),
    "overtime-request-v1": frozenset(
        {"employeeName", "employeeId", "phone", "address", "reason"}
    ),
    "probation-contract-v1": frozenset(
        {"employeeName", "employeeId", "salary", "effectiveDate", "employerName"}
    ),
    "probation-contract-v2": frozenset(
        {
            "employee_name",
            "employee_id_number",
            "probation_salary_monthly",
            "effective_date",
            "employer_name",
        }
    ),
    "cv-v1": frozenset(
        {"fullName", "email", "phoneNumber", "address", "experience"}
    ),
    "cv-v2": frozenset(
        {"full_name", "email", "phone_number", "address", "experience"}
    ),
    "ielts-certificate-v1": frozenset(
        {"recipientName", "credentialId", "overallScore", "issueDate"}
    ),
    "ielts-certificate-v2": frozenset(
        {"recipient_name", "credential_id", "overall_score", "issue_date"}
    ),
    "vietnam-citizen-id-front-v1": frozenset(
        {"idNumber", "fullName", "dateOfBirth", "placeOfOrigin", "placeOfResidence"}
    ),
}
_ROUTING_CRITICAL_FIELDS_BY_TEMPLATE = {
    "probation-contract-v2": frozenset(
        {
            "effective_date",
            "probation_end_date",
            "employer_name",
            "employee_name",
            "job_title",
            "probation_salary_monthly",
        }
    ),
    "cv-v2": frozenset(
        {
            "full_name",
            "headline",
            "email",
            "phone_number",
            "address",
            "education",
            "experience",
            "skills",
        }
    ),
    "ielts-certificate-v2": frozenset(
        {"recipient_name", "credential_id", "credential_type", "overall_score", "issue_date"}
    ),
}
M4_LONG_RUNNING_LOCK_POLICY = LockExtensionPolicy(
    topic_names=frozenset({"document_parse_content"}),
    new_duration_ms=180_000,
)


class DocumentReferenceError(ValueError):
    """An opaque source reference is missing, ambiguous, or outside its private root."""


class DocumentSourceStoreError(RuntimeError):
    """The local private source store could not be read safely."""


class TemplateResultStoreError(RuntimeError):
    """The private Template-first result store is unavailable or inconsistent."""


class TemplatePipeline(Protocol):
    def process(
        self,
        source: DocumentSource,
        *,
        result_reference: str | None = None,
    ) -> TemplateProcessingResult:
        """Process one source through the closed-set Template-first pipeline."""

    def apply_corrections(
        self,
        stored_payload: Mapping[str, object],
        corrections: Mapping[str, object],
    ) -> TemplateProcessingResult:
        """Apply private corrections and rerun the frozen template validator."""


class DocumentSourceStore(Protocol):
    def load(self, document_reference: str) -> DocumentSource:
        """Resolve one opaque reference inside private local storage."""


@dataclass(frozen=True, slots=True)
class StoredTemplateResult:
    reference: str
    document_reference_digest: str
    payload: dict[str, object]

    @property
    def payload_hash(self) -> str:
        return _json_payload_digest(self.payload)


class TemplateResultStore(Protocol):
    def result_reference(self, idempotency_key: str) -> str:
        """Return the deterministic opaque reference reserved for a result."""

    def find_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> StoredTemplateResult | None:
        """Find a previously persisted result for retry/replay."""

    def load(self, result_reference: str) -> StoredTemplateResult:
        """Load a persisted private result through its opaque reference."""

    def save(
        self,
        result: TemplateProcessingResult,
        *,
        idempotency_key: str,
        document_reference: str,
    ) -> StoredTemplateResult:
        """Persist a private result and its idempotency index atomically."""

    def apply_correction(
        self,
        *,
        result_reference: str,
        correction_reference: str,
        expected_payload_hash: str,
        corrected_result: TemplateProcessingResult,
        next_case_version: int,
    ) -> StoredTemplateResult:
        """Persist one idempotent corrected revision while retaining history."""


@dataclass(frozen=True, slots=True)
class M4CamundaRuntimeConfig:
    rest: Camunda7RestConfig
    private_root: Path

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> M4CamundaRuntimeConfig:
        values = os.environ if environment is None else environment
        rest = Camunda7RestConfig.from_environment(values)
        raw_private_root = values.get("HCNS_CAMUNDA_PRIVATE_ROOT", "").strip()
        if not raw_private_root:
            raise ValueError("HCNS_CAMUNDA_PRIVATE_ROOT is required")
        private_root = Path(raw_private_root)
        if not private_root.is_absolute():
            raise ValueError("HCNS_CAMUNDA_PRIVATE_ROOT must be absolute")
        private_root = private_root.resolve()
        if not private_root.is_dir():
            raise ValueError("HCNS_CAMUNDA_PRIVATE_ROOT must be an existing directory")
        return cls(rest=rest, private_root=private_root)


class LocalSessionDocumentSourceStore:
    """Resolve OCR Lab session ids without placing private paths in Camunda."""

    def __init__(self, private_root: Path) -> None:
        if not private_root.is_absolute():
            raise ValueError("Private source root must be absolute")
        self._private_root = private_root.resolve()
        if not self._private_root.is_dir():
            raise ValueError("Private source root must be an existing directory")
        self._sessions_root = self._private_root / "user_uploads" / "sessions"

    def load(self, document_reference: str) -> DocumentSource:
        if _DOCUMENT_REFERENCE_PATTERN.fullmatch(document_reference) is None:
            raise DocumentReferenceError("Document reference is invalid")
        input_directory = self._sessions_root / document_reference / "input"
        try:
            candidates = tuple(
                path
                for path in input_directory.glob("document.*")
                if path.is_file() and path.suffix.casefold() in _SUPPORTED_SOURCE_SUFFIXES
            )
        except OSError as error:
            raise DocumentSourceStoreError("Private document source is unavailable") from error
        if len(candidates) != 1:
            raise DocumentReferenceError("Document reference must resolve to exactly one source")
        source_path = candidates[0].resolve()
        if not source_path.is_relative_to(self._private_root):
            raise DocumentReferenceError("Document reference resolves outside private storage")
        try:
            content = source_path.read_bytes()
        except OSError as error:
            raise DocumentSourceStoreError("Private document source is unavailable") from error
        suffix = source_path.suffix.casefold()
        return DocumentSource(
            document_id=document_reference,
            filename=source_path.name,
            content=content,
            declared_media_type=_SOURCE_MEDIA_TYPES[suffix],
            source_reference=document_reference,
        )


class JsonFileTemplateResultStore:
    """Private JSON store with deterministic references and an idempotency index."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise ValueError("Template result store root must be absolute")
        self._root = root.resolve()
        self._results = self._root / "results"
        self._idempotency = self._root / "idempotency"
        self._revisions = self._root / "result_revisions"
        try:
            self._results.mkdir(parents=True, exist_ok=True)
            self._idempotency.mkdir(parents=True, exist_ok=True)
            self._revisions.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise TemplateResultStoreError("Template result store is unavailable") from error

    def result_reference(self, idempotency_key: str) -> str:
        return f"camunda-m4://result/{_idempotency_digest(idempotency_key)}"

    @property
    def root(self) -> Path:
        return self._root

    def find_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> StoredTemplateResult | None:
        digest = _idempotency_digest(idempotency_key)
        index_path = self._idempotency / f"{digest}.json"
        if not index_path.exists():
            return None
        return self._load_digest(digest)

    def load(self, result_reference: str) -> StoredTemplateResult:
        match = _RESULT_REFERENCE_PATTERN.fullmatch(result_reference)
        if match is None:
            raise TemplateResultStoreError("Template result reference is invalid")
        return self._load_digest(match.group(1))

    def save(
        self,
        result: TemplateProcessingResult,
        *,
        idempotency_key: str,
        document_reference: str,
    ) -> StoredTemplateResult:
        expected_reference = self.result_reference(idempotency_key)
        document_digest = _document_reference_digest(document_reference)
        existing = self.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.document_reference_digest != document_digest:
                raise ValueError("Idempotency key belongs to another document reference")
            return existing

        payload = result.public_dict()
        payload[_PRIVATE_DMN_PROJECTION_KEY] = _build_template_quality_projection(result)
        variables = payload.get("camundaVariables")
        if not isinstance(variables, dict):
            raise TemplateResultStoreError("Template result has no Camunda projection")
        if variables.get("extractedDataReference") != expected_reference:
            raise TemplateResultStoreError("Template result reference is inconsistent")

        digest = _idempotency_digest(idempotency_key)
        result_path = self._results / f"{digest}.json"
        index_path = self._idempotency / f"{digest}.json"
        try:
            _atomic_write_json(result_path, payload)
            _atomic_write_json(
                index_path,
                {
                    "reference": expected_reference,
                    "documentReferenceDigest": document_digest,
                },
            )
        except OSError as error:
            raise TemplateResultStoreError("Template result could not be persisted") from error
        return StoredTemplateResult(
            reference=expected_reference,
            document_reference_digest=document_digest,
            payload=payload,
        )

    def apply_correction(
        self,
        *,
        result_reference: str,
        correction_reference: str,
        expected_payload_hash: str,
        corrected_result: TemplateProcessingResult,
        next_case_version: int,
    ) -> StoredTemplateResult:
        if next_case_version <= 1:
            raise ValueError("Corrected case version must advance")
        current = self.load(result_reference)
        existing_application = current.payload.get(_PRIVATE_CORRECTION_APPLICATION_KEY)
        if isinstance(existing_application, dict) and (
            existing_application.get("correctionReference") == correction_reference
            and existing_application.get("inputPayloadHash") == expected_payload_hash
            and existing_application.get("caseVersion") == next_case_version
        ):
            return current
        if current.payload_hash != expected_payload_hash:
            raise ValueError("Correction is based on a stale result payload")

        corrected_payload = corrected_result.public_dict()
        corrected_payload[_PRIVATE_DMN_PROJECTION_KEY] = (
            _build_template_quality_projection(corrected_result)
        )
        corrected_payload[_PRIVATE_CORRECTION_APPLICATION_KEY] = {
            "correctionReference": correction_reference,
            "inputPayloadHash": expected_payload_hash,
            "caseVersion": next_case_version,
        }
        variables = corrected_payload.get("camundaVariables")
        if (
            not isinstance(variables, dict)
            or variables.get("extractedDataReference") != result_reference
        ):
            raise TemplateResultStoreError("Corrected result reference is inconsistent")

        match = _RESULT_REFERENCE_PATTERN.fullmatch(result_reference)
        if match is None:
            raise TemplateResultStoreError("Template result reference is invalid")
        digest = match.group(1)
        revision_directory = self._revisions / digest
        result_path = self._results / f"{digest}.json"
        try:
            revision_directory.mkdir(parents=True, exist_ok=True)
            revision_path = revision_directory / f"{current.payload_hash}.json"
            if not revision_path.exists():
                _atomic_write_json(revision_path, current.payload)
            _atomic_write_json(result_path, corrected_payload)
        except OSError as error:
            raise TemplateResultStoreError("Corrected result could not be persisted") from error
        return StoredTemplateResult(
            reference=result_reference,
            document_reference_digest=current.document_reference_digest,
            payload=corrected_payload,
        )

    def _load_digest(self, digest: str) -> StoredTemplateResult:
        try:
            index_payload = json.loads(
                (self._idempotency / f"{digest}.json").read_text(encoding="utf-8")
            )
            result_payload = json.loads(
                (self._results / f"{digest}.json").read_text(encoding="utf-8")
            )
            reference = index_payload["reference"]
            document_digest = index_payload["documentReferenceDigest"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise TemplateResultStoreError("Stored Template-first result is unreadable") from error
        expected_reference = f"camunda-m4://result/{digest}"
        if (
            reference != expected_reference
            or not isinstance(document_digest, str)
            or not isinstance(result_payload, dict)
        ):
            raise TemplateResultStoreError("Stored Template-first metadata is inconsistent")
        return StoredTemplateResult(
            reference=expected_reference,
            document_reference_digest=document_digest,
            payload=cast(dict[str, object], result_payload),
        )


class M4TemplateStageOperations:
    """Bind six BPMN document topics to one persisted Template-first result."""

    def __init__(
        self,
        pipeline: TemplatePipeline,
        source_store: DocumentSourceStore,
        result_store: TemplateResultStore,
        correction_store: JsonFileCorrectionStore | None = None,
        review_audit_store: JsonFileReviewAuditStore | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._source_store = source_store
        self._result_store = result_store
        if correction_store is None or review_audit_store is None:
            if not isinstance(result_store, JsonFileTemplateResultStore):
                raise ValueError("Private review stores are required for this result store")
            correction_store = correction_store or JsonFileCorrectionStore(result_store.root)
            review_audit_store = review_audit_store or JsonFileReviewAuditStore(
                result_store.root
            )
        self._correction_store = correction_store
        self._review_audit_store = review_audit_store

    def as_mapping(self) -> Mapping[str, StageOperation]:
        operations: dict[str, StageOperation] = {
            "document_validate_file": self._validate_file,
            "document_parse_content": self._parse_content,
            "document_detect_type": self._detect_type,
            "document_extract": self._extract,
            "document_normalize_validate": self._normalize_validate,
            "document_apply_corrections": self._apply_corrections,
        }
        if set(operations) != set(DOCUMENT_STAGE_TOPICS):
            raise ValueError("M4 stage operation registry is incomplete")
        return operations

    def review_audit_operation(
        self,
        variables: Mapping[str, ProcessValue],
    ) -> ProcessVariables:
        result_reference = _required_reference(variables, "resultReference")
        result_payload_hash = _required_sha256(variables, "resultPayloadHash")
        stored = self._load_result(result_reference)
        if stored.payload_hash != result_payload_hash:
            raise _correction_error("Review is based on a stale result payload")

        review_stage = _required_reference(variables, "reviewStage")
        decision_name = {
            "USER": "userReviewDecision",
            "HR": "hrReviewDecision",
        }.get(review_stage)
        if decision_name is None:
            raise _input_error("Review stage is invalid")
        decision = _required_reference(variables, decision_name)
        allowed_decisions = {
            "USER": frozenset(
                {"CONFIRMED", "CORRECTED", "REQUEST_REUPLOAD", "UNRESOLVED"}
            ),
            "HR": frozenset(
                {"CONFIRMED", "CORRECTED", "REQUEST_REUPLOAD", "REJECTED"}
            ),
        }
        if decision not in allowed_decisions[review_stage]:
            raise _input_error("Review decision is invalid")
        corrections_reference = variables.get("correctionsReference")
        if decision == "CORRECTED" and (
            not isinstance(corrections_reference, str)
            or not corrections_reference.strip()
        ):
            raise _correction_error("Correction reference is required")

        case_version = _required_positive_int(variables, "caseVersion")
        event: ProcessVariables = {
            "reviewStage": review_stage,
            "reviewerId": _required_reference(variables, "reviewerId"),
            "reviewedAt": _required_iso_timestamp(variables, "reviewedAt"),
            "caseVersion": case_version,
            "reviewedPayloadHash": result_payload_hash,
            "resultReference": result_reference,
            "idempotencyKey": _required_reference(variables, "idempotencyKey"),
            decision_name: decision,
        }
        for name in (
            "correctionsReference",
            "hrReviewNoteReference",
            "reviewReasonCodes",
        ):
            value = variables.get(name)
            if isinstance(value, str) and value.strip():
                event[name] = value.strip()
        try:
            audit_reference = self._review_audit_store.record(event)
        except (ReviewArtifactStoreError, ValueError) as error:
            raise CamundaTechnicalError("Private review audit store is unavailable") from error
        return {
            "reviewAuditReference": audit_reference,
            "reviewedPayloadHash": result_payload_hash,
        }

    def _validate_file(self, variables: Mapping[str, ProcessValue]) -> ProcessVariables:
        document_reference = _required_reference(variables, "documentReference")
        self._load_source(document_reference)
        return {"fileValidationStatus": "VALID"}

    def _parse_content(self, variables: Mapping[str, ProcessValue]) -> ProcessVariables:
        document_reference = _required_reference(variables, "documentReference")
        idempotency_key = _required_reference(variables, "idempotencyKey")
        try:
            existing = self._result_store.find_by_idempotency_key(idempotency_key)
        except TemplateResultStoreError as error:
            raise CamundaTechnicalError("Template result store is unavailable") from error
        if existing is not None:
            if existing.document_reference_digest != _document_reference_digest(
                document_reference
            ):
                raise _input_error("Idempotency key does not match the document reference")
            return _parse_process_variables(existing)

        source = self._load_source(document_reference)
        try:
            reserved_reference = self._result_store.result_reference(idempotency_key)
            result = self._pipeline.process(
                source,
                result_reference=reserved_reference,
            )
            stored = self._result_store.save(
                result,
                idempotency_key=idempotency_key,
                document_reference=document_reference,
            )
        except TemplateUnsupportedError as error:
            raise _input_error("Document does not match the M4 closed set") from error
        except TemplateTechnicalError as error:
            raise CamundaTechnicalError("Template processing failed") from error
        except TemplateResultStoreError as error:
            raise CamundaTechnicalError("Template result store is unavailable") from error
        except ValueError as error:
            raise _input_error("Idempotency input is inconsistent") from error
        return _parse_process_variables(stored)

    def _detect_type(self, variables: Mapping[str, ProcessValue]) -> ProcessVariables:
        declared_type = _required_reference(variables, "declaredDocumentType")
        stored = self._load_result(_required_reference(variables, "resultReference"))
        detected_type = _workflow_document_type(
            _payload_string(stored.payload, "documentType")
        )
        if detected_type not in M4_CLOSED_SET_WORKFLOW_DOCUMENT_TYPES:
            raise _input_error("Detected document type is outside the M4 closed set")
        detection = _payload_mapping(stored.payload, "detection")
        confidence = _payload_confidence(detection, "detectionConfidence")
        return {
            "resultReference": stored.reference,
            "detectedDocumentType": detected_type,
            "workflowDocumentType": detected_type,
            "classificationStatus": (
                "CONFIRMED" if declared_type == detected_type else "MISMATCH"
            ),
            "classificationConfidence": confidence,
        }

    def _extract(self, variables: Mapping[str, ProcessValue]) -> ProcessVariables:
        workflow_type = _required_reference(variables, "workflowDocumentType")
        stored = self._load_result(_required_reference(variables, "resultReference"))
        detected_type = _workflow_document_type(
            _payload_string(stored.payload, "documentType")
        )
        if workflow_type != detected_type:
            raise _input_error("Confirmed document type does not match the stored result")
        processing = _payload_mapping(stored.payload, "processing")
        result: ProcessVariables = {
            "resultReference": stored.reference,
            "documentType": detected_type,
            "templateId": _payload_string(stored.payload, "templateId"),
            "templateVersion": _payload_string(stored.payload, "templateVersion"),
            "extractionStatus": "SUCCESS",
            "extractedDataReference": stored.reference,
            "parserName": _payload_string(processing, "parserName"),
            "parserVersion": _payload_string(processing, "parserVersion"),
        }
        ocr_engine = processing.get("ocrEngine")
        if isinstance(ocr_engine, str) and ocr_engine:
            result["ocrEngine"] = ocr_engine
        return result

    def _normalize_validate(
        self,
        variables: Mapping[str, ProcessValue],
    ) -> ProcessVariables:
        stored = self._load_result(_required_reference(variables, "resultReference"))
        return {
            **_stored_quality_projection(stored.payload),
            **_review_context_projection(stored),
        }

    def _apply_corrections(
        self,
        variables: Mapping[str, ProcessValue],
    ) -> ProcessVariables:
        corrections_reference = _required_reference(
            variables, "correctionsReference"
        )
        result_reference = _required_reference(variables, "resultReference")
        current_hash = _required_sha256(variables, "resultPayloadHash")
        current_case_version = _required_positive_int(variables, "caseVersion")
        stored = self._load_result(result_reference)
        if stored.payload_hash != current_hash:
            raise _correction_error("Correction is based on a stale result payload")
        try:
            correction = self._correction_store.load(corrections_reference)
        except ReviewArtifactStoreError as error:
            raise _correction_error("Correction reference is invalid") from error
        if (
            correction.result_reference != result_reference
            or correction.expected_payload_hash != current_hash
        ):
            raise _correction_error("Correction does not match the reviewed result")
        try:
            corrected_result = self._pipeline.apply_corrections(
                stored.payload,
                correction.changes,
            )
            corrected = self._result_store.apply_correction(
                result_reference=result_reference,
                correction_reference=corrections_reference,
                expected_payload_hash=current_hash,
                corrected_result=corrected_result,
                next_case_version=current_case_version + 1,
            )
        except TemplateUnsupportedError as error:
            raise _correction_error("Correction payload is invalid") from error
        except ValueError as error:
            raise _correction_error("Correction is stale or inconsistent") from error
        except (TemplateTechnicalError, TemplateResultStoreError) as error:
            raise CamundaTechnicalError("Correction processing failed") from error
        return {
            "resultReference": corrected.reference,
            "resultPayloadHash": corrected.payload_hash,
            "caseVersion": current_case_version + 1,
        }

    def _load_source(self, document_reference: str) -> DocumentSource:
        try:
            return self._source_store.load(document_reference)
        except DocumentReferenceError as error:
            raise _input_error("Document reference is invalid") from error
        except DocumentSourceStoreError as error:
            raise CamundaTechnicalError("Private document source is unavailable") from error

    def _load_result(self, result_reference: str) -> StoredTemplateResult:
        try:
            return self._result_store.load(result_reference)
        except TemplateResultStoreError as error:
            raise CamundaTechnicalError("Template result store is unavailable") from error


def build_m4_worker(
    *,
    client: CamundaExternalTaskClient,
    pipeline: TemplatePipeline,
    source_store: DocumentSourceStore,
    result_store: TemplateResultStore,
) -> Camunda7ExternalTaskWorker:
    operations = M4TemplateStageOperations(
        pipeline,
        source_store,
        result_store,
    )
    handlers = build_m4_shadow_handlers(
        operations.as_mapping(),
        operations.review_audit_operation,
    )
    return Camunda7ExternalTaskWorker(
        client,
        handlers,
        lock_extension_policy=M4_LONG_RUNNING_LOCK_POLICY,
    )


def build_m4_worker_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    client_factory: Callable[[Camunda7RestConfig], CamundaExternalTaskClient] | None = None,
    pipeline: TemplatePipeline | None = None,
) -> Camunda7ExternalTaskWorker:
    values = os.environ if environment is None else environment
    config = M4CamundaRuntimeConfig.from_environment(values)
    create_client = client_factory or Camunda7ExternalTaskClient.from_config
    selected_pipeline = pipeline or build_local_template_processing_service(
        device=values.get("HCNS_TEMPLATE_OCR_DEVICE", "cpu"),
        ocr_backend=values.get("HCNS_TEMPLATE_OCR_BACKEND") or None,
    )
    return build_m4_worker(
        client=create_client(config.rest),
        pipeline=selected_pipeline,
        source_store=LocalSessionDocumentSourceStore(config.private_root),
        result_store=JsonFileTemplateResultStore(config.private_root / "camunda_m4"),
    )


def _parse_process_variables(stored: StoredTemplateResult) -> ProcessVariables:
    processing = _payload_mapping(stored.payload, "processing")
    return {
        "resultReference": stored.reference,
        "resultPayloadHash": stored.payload_hash,
        "parseStatus": "SUCCESS",
        "sourceFormat": _payload_string(processing, "sourceFormat"),
    }


def _review_context_projection(stored: StoredTemplateResult) -> ProcessVariables:
    quality = _payload_mapping(stored.payload, "quality")
    dmn_projection = _payload_mapping(
        stored.payload,
        _PRIVATE_DMN_PROJECTION_KEY,
    )
    missing_fields = quality.get("missingFields")
    validation_errors = quality.get("validationErrors")
    recommended_action = quality.get("recommendedAction")
    if (
        not isinstance(missing_fields, list)
        or any(not isinstance(item, str) for item in missing_fields)
        or not isinstance(validation_errors, list)
        or any(not isinstance(item, str) for item in validation_errors)
        or not isinstance(recommended_action, str)
    ):
        raise CamundaTechnicalError("Stored review context is inconsistent")
    missing = cast(list[str], missing_fields)
    errors = cast(list[str], validation_errors)
    reason_codes = list(
        dict.fromkeys(
            [
                *(
                    (f"MISSING:{name}" for name in missing)
                    if dmn_projection.get("missingCriticalField") is True
                    else ()
                ),
                *(error.partition(":")[0] for error in errors),
            ]
        )
    )
    if not reason_codes and not M4_SHADOW_POLICY.auto_continue_enabled:
        reason_codes.append("SHADOW_REVIEW_REQUIRED")
    return {
        "resultPayloadHash": stored.payload_hash,
        "missingFields": ",".join(missing),
        "validationErrors": ",".join(errors),
        "recommendedAction": recommended_action,
        "reviewReasonCodes": ",".join(reason_codes),
    }


def _build_template_quality_projection(
    result: TemplateProcessingResult,
) -> ProcessVariables:
    template_id = result.detection.definition.template_id
    sensitive_fields = _SENSITIVE_FIELDS_BY_TEMPLATE.get(template_id)
    if sensitive_fields is None:
        raise TemplateResultStoreError("Template quality policy is not configured")
    uses_ocr = result.processing.get("usesOcr")
    if type(uses_ocr) is not bool:
        raise TemplateResultStoreError("Template processing metadata is inconsistent")

    missing_fields = set(result.validation.missing_fields)
    required_fields = set(result.detection.definition.required_fields)
    critical_fields = _ROUTING_CRITICAL_FIELDS_BY_TEMPLATE.get(
        template_id, frozenset(required_fields)
    )
    missing_required = bool(missing_fields & critical_fields)
    validation_errors = set(result.validation.validation_errors)
    validation_codes = {
        error.partition(":")[0]
        for error in validation_errors
    }
    sensitive_conflict = any(
        error.startswith("MULTIPLE_CANDIDATES:")
        and error.partition(":")[2] in sensitive_fields
        for error in validation_errors
    )
    sensitive_ocr_value = bool(uses_ocr) and any(
        result.data.get(field_name) not in {None, ""}
        for field_name in sensitive_fields
    )
    review_required = (
        result.validation.recommended_action is not RecommendedAction.AUTO_CONTINUE
        or bool(uses_ocr)
    )
    variables: ProcessVariables = {
        "qualityStatus": "REVIEW_REQUIRED" if review_required else "PASS",
        "reviewRequired": review_required,
        "sensitiveFieldNeedsReview": sensitive_conflict or sensitive_ocr_value,
        "missingCriticalField": missing_required,
        "businessInconsistency": bool(
            validation_codes - _REVIEW_ONLY_VALIDATION_CODES
        ),
        "requiredFieldsComplete": not missing_required,
        "overallConfidence": result.validation.confidence,
        "autoContinueEnabled": M4_SHADOW_POLICY.auto_continue_enabled,
    }
    validate_dmn_quality_variables(variables)
    return variables


def _workflow_document_type(document_type: str) -> str:
    try:
        return map_document_type(DocumentType(document_type)).value
    except ValueError:
        return document_type


def _stored_quality_projection(payload: Mapping[str, object]) -> ProcessVariables:
    stored = _payload_mapping(payload, _PRIVATE_DMN_PROJECTION_KEY)
    variables: ProcessVariables = {}
    for name in DMN_QUALITY_INPUT_VARIABLES:
        value = stored.get(name)
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise CamundaTechnicalError("Stored DMN quality projection is inconsistent")
        variables[name] = value
    try:
        validate_dmn_quality_variables(variables)
    except (TypeError, ValueError) as error:
        raise CamundaTechnicalError(
            "Stored DMN quality projection is inconsistent"
        ) from error
    return variables


def _required_reference(
    variables: Mapping[str, ProcessValue],
    name: str,
) -> str:
    value = variables.get(name)
    if not isinstance(value, str) or not value.strip():
        raise _input_error("Required document task reference is invalid")
    return value.strip()


def _required_sha256(
    variables: Mapping[str, ProcessValue],
    name: str,
) -> str:
    value = variables.get(name)
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise _input_error("Required payload hash is invalid")
    return value


def _required_positive_int(
    variables: Mapping[str, ProcessValue],
    name: str,
) -> int:
    value = variables.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _input_error("Required case version is invalid")
    return value


def _required_iso_timestamp(
    variables: Mapping[str, ProcessValue],
    name: str,
) -> str:
    value = _required_reference(variables, name)
    normalized = re.sub(
        r"(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$)",
        r"\1",
        value.replace("Z", "+00:00"),
    )
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise _input_error("Review timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise _input_error("Review timestamp must include a timezone")
    return value


def _payload_mapping(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise CamundaTechnicalError("Stored Template-first result is inconsistent")
    return cast(Mapping[str, object], value)


def _payload_string(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise CamundaTechnicalError("Stored Template-first result is inconsistent")
    return value


def _payload_confidence(payload: Mapping[str, object], name: str) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CamundaTechnicalError("Stored Template-first result is inconsistent")
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise CamundaTechnicalError("Stored Template-first result is inconsistent")
    return confidence


def _input_error(public_message: str) -> CamundaBusinessError:
    return CamundaBusinessError(
        "DOCUMENT_INPUT_INVALID",
        public_message,
        variables={"errorCode": "DOCUMENT_INPUT_INVALID"},
    )


def _correction_error(public_message: str) -> CamundaBusinessError:
    return CamundaBusinessError(
        "CORRECTION_INVALID",
        public_message,
        variables={"errorCode": "CORRECTION_INVALID"},
    )


def _idempotency_digest(idempotency_key: str) -> str:
    if not idempotency_key.strip():
        raise ValueError("Idempotency key must not be empty")
    return sha256(idempotency_key.encode("utf-8")).hexdigest()


def _document_reference_digest(document_reference: str) -> str:
    if not document_reference.strip():
        raise ValueError("Document reference must not be empty")
    return sha256(document_reference.encode("utf-8")).hexdigest()


def _json_payload_digest(payload: Mapping[str, object]) -> str:
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(content).hexdigest()


def _atomic_write_json(path: Path, payload: object) -> None:
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=".write-",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
