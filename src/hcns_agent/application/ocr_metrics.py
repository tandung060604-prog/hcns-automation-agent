"""Canonical, versioned text metrics for Vietnamese OCR evaluation.

Exact Match is deliberately strict after NFC and whitespace normalization.
Case-folded equality is exposed separately for agreement/review workflows and
must never replace the strict evaluation metric.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar

METRIC_SPEC_VERSION = "vi-ocr-metrics/1.0.0"

_Item = TypeVar("_Item")


@dataclass(frozen=True, slots=True)
class CorpusTextMetrics:
    case_count: int
    strict_exact_count: int
    strict_exact_rate: float
    casefold_exact_count: int
    casefold_exact_rate: float
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


def evaluate_text_pairs(
    pairs: Sequence[tuple[str, str]],
) -> CorpusTextMetrics:
    """Evaluate reference/prediction pairs under the canonical metric spec."""

    strict_exact_count = 0
    casefold_exact_count = 0
    reference_character_count = 0
    character_error_count = 0
    reference_word_count = 0
    word_error_count = 0
    reference_diacritic_count = 0
    diacritic_error_count = 0
    prediction_nfc_violation_count = 0

    for raw_reference, raw_prediction in pairs:
        reference = normalize_for_evaluation(raw_reference)
        prediction = normalize_for_evaluation(raw_prediction)
        strict_exact_count += int(reference == prediction)
        casefold_exact_count += int(
            normalize_for_agreement(reference) == normalize_for_agreement(prediction)
        )
        prediction_nfc_violation_count += int(
            not unicodedata.is_normalized("NFC", raw_prediction)
        )

        character_edits = edit_distance(tuple(reference), tuple(prediction))
        base_edits = edit_distance(
            tuple(strip_vietnamese_diacritics(reference)),
            tuple(strip_vietnamese_diacritics(prediction)),
        )
        reference_character_count += len(reference)
        character_error_count += character_edits
        reference_word_count += len(reference.split())
        word_error_count += edit_distance(
            tuple(reference.split()),
            tuple(prediction.split()),
        )
        reference_diacritic_count += count_vietnamese_diacritics(reference)
        diacritic_error_count += max(0, character_edits - base_edits)

    case_count = len(pairs)
    return CorpusTextMetrics(
        case_count=case_count,
        strict_exact_count=strict_exact_count,
        strict_exact_rate=rate(strict_exact_count, case_count),
        casefold_exact_count=casefold_exact_count,
        casefold_exact_rate=rate(casefold_exact_count, case_count),
        reference_character_count=reference_character_count,
        character_error_count=character_error_count,
        character_error_rate=rate(character_error_count, reference_character_count),
        reference_word_count=reference_word_count,
        word_error_count=word_error_count,
        word_error_rate=rate(word_error_count, reference_word_count),
        reference_diacritic_count=reference_diacritic_count,
        diacritic_error_count=diacritic_error_count,
        diacritic_error_rate=rate(
            diacritic_error_count,
            reference_diacritic_count,
        ),
        prediction_nfc_violation_count=prediction_nfc_violation_count,
    )


def normalize_for_evaluation(value: str) -> str:
    """Normalize Unicode representation and whitespace while preserving case."""

    return " ".join(unicodedata.normalize("NFC", value).split())


def normalize_for_agreement(value: str) -> str:
    """Normalize recognizer agreement without changing evaluation truth."""

    return normalize_for_evaluation(value).casefold()


def strip_vietnamese_diacritics(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    stripped = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return stripped.translate(str.maketrans("đĐ", "dD"))


def count_vietnamese_diacritics(value: str) -> int:
    return sum(
        1
        for character in unicodedata.normalize("NFC", value)
        if strip_vietnamese_diacritics(character) != character
    )


def edit_distance(
    reference: Sequence[_Item],
    prediction: Sequence[_Item],
) -> int:
    previous = list(range(len(prediction) + 1))
    for reference_index, reference_value in enumerate(reference, start=1):
        current = [reference_index]
        for prediction_index, prediction_value in enumerate(prediction, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[prediction_index] + 1,
                    previous[prediction_index - 1]
                    + int(reference_value != prediction_value),
                )
            )
        previous = current
    return previous[-1]


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(
        0,
        min(len(ordered) - 1, int(len(ordered) * quantile + 0.999999) - 1),
    )
    return round(float(ordered[index]), 4)


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
