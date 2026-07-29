#!/usr/bin/env python3
"""Seal hidden predictions and evaluate Phase 14.6 exactly once.

Both prediction and Ground Truth inputs are private. The final output contains
aggregate metrics only and is safe for disclosure review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hcns_agent.application.ocr_metrics import (
    METRIC_SPEC_VERSION,
    evaluate_text_pairs,
    normalize_for_agreement,
    normalize_for_evaluation,
)
from hcns_agent.application.recognition_policy import PHASE14_6_SHADOW_POLICY
from scripts.validate_phase14_6_lock import load_and_validate_lock, sha256_file

PRIMARY = "vietocr_vgg_seq2seq"
TRANSFORMER = "vietocr_vgg_transformer"
PADDLE = "paddle_detector_raw"
REQUIRED_PROFILES = (PRIMARY, TRANSFORMER, PADDLE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def contains_ground_truth(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            "groundtruth" in str(key).replace("_", "").casefold()
            or contains_ground_truth(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(contains_ground_truth(child) for child in value)
    return False


def seal_predictions(
    predictions: dict[str, Any],
    lock: dict[str, Any],
    *,
    lock_digest: str,
    source_digest: str,
) -> dict[str, Any]:
    if contains_ground_truth(predictions):
        raise ValueError("Prediction artifact must not contain Ground Truth")
    cases = predictions.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Prediction artifact has no cases")
    document_count = int(predictions.get("documentCount", 0))
    minimum_documents = int(lock["heldOutProtocol"]["minimumDocumentCount"])
    if document_count < minimum_documents:
        raise ValueError(
            f"Held-out corpus requires at least {minimum_documents} documents"
        )
    if int(predictions.get("lineCount", len(cases))) != len(cases):
        raise ValueError("Prediction line count does not match cases")

    case_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("caseId", ""))
        profiles = case.get("predictions")
        if not case_id or case_id in case_ids:
            raise ValueError("Prediction case IDs must be unique and non-empty")
        if not isinstance(profiles, dict) or any(
            profile not in profiles for profile in REQUIRED_PROFILES
        ):
            raise ValueError("A held-out case is missing a locked profile")
        case_ids.add(case_id)

    return {
        "schemaVersion": "phase14.6-hidden-predictions/1.0.0",
        "sealedAt": utc_now(),
        "containsRealPII": True,
        "predictionsHiddenDuringReview": True,
        "groundTruthPresent": False,
        "metricSpecVersion": METRIC_SPEC_VERSION,
        "policyDigest": lock["policy"]["policyDigest"],
        "lockFileSha256": f"sha256:{lock_digest}",
        "sourcePredictionsSha256": f"sha256:{source_digest}",
        "datasetId": predictions.get("datasetId"),
        "datasetDigest": predictions.get("datasetDigest"),
        "documentCount": document_count,
        "lineCount": len(cases),
        "cases": cases,
    }


def fixed_policy_prediction(case: dict[str, Any]) -> tuple[str, str]:
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
    threshold = PHASE14_6_SHADOW_POLICY.primary_confidence_review_threshold
    if (
        threshold is not None
        and confidence < threshold
        and paddle
        and normalize_for_agreement(paddle)
        != normalize_for_agreement(primary)
    ):
        return paddle, "low_primary_confidence_paddle_candidate"
    return primary, "primary_unchanged"


def evaluate_once(
    sealed: dict[str, Any],
    ground_truth: dict[str, Any],
    lock: dict[str, Any],
    *,
    sealed_digest: str,
    ground_truth_digest: str,
) -> dict[str, Any]:
    if sealed.get("predictionsHiddenDuringReview") is not True:
        raise ValueError("Predictions were not sealed before review")
    if sealed.get("policyDigest") != lock["policy"]["policyDigest"]:
        raise ValueError("Sealed predictions use a different policy")
    if sealed.get("metricSpecVersion") != METRIC_SPEC_VERSION:
        raise ValueError("Sealed predictions use a different metric spec")
    if (
        ground_truth.get("groundTruthStatus")
        != "USER_CONFIRMED_HELD_OUT_GROUND_TRUTH"
        or ground_truth.get("predictionsVisibleDuringReview") is not False
        or not ground_truth.get("confirmedAt")
    ):
        raise ValueError("Ground Truth confirmation evidence is incomplete")

    prediction_cases = {
        str(case["caseId"]): case for case in sealed.get("cases", [])
    }
    truth_cases = {
        str(case["caseId"]): case for case in ground_truth.get("cases", [])
    }
    if prediction_cases.keys() != truth_cases.keys():
        raise ValueError("Ground Truth and prediction case IDs do not match")
    if sealed.get("datasetDigest") != ground_truth.get("datasetDigest"):
        raise ValueError("Ground Truth and predictions use different datasets")

    profile_metrics: dict[str, dict[str, Any]] = {}
    for profile in REQUIRED_PROFILES:
        pairs = [
            (
                str(truth_cases[case_id]["groundTruth"]),
                str(prediction_cases[case_id]["predictions"][profile].get("text", "")),
            )
            for case_id in prediction_cases
        ]
        profile_metrics[profile] = _metric_payload(pairs)

    selected_pairs: list[tuple[str, str]] = []
    baseline_losses = 0
    baseline_recoveries = 0
    switch_count = 0
    reason_counts: dict[str, int] = {}
    for case_id, case in prediction_cases.items():
        reference = str(truth_cases[case_id]["groundTruth"])
        primary = str(case["predictions"][PRIMARY].get("text", ""))
        selected, reason = fixed_policy_prediction(case)
        selected_pairs.append((reference, selected))
        normalized_reference = normalize_for_evaluation(reference)
        normalized_primary = normalize_for_evaluation(primary)
        normalized_selected = normalize_for_evaluation(selected)
        switched = normalize_for_agreement(selected) != normalize_for_agreement(
            primary
        )
        switch_count += int(switched)
        baseline_losses += int(
            switched
            and normalized_primary == normalized_reference
            and normalized_selected != normalized_reference
        )
        baseline_recoveries += int(
            switched
            and normalized_primary != normalized_reference
            and normalized_selected == normalized_reference
        )
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    selected_metrics = _metric_payload(selected_pairs)
    baseline_metrics = profile_metrics[PRIMARY]
    zero_loss = baseline_losses == 0
    no_exact_regression = (
        selected_metrics["exactMatchRate"]
        >= baseline_metrics["exactMatchRate"]
    )
    no_der_regression = (
        selected_metrics["diacriticErrorRate"]
        <= baseline_metrics["diacriticErrorRate"]
    )
    controlled_pilot_eligible = zero_loss and no_exact_regression and no_der_regression

    return {
        "schemaVersion": "phase14.6-heldout-evaluation/1.0.0",
        "evaluatedAt": utc_now(),
        "containsRealPII": False,
        "evaluationRunCount": 1,
        "thresholdRetuned": False,
        "predictionsWereHidden": True,
        "metricSpecVersion": METRIC_SPEC_VERSION,
        "policy": PHASE14_6_SHADOW_POLICY.manifest(),
        "lockFileSha256": sealed["lockFileSha256"],
        "sealedPredictionsSha256": f"sha256:{sealed_digest}",
        "groundTruthSha256": f"sha256:{ground_truth_digest}",
        "documentCount": sealed["documentCount"],
        "lineCount": sealed["lineCount"],
        "profiles": profile_metrics,
        "fixedPolicyReplay": {
            "metrics": selected_metrics,
            "switchCount": switch_count,
            "baselineErrorsRecovered": baseline_recoveries,
            "baselineCorrectLost": baseline_losses,
            "selectionReasons": dict(sorted(reason_counts.items())),
        },
        "decision": {
            "controlledPilot": (
                "ELIGIBLE_FOR_CONTROLLED_PILOT"
                if controlled_pilot_eligible
                else "NOT_PROMOTED"
            ),
            "production": "NOT_PRODUCTION_READY",
            "zeroBaselineCorrectLoss": zero_loss,
            "noExactRegression": no_exact_regression,
            "noDiacriticErrorRegression": no_der_regression,
        },
    }


def _metric_payload(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    metrics = evaluate_text_pairs(pairs)
    return {
        "lineCount": metrics.case_count,
        "exactMatchCount": metrics.strict_exact_count,
        "exactMatchRate": metrics.strict_exact_rate,
        "casefoldExactMatchRate": metrics.casefold_exact_rate,
        "cer": metrics.character_error_rate,
        "wer": metrics.word_error_rate,
        "diacriticErrorRate": metrics.diacritic_error_rate,
    }


def _safe_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def atomic_write_new(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(
            "Phase 14.6 artifact already exists; held-out evaluation is single-run"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path("config/phase14_6_benchmark_lock.json"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    seal = subparsers.add_parser("seal")
    seal.add_argument("--predictions", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--sealed-predictions", type=Path, required=True)
    evaluate.add_argument("--ground-truth", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lock = load_and_validate_lock(args.lock)
    lock_digest = sha256_file(args.lock)
    if args.command == "seal":
        source_bytes = args.predictions.read_bytes()
        payload = seal_predictions(
            json.loads(source_bytes),
            lock,
            lock_digest=lock_digest,
            source_digest=hashlib.sha256(source_bytes).hexdigest(),
        )
        atomic_write_new(args.output, payload)
        print(
            f"Hidden predictions sealed: {payload['documentCount']} documents, "
            f"{payload['lineCount']} lines"
        )
        return 0

    sealed_bytes = args.sealed_predictions.read_bytes()
    truth_bytes = args.ground_truth.read_bytes()
    payload = evaluate_once(
        json.loads(sealed_bytes),
        json.loads(truth_bytes),
        lock,
        sealed_digest=hashlib.sha256(sealed_bytes).hexdigest(),
        ground_truth_digest=hashlib.sha256(truth_bytes).hexdigest(),
    )
    atomic_write_new(args.output, payload)
    print(
        f"Held-out evaluation complete: {payload['documentCount']} documents, "
        f"{payload['lineCount']} lines, {payload['decision']['controlledPilot']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
