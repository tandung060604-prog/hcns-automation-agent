#!/usr/bin/env python3
"""Aggregate Phase 14.5 OCR errors and evaluate review-only fallback rules.

The input contains private Ground Truth and predictions. Outputs are aggregate
only: no document key, crop path, Ground Truth or recognized text is retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hcns_agent.application.ocr_metrics import (
    METRIC_SPEC_VERSION,
    edit_distance,
    evaluate_text_pairs,
    normalize_for_agreement,
    normalize_for_evaluation,
    strip_vietnamese_diacritics,
)
from hcns_agent.application.recognition_policy import PHASE14_6_SHADOW_POLICY

PRIMARY_PROFILE = "vietocr_vgg_seq2seq"
TRANSFORMER_PROFILE = "vietocr_vgg_transformer"
PADDLE_PROFILE = "paddle_detector_raw"
THRESHOLDS: tuple[float | None, ...] = (None,) + tuple(
    round(index / 20, 2) for index in range(1, 20)
)


@dataclass(frozen=True)
class LineRecord:
    document_key: str
    ground_truth: str
    primary: str
    transformer: str
    paddle: str
    primary_confidence: float


def normalize(value: Any) -> str:
    return normalize_for_evaluation(str(value))


def strip_diacritics(value: str) -> str:
    return strip_vietnamese_diacritics(value)


def classify_error(reference: str, prediction: str) -> str:
    if reference == prediction:
        return "exact"
    if not prediction:
        return "empty"
    if strip_diacritics(reference) == strip_diacritics(prediction):
        return "diacritic_only"
    if len(prediction) < len(reference):
        return "missing_or_substituted_characters"
    if len(prediction) > len(reference):
        return "extra_or_substituted_characters"
    return "substitution_or_spacing"


def aggregate_metrics(
    records: Sequence[LineRecord],
    predictions: Sequence[str],
) -> dict[str, Any]:
    if len(records) != len(predictions):
        raise ValueError("Prediction count does not match record count")
    metrics = evaluate_text_pairs(
        [
            (record.ground_truth, prediction)
            for record, prediction in zip(records, predictions, strict=True)
        ]
    )
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
    }


def safe_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def load_records(path: Path) -> tuple[list[LineRecord], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Input does not contain benchmark cases")
    records: list[LineRecord] = []
    required_profiles = {
        PRIMARY_PROFILE,
        TRANSFORMER_PROFILE,
        PADDLE_PROFILE,
    }
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("A benchmark case is invalid")
        predictions = case.get("predictions")
        if not isinstance(predictions, dict) or not required_profiles.issubset(
            predictions
        ):
            raise ValueError("A benchmark case is missing recognizer profiles")
        ground_truth = normalize(case.get("groundTruth", ""))
        document_key = str(case.get("documentKey", "")).strip()
        if not ground_truth or not document_key:
            raise ValueError("A benchmark case is missing reviewed Ground Truth")
        primary_payload = predictions[PRIMARY_PROFILE]
        records.append(
            LineRecord(
                document_key=document_key,
                ground_truth=ground_truth,
                primary=normalize(primary_payload.get("text", "")),
                transformer=normalize(
                    predictions[TRANSFORMER_PROFILE].get("text", "")
                ),
                paddle=normalize(predictions[PADDLE_PROFILE].get("text", "")),
                primary_confidence=safe_confidence(
                    primary_payload.get("confidence")
                ),
            )
        )
    document_count = len({record.document_key for record in records})
    expected_lines = int(payload.get("lineCount", len(records)))
    expected_documents = int(payload.get("documentCount", document_count))
    if expected_lines != len(records) or expected_documents != document_count:
        raise ValueError("Input aggregate counts do not match benchmark cases")
    return records, payload


def conditional_prediction(
    record: LineRecord,
    threshold: float | None,
) -> tuple[str, str]:
    if (
        record.transformer
        and normalize_for_agreement(record.transformer)
        == normalize_for_agreement(record.paddle)
        and normalize_for_agreement(record.transformer)
        != normalize_for_agreement(record.primary)
    ):
        return record.transformer, "transformer_paddle_agreement"
    if (
        threshold is not None
        and record.primary_confidence < threshold
        and record.paddle
        and normalize_for_agreement(record.paddle)
        != normalize_for_agreement(record.primary)
    ):
        return record.paddle, "low_primary_confidence_paddle_candidate"
    return record.primary, "primary_unchanged"


def predictions_for(
    records: Sequence[LineRecord],
    threshold: float | None,
) -> tuple[list[str], Counter[str]]:
    predictions: list[str] = []
    reasons: Counter[str] = Counter()
    for record in records:
        prediction, reason = conditional_prediction(record, threshold)
        predictions.append(prediction)
        reasons[reason] += 1
    return predictions, reasons


def selection_score(
    records: Sequence[LineRecord],
    threshold: float | None,
) -> tuple[int, int, int, int]:
    predictions, _ = predictions_for(records, threshold)
    exact_count = 0
    baseline_losses = 0
    switches = 0
    char_errors = 0
    for record, prediction in zip(records, predictions, strict=True):
        exact_count += prediction == record.ground_truth
        switched = normalize_for_agreement(prediction) != normalize_for_agreement(
            record.primary
        )
        switches += switched
        baseline_losses += (
            switched
            and record.primary == record.ground_truth
            and prediction != record.ground_truth
        )
        char_errors += edit_distance(record.ground_truth, prediction)
    # Zero regression is the first constraint. An exploratory threshold may
    # recover more errors, but it must not outrank a threshold that preserves
    # every baseline-correct line.
    return -baseline_losses, exact_count, -switches, -char_errors


def select_threshold(records: Sequence[LineRecord]) -> float | None:
    return max(
        THRESHOLDS,
        key=lambda threshold: selection_score(records, threshold),
    )


def leave_one_document_out(
    records: Sequence[LineRecord],
) -> tuple[list[str], Counter[str], Counter[str], float | None]:
    documents = sorted({record.document_key for record in records})
    held_out_by_position: dict[int, str] = {}
    reasons: Counter[str] = Counter()
    threshold_votes: Counter[str] = Counter()
    for document in documents:
        training = [
            record for record in records if record.document_key != document
        ]
        threshold = select_threshold(training)
        threshold_label = "consensus_only" if threshold is None else f"{threshold:.2f}"
        threshold_votes[threshold_label] += 1
        for position, record in enumerate(records):
            if record.document_key != document:
                continue
            prediction, reason = conditional_prediction(record, threshold)
            held_out_by_position[position] = prediction
            reasons[reason] += 1
    if len(held_out_by_position) != len(records):
        raise ValueError("Document-level validation did not cover every line")
    recommended_label = sorted(
        threshold_votes,
        key=lambda label: (
            -threshold_votes[label],
            label == "consensus_only",
            float(label) if label != "consensus_only" else -1.0,
        ),
    )[0]
    recommended_threshold = (
        None
        if recommended_label == "consensus_only"
        else float(recommended_label)
    )
    predictions = [
        held_out_by_position[position] for position in range(len(records))
    ]
    return predictions, reasons, threshold_votes, recommended_threshold


def pairwise_agreement(
    records: Sequence[LineRecord],
    left: str,
    right: str,
) -> dict[str, Any]:
    agreed = 0
    exact = 0
    for record in records:
        left_value = getattr(record, left)
        right_value = getattr(record, right)
        if left_value and normalize_for_agreement(
            left_value
        ) == normalize_for_agreement(right_value):
            agreed += 1
            exact += left_value == record.ground_truth
    return {
        "agreementCount": agreed,
        "agreementRate": round(agreed / max(1, len(records)), 6),
        "exactAgreementCount": exact,
        "agreementPrecision": round(exact / max(1, agreed), 6),
    }


def outcome_summary(
    records: Sequence[LineRecord],
    predictions: Sequence[str],
) -> dict[str, Any]:
    recovered = 0
    lost = 0
    switches = 0
    per_document: dict[str, list[int]] = {}
    for record, prediction in zip(records, predictions, strict=True):
        primary_exact = record.primary == record.ground_truth
        selected_exact = prediction == record.ground_truth
        switched = normalize_for_agreement(prediction) != normalize_for_agreement(
            record.primary
        )
        switches += switched
        recovered += switched and selected_exact and not primary_exact
        lost += switched and primary_exact and not selected_exact
        values = per_document.setdefault(record.document_key, [0, 0])
        values[0] += primary_exact
        values[1] += selected_exact
    improved = sum(selected > primary for primary, selected in per_document.values())
    regressed = sum(selected < primary for primary, selected in per_document.values())
    return {
        "switchCount": switches,
        "baselineErrorsRecovered": recovered,
        "baselineCorrectLost": lost,
        "netExactGain": recovered - lost,
        "documentsImproved": improved,
        "documentsRegressed": regressed,
        "documentsUnchanged": len(per_document) - improved - regressed,
    }


def error_taxonomy(
    records: Sequence[LineRecord],
    predictions: Sequence[str],
) -> dict[str, int]:
    counts = Counter(
        classify_error(record.ground_truth, prediction)
        for record, prediction in zip(records, predictions, strict=True)
    )
    return dict(sorted(counts.items()))


def build_analysis(
    records: Sequence[LineRecord],
    source_payload: dict[str, Any],
    source_digest: str,
) -> dict[str, Any]:
    primary_predictions = [record.primary for record in records]
    transformer_predictions = [record.transformer for record in records]
    paddle_predictions = [record.paddle for record in records]
    cv_predictions, cv_reasons, threshold_votes, threshold = (
        leave_one_document_out(records)
    )
    recommended_predictions, recommended_reasons = predictions_for(
        records, threshold
    )
    oracle_exact = sum(
        record.ground_truth
        in {record.primary, record.transformer, record.paddle}
        for record in records
    )
    primary_errors = sum(
        record.primary != record.ground_truth for record in records
    )
    transformer_recoveries = sum(
        record.primary != record.ground_truth
        and record.transformer == record.ground_truth
        for record in records
    )
    paddle_recoveries = sum(
        record.primary != record.ground_truth
        and record.paddle == record.ground_truth
        for record in records
    )
    primary_taxonomy = error_taxonomy(records, primary_predictions)
    primary_taxonomy.pop("exact", None)
    return {
        "schemaVersion": "14.5.0-private-aggregate",
        "metricSpecVersion": METRIC_SPEC_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "containsRealPII": False,
        "sourceArtifactSha256": f"sha256:{source_digest}",
        "groundTruthStatus": source_payload.get("groundTruthStatus"),
        "predictionSource": source_payload.get("predictionSource"),
        "documentCount": len({record.document_key for record in records}),
        "lineCount": len(records),
        "profiles": {
            PRIMARY_PROFILE: aggregate_metrics(records, primary_predictions),
            TRANSFORMER_PROFILE: aggregate_metrics(
                records, transformer_predictions
            ),
            PADDLE_PROFILE: aggregate_metrics(records, paddle_predictions),
        },
        "primaryErrorAnalysis": {
            "errorCount": primary_errors,
            "categoryCounts": primary_taxonomy,
            "transformerExactRecoveryCount": transformer_recoveries,
            "paddleExactRecoveryCount": paddle_recoveries,
            "threeRecognizerOracleExactCount": oracle_exact,
            "threeRecognizerOracleExactRate": round(
                oracle_exact / max(1, len(records)),
                6,
            ),
        },
        "agreements": {
            "primaryTransformer": pairwise_agreement(
                records, "primary", "transformer"
            ),
            "primaryPaddle": pairwise_agreement(
                records, "primary", "paddle"
            ),
            "transformerPaddle": pairwise_agreement(
                records, "transformer", "paddle"
            ),
        },
        "documentLevelValidation": {
            "method": "LEAVE_ONE_DOCUMENT_OUT_THRESHOLD_SELECTION",
            "candidateThresholds": [
                "consensus_only" if value is None else value
                for value in THRESHOLDS
            ],
            "thresholdVotes": dict(sorted(threshold_votes.items())),
            "recommendedPrimaryConfidenceThreshold": threshold,
            "metrics": aggregate_metrics(records, cv_predictions),
            "outcomes": outcome_summary(records, cv_predictions),
            "selectionReasons": dict(sorted(cv_reasons.items())),
        },
        "resubstitutionEstimate": {
            "metrics": aggregate_metrics(records, recommended_predictions),
            "outcomes": outcome_summary(records, recommended_predictions),
            "selectionReasons": dict(sorted(recommended_reasons.items())),
        },
        "recommendedPolicy": {
            **PHASE14_6_SHADOW_POLICY.manifest(),
            "status": "SHADOW_REVIEW_ONLY",
            "primary": PRIMARY_PROFILE,
            "rules": [
                "Use transformer when it exactly agrees with Paddle "
                "and differs from primary",
                "Below the selected primary confidence threshold, "
                "expose Paddle as review candidate",
                "Every changed candidate remains needs_review",
            ],
            "autoAcceptChangedCandidate": False,
            "productionDecision": "NOT_PRODUCTION_READY",
            "nextGate": (
                "Repeat unchanged policy on held-out authorized documents; "
                "require zero baseline-correct loss before controlled promotion"
            ),
        },
    }


def build_markdown(payload: dict[str, Any]) -> str:
    profiles = payload["profiles"]
    validation = payload["documentLevelValidation"]
    outcomes = validation["outcomes"]
    errors = payload["primaryErrorAnalysis"]
    lines = [
        "# Phase 14.5 — Conditional fallback analysis",
        "",
        "Báo cáo chỉ chứa số liệu tổng hợp; Ground Truth và prediction "
        "không được ghi vào file này.",
        "",
        f"- Documents: {payload['documentCount']}",
        f"- Confirmed line crops: {payload['lineCount']}",
        f"- Primary errors: {errors['errorCount']}",
        f"- Decision: `{payload['recommendedPolicy']['status']}` / `NOT_PRODUCTION_READY`",
        "",
        "## Recognizer metrics",
        "",
        "| Profile | Exact Match | CER | WER | DER |",
        "|---|---:|---:|---:|---:|",
    ]
    for profile in (PRIMARY_PROFILE, TRANSFORMER_PROFILE, PADDLE_PROFILE):
        metrics = profiles[profile]
        lines.append(
            f"| `{profile}` | {metrics['exactMatchRate']:.2%} | "
            f"{metrics['cer']:.2%} | {metrics['wer']:.2%} | "
            f"{metrics['diacriticErrorRate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Primary error taxonomy",
            "",
            "| Category | Count |",
            "|---|---:|",
        ]
    )
    for category, count in errors["categoryCounts"].items():
        lines.append(f"| `{category}` | {count} |")
    metrics = validation["metrics"]
    lines.extend(
        [
            "",
            "## Document-level validation",
            "",
            f"- Method: `{validation['method']}`",
            "- Recommended confidence threshold: "
            f"`{validation['recommendedPrimaryConfidenceThreshold']}`",
            f"- Exact Match: {metrics['exactMatchRate']:.2%}",
            f"- CER: {metrics['cer']:.2%}",
            f"- WER: {metrics['wer']:.2%}",
            f"- DER: {metrics['diacriticErrorRate']:.2%}",
            f"- Switches: {outcomes['switchCount']}",
            f"- Baseline errors recovered: {outcomes['baselineErrorsRecovered']}",
            f"- Baseline-correct lines lost: {outcomes['baselineCorrectLost']}",
            f"- Documents improved/regressed: "
            f"{outcomes['documentsImproved']}/{outcomes['documentsRegressed']}",
            "",
            "## Decision",
            "",
            "Fallback chỉ được chạy ở chế độ shadow/review. Mọi candidate thay đổi text "
            "phải giữ `needs_review`; chưa có auto-accept hoặc production promotion.",
            "",
        ]
    )
    return "\n".join(lines)


def write_output(path: Path, content: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze Phase 14.5 private OCR predictions safely"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.is_file():
        raise SystemExit("Private benchmark input does not exist")
    source_bytes = args.input.read_bytes()
    records, source_payload = load_records(args.input)
    payload = build_analysis(
        records,
        source_payload,
        hashlib.sha256(source_bytes).hexdigest(),
    )
    write_output(
        args.output_json,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        args.overwrite,
    )
    write_output(args.output_md, build_markdown(payload), args.overwrite)
    validation = payload["documentLevelValidation"]
    print(
        "Phase 14.5 complete: "
        f"{payload['documentCount']} documents, "
        f"{payload['lineCount']} lines, "
        f"{validation['outcomes']['baselineErrorsRecovered']} recovered, "
        f"{validation['outcomes']['baselineCorrectLost']} lost, "
        f"{payload['recommendedPolicy']['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
