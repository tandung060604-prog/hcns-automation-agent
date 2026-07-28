"""Models for privacy-preserving Vietnamese line-recognition evaluation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from re import fullmatch


@dataclass(frozen=True, slots=True)
class RecognitionGroundTruthCase:
    case_id: str
    text: str

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")
        if not self.text.strip():
            raise ValueError("Ground Truth text must not be empty")


@dataclass(frozen=True, slots=True)
class RecognitionGroundTruth:
    dataset_id: str
    dataset_version: str
    content_digest: str
    authorized_for_local_evaluation: bool
    cases: tuple[RecognitionGroundTruthCase, ...]

    def __post_init__(self) -> None:
        _validate_dataset_identity(
            self.dataset_id,
            self.dataset_version,
            self.content_digest,
        )
        if not self.authorized_for_local_evaluation:
            raise ValueError("Recognition dataset is not authorized for local evaluation")
        _validate_unique_case_ids(case.case_id for case in self.cases)


@dataclass(frozen=True, slots=True)
class RecognitionPredictionCase:
    case_id: str
    text: str
    confidence: float
    duration_ms: float

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must not be negative")


@dataclass(frozen=True, slots=True)
class RecognitionSubmission:
    dataset_id: str
    dataset_version: str
    backend_name: str
    backend_version: str
    model_identifier: str
    cases: tuple[RecognitionPredictionCase, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.dataset_id, "dataset_id"),
            (self.dataset_version, "dataset_version"),
            (self.backend_name, "backend_name"),
            (self.backend_version, "backend_version"),
            (self.model_identifier, "model_identifier"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        _validate_unique_case_ids(case.case_id for case in self.cases)


@dataclass(frozen=True, slots=True)
class RecognitionMetrics:
    case_count: int
    exact_match_count: int
    exact_match_rate: float
    reference_character_count: int
    character_error_count: int
    character_error_rate: float
    reference_word_count: int
    word_error_count: int
    word_error_rate: float
    reference_diacritic_count: int
    diacritic_error_count: int
    diacritic_error_rate: float
    prediction_nfc_violation_count: int
    accepted_count: int
    accepted_exact_count: int
    accepted_precision: float
    confidence_threshold: float
    latency_p50_ms: float
    latency_p95_ms: float


@dataclass(frozen=True, slots=True)
class RecognitionReport:
    dataset_id: str
    dataset_version: str
    dataset_content_digest: str
    backend_name: str
    backend_version: str
    model_identifier: str
    metrics: RecognitionMetrics


@dataclass(frozen=True, slots=True)
class CharsetAuditReport:
    model_identifier: str
    required_character_count: int
    present_character_count: int
    missing_character_count: int
    coverage: float
    missing_characters: tuple[str, ...]


def _validate_dataset_identity(
    dataset_id: str,
    dataset_version: str,
    content_digest: str,
) -> None:
    if not dataset_id.strip() or not dataset_version.strip():
        raise ValueError("dataset_id and dataset_version must not be empty")
    if fullmatch(r"sha256:[a-f0-9]{64}", content_digest) is None:
        raise ValueError("content_digest must be a lowercase sha256 digest")


def _validate_unique_case_ids(case_ids: Iterable[str]) -> None:
    values = tuple(case_ids)
    if not values:
        raise ValueError("Recognition cases must not be empty")
    if len(values) != len(set(values)):
        raise ValueError("Recognition case IDs must be unique")
