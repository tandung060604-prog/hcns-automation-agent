"""Aggregate-only benchmark metrics and promotion gates."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from hcns_agent.domain.content import iter_text_observations
from hcns_agent.domain.documents import DocumentType
from hcns_agent.domain.evaluation import (
    BenchmarkReport,
    BenchmarkSubmission,
    ClassificationMetrics,
    ClassificationTypeMetrics,
    DatasetAuthorizationStatus,
    DatasetManifest,
    ExtractionMetrics,
    FieldMetrics,
    GroundTruthCase,
    OcrMetrics,
    PredictedField,
    PredictionCase,
    PromotionCheck,
    PromotionDecision,
    PromotionEvidence,
    PromotionPolicy,
    PromotionStatus,
    QualityMetrics,
    SystemMetrics,
)
from hcns_agent.domain.models import FieldStatus
from hcns_agent.domain.understanding import IdpResult, QualityStatus


class BenchmarkInputError(ValueError):
    """Raised when benchmark inputs cannot be compared safely."""


def compute_dataset_digest(
    dataset_id: str,
    dataset_version: str,
    ground_truth: tuple[GroundTruthCase, ...],
) -> str:
    """Hash source identities and labels without exposing their values in reports."""
    payload = {
        "datasetId": dataset_id,
        "datasetVersion": dataset_version,
        "cases": [
            {
                "caseId": case.case_id,
                "sourceRelativePath": case.source_relative_path,
                "sourceSha256": case.source_sha256,
                "pageCount": case.page_count,
                "documentType": case.document_type.value,
                "fields": [
                    {
                        "name": field.name,
                        "value": field.value,
                        "sensitive": field.sensitive,
                    }
                    for field in sorted(case.fields, key=lambda item: item.name)
                ],
                "expectedQualityStatus": case.expected_quality_status.value,
                "reviewRequired": case.review_required,
                "ocrLines": list(case.ocr_lines),
            }
            for case in sorted(ground_truth, key=lambda item: item.case_id)
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def validate_authorized_manifest(
    manifest: DatasetManifest,
    *,
    as_of: date | None = None,
) -> None:
    evaluation_date = as_of or date.today()
    if manifest.authorization_status is not DatasetAuthorizationStatus.APPROVED:
        raise BenchmarkInputError("Dataset authorization status must be APPROVED")
    if not manifest.approved_at <= evaluation_date <= manifest.retention_until:
        raise BenchmarkInputError("Dataset approval or retention window is not active")


def prediction_case_from_idp_result(
    result: IdpResult,
    *,
    latency_ms: float,
    failure_code: str | None = None,
) -> PredictionCase:
    """Adapt the vendor-neutral M2 result contract into one benchmark prediction."""
    return PredictionCase(
        case_id=result.document_id,
        document_type=result.classification.document_type,
        fields=tuple(
            PredictedField(
                name=field.name,
                value=field.value,
                status=field.status,
                sensitive=field.sensitive,
            )
            for field in result.fields
        ),
        quality_status=result.quality.status,
        review_required=result.quality.review_required,
        latency_ms=latency_ms,
        failure_code=failure_code,
        ocr_lines=tuple(
            observation.text for observation in iter_text_observations(
                result.canonical_document
            )
        ),
    )


class BenchmarkHarness:
    """Evaluate a versioned submission without copying field values into the report."""

    def evaluate(
        self,
        manifest: DatasetManifest,
        ground_truth: tuple[GroundTruthCase, ...],
        submission: BenchmarkSubmission,
) -> BenchmarkReport:
        truth_by_id, prediction_by_id = _validate_inputs(manifest, ground_truth, submission)
        pairs = tuple(
            (truth_by_id[case_id], prediction_by_id[case_id])
            for case_id in sorted(truth_by_id)
        )
        return BenchmarkReport(
            dataset_id=manifest.dataset_id,
            dataset_version=manifest.version,
            dataset_content_digest=manifest.content_digest,
            backend_name=submission.backend_name,
            backend_version=submission.backend_version,
            model_identifiers=submission.model_identifiers,
            case_count=len(pairs),
            classification=_classification_metrics(pairs),
            ocr=_ocr_metrics(pairs),
            extraction=_extraction_metrics(pairs),
            quality=_quality_metrics(pairs),
            system=_system_metrics(prediction_by_id.values()),
        )


class PromotionGate:
    """Compare a challenger with a baseline on one immutable dataset version."""

    def __init__(self, policy: PromotionPolicy | None = None) -> None:
        self._policy = policy or PromotionPolicy()

    def evaluate(
        self,
        manifest: DatasetManifest,
        baseline: BenchmarkReport,
        challenger: BenchmarkReport,
        evidence: PromotionEvidence,
        *,
        as_of: date | None = None,
    ) -> PromotionDecision:
        evaluation_date = as_of or date.today()
        checks = (
            _check_same_dataset(manifest, baseline, challenger),
            PromotionCheck(
                code="DATASET_AUTHORIZATION_ACTIVE",
                passed=(
                    manifest.authorization_status
                    is DatasetAuthorizationStatus.APPROVED
                    and manifest.approved_at
                    <= evaluation_date
                    <= manifest.retention_until
                ),
                message="Dataset approval and retention window must be active",
            ),
            PromotionCheck(
                code="MINIMUM_BENCHMARK_PAGES",
                passed=manifest.page_count >= self._policy.minimum_benchmark_pages,
                message="Dataset must meet the minimum authorized page count",
            ),
            PromotionCheck(
                code="FIELD_EXACT_MATCH_IMPROVEMENT",
                passed=(
                    challenger.extraction.exact_match_rate
                    - baseline.extraction.exact_match_rate
                    >= self._policy.minimum_field_exact_match_improvement
                ),
                message="Challenger must improve aggregate field exact match",
            ),
            PromotionCheck(
                code="MINIMUM_OCR_CASES",
                passed=challenger.ocr.evaluated_cases >= self._policy.minimum_ocr_cases,
                message="Benchmark must contain enough OCR Ground Truth cases",
            ),
            PromotionCheck(
                code="OCR_CER_NON_REGRESSION",
                passed=(
                    challenger.ocr.character_error_rate
                    <= baseline.ocr.character_error_rate
                ),
                message="Challenger character error rate must not regress",
            ),
            PromotionCheck(
                code="OCR_WER_NON_REGRESSION",
                passed=challenger.ocr.word_error_rate <= baseline.ocr.word_error_rate,
                message="Challenger word error rate must not regress",
            ),
            PromotionCheck(
                code="READING_ORDER_NON_REGRESSION",
                passed=(
                    challenger.ocr.reading_order_accuracy
                    >= baseline.ocr.reading_order_accuracy
                ),
                message="Challenger reading-order accuracy must not regress",
            ),
            PromotionCheck(
                code="NO_SENSITIVE_FALSE_ACCEPTANCE_INCREASE",
                passed=(
                    challenger.quality.sensitive_false_acceptance_count
                    <= baseline.quality.sensitive_false_acceptance_count
                ),
                message="Challenger must not increase sensitive-field false acceptance",
            ),
            PromotionCheck(
                code="NO_FALSE_PASS_INCREASE",
                passed=challenger.quality.false_pass_rate <= baseline.quality.false_pass_rate,
                message="Challenger must not increase false PASS rate",
            ),
            PromotionCheck(
                code="LATENCY_SLO",
                passed=challenger.system.latency_p95_ms <= self._policy.maximum_latency_p95_ms,
                message="Challenger p95 latency must stay within the configured SLO",
            ),
            PromotionCheck(
                code="REVIEW_EFFORT",
                passed=(
                    challenger.quality.review_rate
                    <= baseline.quality.review_rate + self._policy.maximum_review_rate_increase
                ),
                message="Challenger must not materially increase review workload",
            ),
            PromotionCheck(
                code="FAILURE_RATE",
                passed=challenger.system.failure_rate <= self._policy.maximum_failure_rate,
                message="Challenger failure rate must stay within policy",
            ),
            PromotionCheck(
                code="CONTRACT_REGRESSION",
                passed=evidence.contract_tests_passed,
                message="Contract and regression tests must pass",
            ),
            PromotionCheck(
                code="PRIVACY_APPROVAL",
                passed=evidence.privacy_approved,
                message="Dataset and backend privacy review must be approved",
            ),
            PromotionCheck(
                code="LICENSE_APPROVAL",
                passed=evidence.license_approved,
                message="Backend and model licenses must be approved",
            ),
            PromotionCheck(
                code="MODEL_PROVENANCE_APPROVAL",
                passed=evidence.model_provenance_approved,
                message="Model identifiers and provenance must be approved",
            ),
        )
        status = (
            PromotionStatus.PROMOTE
            if all(check.passed for check in checks)
            else PromotionStatus.HOLD
        )
        return PromotionDecision(status=status, checks=checks)


def _validate_inputs(
    manifest: DatasetManifest,
    ground_truth: tuple[GroundTruthCase, ...],
    submission: BenchmarkSubmission,
) -> tuple[dict[str, GroundTruthCase], dict[str, PredictionCase]]:
    if not ground_truth:
        raise BenchmarkInputError("Ground truth must contain at least one case")
    if submission.dataset_id != manifest.dataset_id:
        raise BenchmarkInputError("Submission dataset_id does not match the manifest")
    if submission.dataset_version != manifest.version:
        raise BenchmarkInputError("Submission dataset_version does not match the manifest")
    truth_by_id = {case.case_id: case for case in ground_truth}
    if len(truth_by_id) != len(ground_truth):
        raise BenchmarkInputError("Ground truth case IDs must be unique")
    prediction_by_id = {case.case_id: case for case in submission.cases}
    if set(truth_by_id) != set(prediction_by_id):
        raise BenchmarkInputError("Ground truth and prediction case IDs must match exactly")
    if manifest.document_count != len(ground_truth):
        raise BenchmarkInputError("Manifest document_count does not match ground truth")
    if manifest.page_count != sum(case.page_count for case in ground_truth):
        raise BenchmarkInputError("Manifest page_count does not match ground truth")
    expected_digest = compute_dataset_digest(
        manifest.dataset_id,
        manifest.version,
        ground_truth,
    )
    if manifest.content_digest != expected_digest:
        raise BenchmarkInputError("Manifest content_digest does not match Ground Truth")
    return truth_by_id, prediction_by_id


def _classification_metrics(
    pairs: tuple[tuple[GroundTruthCase, PredictionCase], ...],
) -> ClassificationMetrics:
    expected_counts: dict[DocumentType, int] = defaultdict(int)
    predicted_counts: dict[DocumentType, int] = defaultdict(int)
    true_positive: dict[DocumentType, int] = defaultdict(int)
    unknown_count = 0
    for truth, prediction in pairs:
        expected_counts[truth.document_type] += 1
        predicted_counts[prediction.document_type] += 1
        if prediction.document_type is truth.document_type:
            true_positive[truth.document_type] += 1
        if prediction.document_type is DocumentType.UNKNOWN:
            unknown_count += 1

    labels = sorted(set(expected_counts) | set(predicted_counts), key=lambda item: item.value)
    per_type = tuple(
        _classification_type_metrics(
            label,
            expected_counts[label],
            predicted_counts[label],
            true_positive[label],
        )
        for label in labels
    )
    evaluated = tuple(metric for metric in per_type if metric.support > 0)
    return ClassificationMetrics(
        per_type=per_type,
        macro_precision=_mean(metric.precision for metric in evaluated),
        macro_recall=_mean(metric.recall for metric in evaluated),
        macro_f1=_mean(metric.f1 for metric in evaluated),
        unknown_rate=_rate(unknown_count, len(pairs)),
    )


def _classification_type_metrics(
    document_type: DocumentType,
    support: int,
    predicted: int,
    true_positive: int,
) -> ClassificationTypeMetrics:
    precision = _rate(true_positive, predicted)
    recall = _rate(true_positive, support)
    return ClassificationTypeMetrics(
        document_type=document_type,
        support=support,
        predicted=predicted,
        true_positive=true_positive,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
    )


def _ocr_metrics(
    pairs: tuple[tuple[GroundTruthCase, PredictionCase], ...],
) -> OcrMetrics:
    evaluated_cases = 0
    reference_character_count = 0
    character_error_count = 0
    reference_word_count = 0
    word_error_count = 0
    reading_order_exact_count = 0
    for truth, prediction in pairs:
        if not truth.ocr_lines:
            continue
        evaluated_cases += 1
        reference_text = "\n".join(truth.ocr_lines)
        prediction_text = "\n".join(prediction.ocr_lines)
        reference_characters = tuple(reference_text)
        predicted_characters = tuple(prediction_text)
        reference_words = tuple(reference_text.split())
        predicted_words = tuple(prediction_text.split())
        reference_character_count += len(reference_characters)
        character_error_count += _edit_distance(
            reference_characters, predicted_characters
        )
        reference_word_count += len(reference_words)
        word_error_count += _edit_distance(reference_words, predicted_words)
        reading_order_exact_count += int(truth.ocr_lines == prediction.ocr_lines)
    return OcrMetrics(
        evaluated_cases=evaluated_cases,
        reference_character_count=reference_character_count,
        character_error_count=character_error_count,
        character_error_rate=_error_rate(
            character_error_count, reference_character_count
        ),
        reference_word_count=reference_word_count,
        word_error_count=word_error_count,
        word_error_rate=_error_rate(word_error_count, reference_word_count),
        reading_order_exact_count=reading_order_exact_count,
        reading_order_accuracy=_rate(reading_order_exact_count, evaluated_cases),
    )


def _extraction_metrics(
    pairs: tuple[tuple[GroundTruthCase, PredictionCase], ...],
) -> ExtractionMetrics:
    counters: dict[tuple[DocumentType, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for truth, prediction in pairs:
        predicted_by_name: dict[str, list[PredictedField]] = defaultdict(list)
        for field in prediction.fields:
            predicted_by_name[field.name].append(field)

        expected_names = {field.name for field in truth.fields}
        for expected in truth.fields:
            candidates = predicted_by_name.get(expected.name, [])
            exact_matches = sum(candidate.value == expected.value for candidate in candidates)
            bucket = counters[(truth.document_type, expected.name)]
            bucket[0] += 1
            bucket[1] += len(candidates)
            bucket[2] += min(1, exact_matches)
            bucket[3] += int(not candidates)

        for field_name, candidates in predicted_by_name.items():
            if field_name not in expected_names:
                counters[(truth.document_type, field_name)][1] += len(candidates)

    per_field = tuple(
        _field_metrics(document_type, field_name, values)
        for (document_type, field_name), values in sorted(
            counters.items(), key=lambda item: (item[0][0].value, item[0][1])
        )
    )
    expected_count = sum(metric.expected_count for metric in per_field)
    predicted_count = sum(metric.predicted_count for metric in per_field)
    exact_match_count = sum(metric.exact_match_count for metric in per_field)
    not_found_count = sum(metric.not_found_count for metric in per_field)
    return ExtractionMetrics(
        per_field=per_field,
        expected_count=expected_count,
        predicted_count=predicted_count,
        exact_match_count=exact_match_count,
        not_found_count=not_found_count,
        exact_match_rate=_rate(exact_match_count, expected_count),
        precision=_rate(exact_match_count, predicted_count),
        recall=_rate(exact_match_count, expected_count),
        not_found_rate=_rate(not_found_count, expected_count),
    )


def _field_metrics(
    document_type: DocumentType,
    field_name: str,
    values: list[int],
) -> FieldMetrics:
    expected_count, predicted_count, exact_match_count, not_found_count = values
    return FieldMetrics(
        document_type=document_type,
        field_name=field_name,
        expected_count=expected_count,
        predicted_count=predicted_count,
        exact_match_count=exact_match_count,
        not_found_count=not_found_count,
        exact_match_rate=_rate(exact_match_count, expected_count),
        precision=_rate(exact_match_count, predicted_count),
        recall=_rate(exact_match_count, expected_count),
    )


def _quality_metrics(
    pairs: tuple[tuple[GroundTruthCase, PredictionCase], ...],
) -> QualityMetrics:
    false_pass = 0
    false_reject = 0
    review_required = 0
    review_true_positive = 0
    sensitive_field_count = 0
    sensitive_false_acceptance = 0
    for truth, prediction in pairs:
        if prediction.quality_status is QualityStatus.PASS and truth.review_required:
            false_pass += 1
        if (
            prediction.quality_status is QualityStatus.REJECTED
            and truth.expected_quality_status is QualityStatus.PASS
        ):
            false_reject += 1
        if prediction.review_required:
            review_required += 1
            review_true_positive += int(truth.review_required)

        sensitive_names = {field.name for field in truth.fields if field.sensitive}
        sensitive_field_count += len(sensitive_names)
        accepted_sensitive_names = {
            field.name
            for field in prediction.fields
            if field.name in sensitive_names and field.status is FieldStatus.ACCEPTED
        }
        sensitive_false_acceptance += len(accepted_sensitive_names)

    total_cases = len(pairs)
    return QualityMetrics(
        total_cases=total_cases,
        false_pass_count=false_pass,
        false_pass_rate=_rate(false_pass, total_cases),
        false_reject_count=false_reject,
        false_reject_rate=_rate(false_reject, total_cases),
        review_required_count=review_required,
        review_rate=_rate(review_required, total_cases),
        review_precision=_rate(review_true_positive, review_required),
        sensitive_field_count=sensitive_field_count,
        sensitive_false_acceptance_count=sensitive_false_acceptance,
        sensitive_false_acceptance_rate=_rate(
            sensitive_false_acceptance, sensitive_field_count
        ),
    )


def _system_metrics(predictions: Iterable[PredictionCase]) -> SystemMetrics:
    cases = tuple(predictions)
    latencies = sorted(case.latency_ms for case in cases)
    failures = sum(case.failure_code is not None for case in cases)
    return SystemMetrics(
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        failure_count=failures,
        failure_rate=_rate(failures, len(cases)),
    )


def _check_same_dataset(
    manifest: DatasetManifest,
    baseline: BenchmarkReport,
    challenger: BenchmarkReport,
) -> PromotionCheck:
    expected = (manifest.dataset_id, manifest.version, manifest.content_digest)
    baseline_identity = (
        baseline.dataset_id,
        baseline.dataset_version,
        baseline.dataset_content_digest,
    )
    challenger_identity = (
        challenger.dataset_id,
        challenger.dataset_version,
        challenger.dataset_content_digest,
    )
    passed = (
        baseline_identity == expected
        and challenger_identity == expected
        and baseline.case_count == challenger.case_count == manifest.document_count
    )
    return PromotionCheck(
        code="SAME_IMMUTABLE_DATASET",
        passed=passed,
        message="Baseline and challenger must use the same complete dataset version",
    )


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _error_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _mean(values: Iterable[float]) -> float:
    collected = tuple(values)
    if not collected:
        return 0.0
    return round(sum(collected) / len(collected), 6)


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 6)


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    rank = max(0, math.ceil(quantile * len(values)) - 1)
    return round(values[rank], 3)


def _edit_distance(reference: tuple[str, ...], prediction: tuple[str, ...]) -> int:
    previous = list(range(len(prediction) + 1))
    for reference_index, reference_item in enumerate(reference, start=1):
        current = [reference_index]
        for prediction_index, prediction_item in enumerate(prediction, start=1):
            substitution_cost = int(reference_item != prediction_item)
            current.append(
                min(
                    current[-1] + 1,
                    previous[prediction_index] + 1,
                    previous[prediction_index - 1] + substitution_cost,
                )
            )
        previous = current
    return previous[-1]
