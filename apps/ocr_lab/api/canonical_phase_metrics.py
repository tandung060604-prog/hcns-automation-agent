"""Canonical aggregate adapter for private Phase 14 benchmark payloads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hcns_agent.application.ocr_metrics import (
    METRIC_SPEC_VERSION,
    evaluate_text_pairs,
    percentile,
)


def aggregate_profile(
    cases: list[dict[str, Any]],
    profile: str,
    reference_for: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    pairs = [
        (
            reference_for(case),
            str(case["predictions"][profile].get("text", "")),
        )
        for case in cases
    ]
    metrics = evaluate_text_pairs(pairs)
    durations = [
        float(case["predictions"][profile].get("durationMs", 0.0))
        for case in cases
    ]
    return {
        "metricSpecVersion": METRIC_SPEC_VERSION,
        "lineCount": metrics.case_count,
        "exactMatchCount": metrics.strict_exact_count,
        "exactMatchRate": metrics.strict_exact_rate,
        "casefoldExactMatchCount": metrics.casefold_exact_count,
        "casefoldExactMatchRate": metrics.casefold_exact_rate,
        "referenceCharacterCount": metrics.reference_character_count,
        "characterErrorCount": metrics.character_error_count,
        "cer": metrics.character_error_rate,
        "referenceWordCount": metrics.reference_word_count,
        "wordErrorCount": metrics.word_error_count,
        "wer": metrics.word_error_rate,
        "referenceDiacriticCount": metrics.reference_diacritic_count,
        "diacriticErrorCount": metrics.diacritic_error_count,
        "diacriticErrorRate": metrics.diacritic_error_rate,
        "meanDurationMs": round(sum(durations) / max(1, len(durations)), 3),
        "p95DurationMs": percentile(durations, 0.95),
    }
