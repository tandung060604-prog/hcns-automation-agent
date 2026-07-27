"""Run one backend over an immutable, authorized benchmark corpus."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from hcns_agent.application.benchmark import (
    BenchmarkInputError,
    compute_dataset_digest,
    prediction_case_from_idp_result,
    validate_authorized_manifest,
)
from hcns_agent.domain.documents import DocumentType
from hcns_agent.domain.errors import DocumentIntakeError
from hcns_agent.domain.evaluation import (
    BenchmarkSubmission,
    DatasetManifest,
    GroundTruthCase,
    PredictionCase,
)
from hcns_agent.domain.understanding import QualityStatus
from hcns_agent.ports.benchmark import BenchmarkBackend, SourcePageCounter
from hcns_agent.ports.document_parser import DocumentSource


@dataclass(frozen=True, slots=True)
class BenchmarkRunPolicy:
    minimum_pages: int = 30
    maximum_pages: int = 50
    require_outside_git: bool = True

    def __post_init__(self) -> None:
        if self.minimum_pages <= 0:
            raise ValueError("minimum_pages must be positive")
        if self.maximum_pages < self.minimum_pages:
            raise ValueError("maximum_pages must not be smaller than minimum_pages")


class BenchmarkRunner:
    """Verify all corpus identities before invoking a local benchmark backend."""

    def __init__(
        self,
        page_counter: SourcePageCounter,
        *,
        policy: BenchmarkRunPolicy | None = None,
    ) -> None:
        self._page_counter = page_counter
        self._policy = policy or BenchmarkRunPolicy()

    def run(
        self,
        manifest: DatasetManifest,
        ground_truth: tuple[GroundTruthCase, ...],
        backend: BenchmarkBackend,
        *,
        private_root: Path,
        output_directory: Path,
    ) -> BenchmarkSubmission:
        validate_authorized_manifest(manifest)
        self._validate_contract(manifest, ground_truth)
        root = private_root.resolve(strict=True)
        if self._policy.require_outside_git and any(
            (candidate / ".git").exists() for candidate in (root, *root.parents)
        ):
            raise BenchmarkInputError("private_root must be outside every Git repository")
        work_root = output_directory.resolve()
        if not work_root.is_relative_to(root):
            raise BenchmarkInputError("Benchmark output_directory must be inside private_root")
        work_root.mkdir(parents=True, exist_ok=True)

        verified_sources = tuple(
            self._load_verified_source(root, case) for case in sorted(
                ground_truth,
                key=lambda item: item.case_id,
            )
        )
        predictions: list[PredictionCase] = []
        for case, source_path, source in verified_sources:
            case_output = work_root / case.case_id
            case_output.mkdir(parents=True, exist_ok=True)
            started = time.perf_counter()
            try:
                result = backend.process(
                    source,
                    source_path=source_path,
                    output_directory=case_output,
                )
                latency_ms = (time.perf_counter() - started) * 1000.0
                predictions.append(
                    prediction_case_from_idp_result(result, latency_ms=latency_ms)
                )
            except Exception as error:
                latency_ms = (time.perf_counter() - started) * 1000.0
                predictions.append(
                    PredictionCase(
                        case_id=case.case_id,
                        document_type=DocumentType.UNKNOWN,
                        fields=(),
                        quality_status=QualityStatus.REJECTED,
                        review_required=True,
                        latency_ms=latency_ms,
                        failure_code=_safe_failure_code(error),
                    )
                )

        return BenchmarkSubmission(
            dataset_id=manifest.dataset_id,
            dataset_version=manifest.version,
            backend_name=backend.name,
            backend_version=backend.version,
            model_identifiers=backend.model_identifiers,
            cases=tuple(predictions),
        )

    def _validate_contract(
        self,
        manifest: DatasetManifest,
        ground_truth: tuple[GroundTruthCase, ...],
    ) -> None:
        if not self._policy.minimum_pages <= manifest.page_count <= self._policy.maximum_pages:
            raise BenchmarkInputError(
                "Authorized benchmark must contain between "
                f"{self._policy.minimum_pages} and {self._policy.maximum_pages} pages"
            )
        if manifest.document_count != len(ground_truth):
            raise BenchmarkInputError("manifest document_count does not match Ground Truth")
        if manifest.page_count != sum(case.page_count for case in ground_truth):
            raise BenchmarkInputError("manifest page_count does not match Ground Truth")
        case_ids = [case.case_id for case in ground_truth]
        if len(case_ids) != len(set(case_ids)):
            raise BenchmarkInputError("Ground Truth case IDs must be unique")
        expected_digest = compute_dataset_digest(
            manifest.dataset_id,
            manifest.version,
            ground_truth,
        )
        if manifest.content_digest != expected_digest:
            raise BenchmarkInputError("manifest content_digest does not match Ground Truth")

    def _load_verified_source(
        self,
        root: Path,
        case: GroundTruthCase,
    ) -> tuple[GroundTruthCase, Path, DocumentSource]:
        source_path = (root / Path(case.source_relative_path)).resolve(strict=True)
        if not source_path.is_relative_to(root) or not source_path.is_file():
            raise BenchmarkInputError("Ground Truth source path escapes private_root")
        content = source_path.read_bytes()
        actual_digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if actual_digest != case.source_sha256:
            raise BenchmarkInputError(
                f"Source digest mismatch for benchmark case {case.case_id}"
            )
        source = DocumentSource(
            document_id=case.case_id,
            filename=source_path.name,
            content=content,
            source_reference=f"benchmark://{case.case_id}",
        )
        actual_pages = self._page_counter.count_pages(source)
        if actual_pages != case.page_count:
            raise BenchmarkInputError(
                f"Page count mismatch for benchmark case {case.case_id}"
            )
        return case, source_path, source


def _safe_failure_code(error: Exception) -> str:
    if isinstance(error, DocumentIntakeError):
        return f"INTAKE_{error.code.value}"
    if isinstance(error, TimeoutError):
        return "BACKEND_TIMEOUT"
    return f"BACKEND_{type(error).__name__.upper()}"
