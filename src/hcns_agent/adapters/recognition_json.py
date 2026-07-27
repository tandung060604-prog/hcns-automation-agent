"""JSON boundary for private recognition inputs and aggregate-only reports."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

from hcns_agent.domain.recognition import (
    CharsetAuditReport,
    RecognitionGroundTruth,
    RecognitionGroundTruthCase,
    RecognitionPredictionCase,
    RecognitionReport,
    RecognitionSubmission,
)


class RecognitionJsonError(ValueError):
    """Raised for invalid recognition benchmark JSON."""


def load_recognition_characters(path: Path) -> str:
    """Load a plain dictionary or Paddle inference YAML character list."""
    if path.suffix.lower() not in {".yml", ".yaml"}:
        try:
            return path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise RecognitionJsonError(f"Cannot read dictionary {path.name}: {exc}") from exc
    try:
        yaml = import_module("yaml")
        payload = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        characters = payload["PostProcess"]["character_dict"]
    except (ImportError, OSError, KeyError, TypeError, ValueError) as exc:
        raise RecognitionJsonError(
            f"Cannot read Paddle character_dict from {path.name}: {exc}"
        ) from exc
    if not isinstance(characters, list) or not all(
        isinstance(character, str) for character in characters
    ):
        raise RecognitionJsonError("Paddle character_dict must be an array of strings")
    return "".join(characters)


def load_recognition_ground_truth(path: Path) -> RecognitionGroundTruth:
    payload = _load_object(path)
    try:
        cases = tuple(
            RecognitionGroundTruthCase(
                case_id=_string(case, "caseId"),
                text=_string(case, "text"),
            )
            for case in _object_list(payload, "cases")
        )
        return RecognitionGroundTruth(
            dataset_id=_string(payload, "datasetId"),
            dataset_version=_string(payload, "datasetVersion"),
            content_digest=_string(payload, "contentDigest"),
            authorized_for_local_evaluation=_boolean(
                payload,
                "authorizedForLocalEvaluation",
            ),
            cases=cases,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RecognitionJsonError(f"Invalid recognition Ground Truth: {exc}") from exc


def load_recognition_submission(path: Path) -> RecognitionSubmission:
    payload = _load_object(path)
    try:
        cases = tuple(
            RecognitionPredictionCase(
                case_id=_string(case, "caseId"),
                text=_string(case, "text", allow_empty=True),
                confidence=_number(case, "confidence"),
                duration_ms=_number(case, "durationMs"),
            )
            for case in _object_list(payload, "cases")
        )
        return RecognitionSubmission(
            dataset_id=_string(payload, "datasetId"),
            dataset_version=_string(payload, "datasetVersion"),
            backend_name=_string(payload, "backendName"),
            backend_version=_string(payload, "backendVersion"),
            model_identifier=_string(payload, "modelIdentifier"),
            cases=cases,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RecognitionJsonError(f"Invalid recognition submission: {exc}") from exc


def write_recognition_report(
    path: Path,
    report: RecognitionReport,
    *,
    overwrite: bool = False,
) -> None:
    metrics = report.metrics
    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "datasetId": report.dataset_id,
        "datasetVersion": report.dataset_version,
        "datasetContentDigest": report.dataset_content_digest,
        "backendName": report.backend_name,
        "backendVersion": report.backend_version,
        "modelIdentifier": report.model_identifier,
        "metrics": {
            "caseCount": metrics.case_count,
            "exactMatchCount": metrics.exact_match_count,
            "exactMatchRate": metrics.exact_match_rate,
            "referenceCharacterCount": metrics.reference_character_count,
            "characterErrorCount": metrics.character_error_count,
            "characterErrorRate": metrics.character_error_rate,
            "referenceWordCount": metrics.reference_word_count,
            "wordErrorCount": metrics.word_error_count,
            "wordErrorRate": metrics.word_error_rate,
            "referenceDiacriticCount": metrics.reference_diacritic_count,
            "diacriticErrorCount": metrics.diacritic_error_count,
            "diacriticErrorRate": metrics.diacritic_error_rate,
            "predictionNfcViolationCount": metrics.prediction_nfc_violation_count,
            "acceptedCount": metrics.accepted_count,
            "acceptedExactCount": metrics.accepted_exact_count,
            "acceptedPrecision": metrics.accepted_precision,
            "confidenceThreshold": metrics.confidence_threshold,
            "latencyP50Ms": metrics.latency_p50_ms,
            "latencyP95Ms": metrics.latency_p95_ms,
        },
    }
    _write_object(path, payload, overwrite=overwrite)


def write_charset_audit(
    path: Path,
    report: CharsetAuditReport,
    *,
    overwrite: bool = False,
) -> None:
    _write_object(
        path,
        {
            "schemaVersion": "1.0.0",
            "modelIdentifier": report.model_identifier,
            "requiredCharacterCount": report.required_character_count,
            "presentCharacterCount": report.present_character_count,
            "missingCharacterCount": report.missing_character_count,
            "coverage": report.coverage,
            "missingCharacters": list(report.missing_characters),
        },
        overwrite=overwrite,
    )


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecognitionJsonError(f"Cannot read JSON {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RecognitionJsonError(f"{path.name} must contain a JSON object")
    return payload


def _write_object(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RecognitionJsonError(f"Output already exists: {path.name}; use --overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _string(payload: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = payload[key]
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise TypeError(f"{key} must be a string")
    return value


def _boolean(payload: dict[str, Any], key: str) -> bool:
    value = payload[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value


def _number(payload: dict[str, Any], key: str) -> float:
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be a number")
    return float(value)


def _object_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload[key]
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypeError(f"{key} must be an array of objects")
    return value
