"""Aggregate-only evaluation for the blinded Phase 14.7 held-out corpus."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hcns_agent.application.ocr_metrics import (
    METRIC_SPEC_VERSION,
    evaluate_text_pairs,
    normalize_for_agreement,
    normalize_for_evaluation,
)

PRIMARY = "vietocr_vgg_seq2seq"
TRANSFORMER = "vietocr_vgg_transformer"
PADDLE = "paddle_detector_raw"
PROFILES = (PRIMARY, TRANSFORMER, PADDLE)


def _safe_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def fixed_policy_prediction(
    case: Mapping[str, Any],
    *,
    confidence_threshold: float,
) -> tuple[str, str]:
    predictions = case["predictions"]
    primary = str(predictions[PRIMARY].get("text", ""))
    transformer = str(predictions[TRANSFORMER].get("text", ""))
    paddle = str(predictions[PADDLE].get("text", ""))
    confidence = _safe_confidence(predictions[PRIMARY].get("confidence"))
    if (
        transformer
        and normalize_for_agreement(transformer)
        == normalize_for_agreement(paddle)
        and normalize_for_agreement(transformer)
        != normalize_for_agreement(primary)
    ):
        return transformer, "transformer_paddle_agreement"
    if (
        confidence < confidence_threshold
        and paddle
        and normalize_for_agreement(paddle)
        != normalize_for_agreement(primary)
    ):
        return paddle, "low_primary_confidence_paddle_candidate"
    return primary, "primary_unchanged"


def metric_payload(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    metrics = evaluate_text_pairs(pairs)
    return {
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
        "der": metrics.diacritic_error_rate,
        "predictionNfcViolationCount": metrics.prediction_nfc_violation_count,
    }


def evaluate_phase14_7(
    *,
    snapshot: Mapping[str, Any],
    ground_truth: Mapping[str, Any],
    policy: Mapping[str, Any],
    minimum_document_count: int,
    evaluated_at: str,
    snapshot_sha256: str,
    ground_truth_sha256: str,
    dataset_lock_sha256: str,
) -> dict[str, Any]:
    """Evaluate confirmed lines without returning any line text or PII."""

    if snapshot.get("predictionsHiddenDuringReview") is not True:
        raise ValueError("Prediction snapshot was not blinded")
    if snapshot.get("groundTruthPresent") is not False:
        raise ValueError("Prediction snapshot contains Ground Truth")
    if (
        ground_truth.get("groundTruthStatus")
        != "USER_CONFIRMED_HELD_OUT_GROUND_TRUTH"
        or ground_truth.get("predictionsVisibleDuringReview") is not False
        or not ground_truth.get("confirmedAt")
    ):
        raise ValueError("Ground Truth confirmation evidence is incomplete")
    if ground_truth.get("queueDigest") != snapshot.get("queueDigest"):
        raise ValueError("Ground Truth and prediction queue digests differ")
    if ground_truth.get("datasetDigest") != snapshot.get("datasetDigest"):
        raise ValueError("Ground Truth and predictions use different datasets")

    prediction_cases = {
        str(case["caseId"]): case for case in snapshot.get("cases", [])
    }
    truth_cases = {
        str(case["caseId"]): case for case in ground_truth.get("cases", [])
    }
    if not prediction_cases or prediction_cases.keys() != truth_cases.keys():
        raise ValueError("Ground Truth and prediction case IDs do not match")
    if any(case.get("status") == "PENDING_REVIEW" for case in truth_cases.values()):
        raise ValueError("Ground Truth review is not complete")

    confirmed_ids = [
        case_id
        for case_id, case in truth_cases.items()
        if case.get("status") == "CONFIRMED"
    ]
    skipped_count = sum(
        case.get("status") == "SKIPPED" for case in truth_cases.values()
    )
    if not confirmed_ids:
        raise ValueError("Ground Truth has no confirmed lines")
    for case_id in confirmed_ids:
        if not str(truth_cases[case_id].get("confirmedTranscription", "")).strip():
            raise ValueError("A confirmed Ground Truth line is empty")
        profiles = prediction_cases[case_id].get("predictions")
        if not isinstance(profiles, Mapping) or any(
            profile not in profiles for profile in PROFILES
        ):
            raise ValueError("A prediction case is missing a locked profile")

    profile_metrics: dict[str, dict[str, Any]] = {}
    for profile in PROFILES:
        pairs = [
            (
                str(truth_cases[case_id]["confirmedTranscription"]),
                str(
                    prediction_cases[case_id]["predictions"][profile].get(
                        "text", ""
                    )
                ),
            )
            for case_id in confirmed_ids
        ]
        profile_metrics[profile] = metric_payload(pairs)

    threshold = float(policy["primaryConfidenceReviewThreshold"])
    selected_pairs: list[tuple[str, str]] = []
    baseline_correct_lost = 0
    baseline_errors_recovered = 0
    switch_count = 0
    reason_counts: dict[str, int] = {}
    for case_id in confirmed_ids:
        reference = str(truth_cases[case_id]["confirmedTranscription"])
        prediction_case = prediction_cases[case_id]
        primary = str(prediction_case["predictions"][PRIMARY].get("text", ""))
        selected, reason = fixed_policy_prediction(
            prediction_case,
            confidence_threshold=threshold,
        )
        selected_pairs.append((reference, selected))
        normalized_reference = normalize_for_evaluation(reference)
        normalized_primary = normalize_for_evaluation(primary)
        normalized_selected = normalize_for_evaluation(selected)
        switched = normalize_for_agreement(selected) != normalize_for_agreement(
            primary
        )
        switch_count += int(switched)
        baseline_correct_lost += int(
            switched
            and normalized_primary == normalized_reference
            and normalized_selected != normalized_reference
        )
        baseline_errors_recovered += int(
            switched
            and normalized_primary != normalized_reference
            and normalized_selected == normalized_reference
        )
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    selected_metrics = metric_payload(selected_pairs)
    baseline_metrics = profile_metrics[PRIMARY]
    zero_loss = baseline_correct_lost == 0
    no_exact_regression = (
        selected_metrics["exactMatchRate"]
        >= baseline_metrics["exactMatchRate"]
    )
    no_der_regression = selected_metrics["der"] <= baseline_metrics["der"]
    document_count = int(snapshot["documentCount"])
    enough_documents = document_count >= minimum_document_count
    quality_signals_pass = zero_loss and no_exact_regression and no_der_regression
    diagnostic_candidate = (
        "QUALITY_SIGNALS_PASS"
        if quality_signals_pass
        else "QUALITY_SIGNALS_FAIL"
    )

    return {
        "schemaVersion": "phase14.7-heldout-evaluation/1.0.0",
        "evaluatedAt": evaluated_at,
        "containsRealPII": False,
        "evaluationRunCount": 1,
        "thresholdRetuned": False,
        "predictionsWereHidden": True,
        "metricSpecVersion": METRIC_SPEC_VERSION,
        "datasetId": snapshot.get("datasetId"),
        "datasetDigest": snapshot.get("datasetDigest"),
        "datasetLockSha256": dataset_lock_sha256,
        "sealedPredictionsSha256": snapshot_sha256,
        "groundTruthSha256": ground_truth_sha256,
        "documentCount": document_count,
        "minimumDocumentCount": minimum_document_count,
        "review": {
            "totalLineCount": len(truth_cases),
            "evaluatedConfirmedLineCount": len(confirmed_ids),
            "skippedLineCount": skipped_count,
            "pendingLineCount": 0,
            "predictionsVisibleDuringReview": False,
        },
        "profiles": profile_metrics,
        "fixedPolicyReplay": {
            "policyId": policy["policyId"],
            "policyVersion": policy["version"],
            "mode": policy["mode"],
            "metrics": selected_metrics,
            "switchCount": switch_count,
            "baselineErrorsRecovered": baseline_errors_recovered,
            "baselineCorrectLost": baseline_correct_lost,
            "selectionReasons": dict(sorted(reason_counts.items())),
        },
        "decision": {
            "diagnosticQualitySignals": diagnostic_candidate,
            "heldOutSampleGate": (
                "PASS" if enough_documents else "INSUFFICIENT_DOCUMENTS"
            ),
            "controlledPilot": (
                "NOT_PROMOTED_INSUFFICIENT_DOCUMENTS"
                if not enough_documents
                else (
                    "ELIGIBLE_FOR_CONTROLLED_PILOT"
                    if quality_signals_pass
                    else "NOT_PROMOTED"
                )
            ),
            "production": "NOT_PRODUCTION_READY",
            "zeroBaselineCorrectLoss": zero_loss,
            "noExactRegression": no_exact_regression,
            "noDiacriticErrorRegression": no_der_regression,
            "sensitiveFieldFalseAcceptance": "NOT_MEASURED_AT_LINE_LEVEL",
        },
    }
