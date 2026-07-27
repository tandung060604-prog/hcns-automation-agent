"""Privacy-preserving benchmark and promotion models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import PurePosixPath
from re import fullmatch

from hcns_agent.domain.canonical import ScalarValue
from hcns_agent.domain.documents import DocumentType
from hcns_agent.domain.models import FieldStatus
from hcns_agent.domain.understanding import QualityStatus


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class DatasetAuthorizationStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REVOKED = "REVOKED"


class StorageProtection(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    ENCRYPTED_VOLUME = "ENCRYPTED_VOLUME"
    EFS = "EFS"
    ENTERPRISE_MANAGED = "ENTERPRISE_MANAGED"


class PromotionStatus(str, Enum):
    PROMOTE = "PROMOTE"
    HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_id: str
    version: str
    content_digest: str
    purpose: str
    rights_basis: str
    data_owner: str
    approved_by: str
    approval_reference: str
    approved_at: date
    retention_until: date
    authorization_status: DatasetAuthorizationStatus
    storage_protection: StorageProtection
    data_classification: DataClassification
    document_count: int
    page_count: int

    def __post_init__(self) -> None:
        for value, name in (
            (self.dataset_id, "dataset_id"),
            (self.version, "version"),
            (self.content_digest, "content_digest"),
            (self.purpose, "purpose"),
            (self.rights_basis, "rights_basis"),
            (self.data_owner, "data_owner"),
            (self.approved_by, "approved_by"),
            (self.approval_reference, "approval_reference"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.document_count <= 0 or self.page_count <= 0:
            raise ValueError("document_count and page_count must be positive")
        if self.retention_until < self.approved_at:
            raise ValueError("retention_until must not be earlier than approved_at")
        if fullmatch(r"sha256:[a-f0-9]{64}", self.content_digest) is None:
            raise ValueError("content_digest must be a lowercase sha256 digest")
        if (
            self.authorization_status is DatasetAuthorizationStatus.APPROVED
            and self.storage_protection is StorageProtection.UNVERIFIED
        ):
            raise ValueError("Approved datasets require verified encrypted storage")


@dataclass(frozen=True, slots=True)
class ExpectedField:
    name: str
    value: ScalarValue
    sensitive: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Expected field name must not be empty")


@dataclass(frozen=True, slots=True)
class GroundTruthCase:
    case_id: str
    source_relative_path: str
    source_sha256: str
    page_count: int
    document_type: DocumentType
    fields: tuple[ExpectedField, ...]
    expected_quality_status: QualityStatus
    review_required: bool
    ocr_lines: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")
        source_path = PurePosixPath(self.source_relative_path)
        if (
            not self.source_relative_path.strip()
            or source_path.is_absolute()
            or ".." in source_path.parts
            or "\\" in self.source_relative_path
        ):
            raise ValueError("source_relative_path must be a safe POSIX relative path")
        if fullmatch(r"sha256:[a-f0-9]{64}", self.source_sha256) is None:
            raise ValueError("source_sha256 must be a lowercase sha256 digest")
        if self.page_count <= 0:
            raise ValueError("Ground truth page_count must be positive")
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("Ground truth field names must be unique within a case")
        if self.expected_quality_status is QualityStatus.PASS and self.review_required:
            raise ValueError("PASS ground truth cannot require review")
        if any(not line.strip() for line in self.ocr_lines):
            raise ValueError("Ground truth OCR lines must not be blank")


@dataclass(frozen=True, slots=True)
class PredictedField:
    name: str
    value: ScalarValue
    status: FieldStatus
    sensitive: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Predicted field name must not be empty")


@dataclass(frozen=True, slots=True)
class PredictionCase:
    case_id: str
    document_type: DocumentType
    fields: tuple[PredictedField, ...]
    quality_status: QualityStatus
    review_required: bool
    latency_ms: float
    failure_code: str | None = None
    ocr_lines: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        if self.quality_status is QualityStatus.PASS and self.review_required:
            raise ValueError("PASS prediction cannot require review")
        if self.failure_code is not None and not self.failure_code.strip():
            raise ValueError("failure_code must be None or non-empty")
        if any(not line.strip() for line in self.ocr_lines):
            raise ValueError("Prediction OCR lines must not be blank")


@dataclass(frozen=True, slots=True)
class BenchmarkSubmission:
    dataset_id: str
    dataset_version: str
    backend_name: str
    backend_version: str
    model_identifiers: tuple[str, ...]
    cases: tuple[PredictionCase, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.dataset_id, "dataset_id"),
            (self.dataset_version, "dataset_version"),
            (self.backend_name, "backend_name"),
            (self.backend_version, "backend_version"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not self.cases:
            raise ValueError("Benchmark submission must contain at least one case")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Prediction case IDs must be unique")


@dataclass(frozen=True, slots=True)
class ClassificationTypeMetrics:
    document_type: DocumentType
    support: int
    predicted: int
    true_positive: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True, slots=True)
class ClassificationMetrics:
    per_type: tuple[ClassificationTypeMetrics, ...]
    macro_precision: float
    macro_recall: float
    macro_f1: float
    unknown_rate: float


@dataclass(frozen=True, slots=True)
class OcrMetrics:
    evaluated_cases: int
    reference_character_count: int
    character_error_count: int
    character_error_rate: float
    reference_word_count: int
    word_error_count: int
    word_error_rate: float
    reading_order_exact_count: int
    reading_order_accuracy: float


@dataclass(frozen=True, slots=True)
class FieldMetrics:
    document_type: DocumentType
    field_name: str
    expected_count: int
    predicted_count: int
    exact_match_count: int
    not_found_count: int
    exact_match_rate: float
    precision: float
    recall: float


@dataclass(frozen=True, slots=True)
class ExtractionMetrics:
    per_field: tuple[FieldMetrics, ...]
    expected_count: int
    predicted_count: int
    exact_match_count: int
    not_found_count: int
    exact_match_rate: float
    precision: float
    recall: float
    not_found_rate: float


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    total_cases: int
    false_pass_count: int
    false_pass_rate: float
    false_reject_count: int
    false_reject_rate: float
    review_required_count: int
    review_rate: float
    review_precision: float
    sensitive_field_count: int
    sensitive_false_acceptance_count: int
    sensitive_false_acceptance_rate: float


@dataclass(frozen=True, slots=True)
class SystemMetrics:
    latency_p50_ms: float
    latency_p95_ms: float
    failure_count: int
    failure_rate: float


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    dataset_id: str
    dataset_version: str
    dataset_content_digest: str
    backend_name: str
    backend_version: str
    model_identifiers: tuple[str, ...]
    case_count: int
    classification: ClassificationMetrics
    ocr: OcrMetrics
    extraction: ExtractionMetrics
    quality: QualityMetrics
    system: SystemMetrics


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    contract_tests_passed: bool
    privacy_approved: bool
    license_approved: bool
    model_provenance_approved: bool


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    minimum_field_exact_match_improvement: float = 0.01
    maximum_latency_p95_ms: float = 5_000.0
    maximum_review_rate_increase: float = 0.02
    maximum_failure_rate: float = 0.01
    minimum_benchmark_pages: int = 30
    minimum_ocr_cases: int = 1

    def __post_init__(self) -> None:
        if self.minimum_field_exact_match_improvement < 0:
            raise ValueError("minimum_field_exact_match_improvement must not be negative")
        if self.maximum_latency_p95_ms <= 0:
            raise ValueError("maximum_latency_p95_ms must be positive")
        for value, name in (
            (self.maximum_review_rate_increase, "maximum_review_rate_increase"),
            (self.maximum_failure_rate, "maximum_failure_rate"),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.minimum_benchmark_pages <= 0:
            raise ValueError("minimum_benchmark_pages must be positive")
        if self.minimum_ocr_cases < 0:
            raise ValueError("minimum_ocr_cases must not be negative")


@dataclass(frozen=True, slots=True)
class PromotionCheck:
    code: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    status: PromotionStatus
    checks: tuple[PromotionCheck, ...]
