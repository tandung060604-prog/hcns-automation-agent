"""Recognition-only metrics for Vietnamese OCR challengers."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

from hcns_agent.application import ocr_metrics
from hcns_agent.domain.recognition import (
    CharsetAuditReport,
    RecognitionGroundTruth,
    RecognitionMetrics,
    RecognitionReport,
    RecognitionSubmission,
)


class RecognitionBenchmarkError(ValueError):
    """Raised when Ground Truth and prediction contracts do not match."""


class VietnameseRecognitionBenchmark:
    def evaluate(
        self,
        ground_truth: RecognitionGroundTruth,
        submission: RecognitionSubmission,
        *,
        confidence_threshold: float = 0.95,
    ) -> RecognitionReport:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise RecognitionBenchmarkError("confidence_threshold must be between 0 and 1")
        if (
            ground_truth.dataset_id != submission.dataset_id
            or ground_truth.dataset_version != submission.dataset_version
        ):
            raise RecognitionBenchmarkError("Ground Truth and submission dataset do not match")

        expected = {case.case_id: case for case in ground_truth.cases}
        predicted = {case.case_id: case for case in submission.cases}
        if expected.keys() != predicted.keys():
            raise RecognitionBenchmarkError("Ground Truth and prediction case IDs must match")

        exact_count = 0
        reference_character_count = 0
        character_error_count = 0
        reference_word_count = 0
        word_error_count = 0
        reference_diacritic_count = 0
        diacritic_error_count = 0
        nfc_violation_count = 0
        accepted_count = 0
        accepted_exact_count = 0
        durations: list[float] = []

        for case_id, expected_case in expected.items():
            predicted_case = predicted[case_id]
            reference = normalize_for_evaluation(expected_case.text)
            raw_prediction = predicted_case.text
            prediction = normalize_for_evaluation(raw_prediction)
            exact = reference == prediction
            exact_count += int(exact)
            nfc_violation_count += int(not unicodedata.is_normalized("NFC", raw_prediction))

            reference_characters = tuple(reference)
            prediction_characters = tuple(prediction)
            character_edits = edit_distance(reference_characters, prediction_characters)
            base_edits = edit_distance(
                tuple(strip_vietnamese_diacritics(reference)),
                tuple(strip_vietnamese_diacritics(prediction)),
            )
            reference_character_count += len(reference_characters)
            character_error_count += character_edits
            reference_word_count += len(reference.split())
            word_error_count += edit_distance(tuple(reference.split()), tuple(prediction.split()))
            reference_diacritic_count += count_vietnamese_diacritics(reference)
            diacritic_error_count += max(0, character_edits - base_edits)
            durations.append(predicted_case.duration_ms)

            if predicted_case.confidence >= confidence_threshold:
                accepted_count += 1
                accepted_exact_count += int(exact)

        metrics = RecognitionMetrics(
            case_count=len(expected),
            exact_match_count=exact_count,
            exact_match_rate=_rate(exact_count, len(expected)),
            reference_character_count=reference_character_count,
            character_error_count=character_error_count,
            character_error_rate=_rate(character_error_count, reference_character_count),
            reference_word_count=reference_word_count,
            word_error_count=word_error_count,
            word_error_rate=_rate(word_error_count, reference_word_count),
            reference_diacritic_count=reference_diacritic_count,
            diacritic_error_count=diacritic_error_count,
            diacritic_error_rate=_rate(diacritic_error_count, reference_diacritic_count),
            prediction_nfc_violation_count=nfc_violation_count,
            accepted_count=accepted_count,
            accepted_exact_count=accepted_exact_count,
            accepted_precision=_rate(accepted_exact_count, accepted_count),
            confidence_threshold=confidence_threshold,
            latency_p50_ms=percentile(durations, 0.50),
            latency_p95_ms=percentile(durations, 0.95),
        )
        return RecognitionReport(
            dataset_id=ground_truth.dataset_id,
            dataset_version=ground_truth.dataset_version,
            dataset_content_digest=ground_truth.content_digest,
            backend_name=submission.backend_name,
            backend_version=submission.backend_version,
            model_identifier=submission.model_identifier,
            metrics=metrics,
        )


def audit_vietnamese_charset(
    characters: str,
    *,
    model_identifier: str,
) -> CharsetAuditReport:
    available = set(unicodedata.normalize("NFC", characters))
    required = set(required_vietnamese_extended_characters())
    missing = tuple(sorted(required - available))
    present_count = len(required) - len(missing)
    return CharsetAuditReport(
        model_identifier=model_identifier,
        required_character_count=len(required),
        present_character_count=present_count,
        missing_character_count=len(missing),
        coverage=_rate(present_count, len(required)),
        missing_characters=missing,
    )


def required_vietnamese_extended_characters() -> tuple[str, ...]:
    groups = ("aăâ", "eê", "i", "oôơ", "uư", "y")
    tones = ("", "\u0300", "\u0301", "\u0303", "\u0309", "\u0323")
    characters = {"đ", "Đ"}
    for group in groups:
        for base in group:
            for tone in tones:
                for value in (base, base.upper()):
                    composed = unicodedata.normalize("NFC", value + tone)
                    if not composed.isascii():
                        characters.add(composed)
    return tuple(sorted(characters))


def normalize_for_evaluation(value: str) -> str:
    return ocr_metrics.normalize_for_evaluation(value)


def strip_vietnamese_diacritics(value: str) -> str:
    return ocr_metrics.strip_vietnamese_diacritics(value)


def count_vietnamese_diacritics(value: str) -> int:
    return ocr_metrics.count_vietnamese_diacritics(value)


def edit_distance(reference: Sequence[str], prediction: Sequence[str]) -> int:
    return ocr_metrics.edit_distance(reference, prediction)


def percentile(values: Sequence[float], quantile: float) -> float:
    return ocr_metrics.percentile(values, quantile)


def _rate(numerator: int, denominator: int) -> float:
    return ocr_metrics.rate(numerator, denominator)
