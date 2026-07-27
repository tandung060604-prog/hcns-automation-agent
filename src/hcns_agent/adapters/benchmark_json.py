"""Strict JSON boundary for benchmark inputs and aggregate-only outputs."""

from __future__ import annotations

import json
from datetime import date
from enum import Enum
from pathlib import Path
from typing import TypeAlias, TypeVar, cast

from hcns_agent.domain.canonical import ScalarValue
from hcns_agent.domain.documents import DocumentType
from hcns_agent.domain.evaluation import (
    BenchmarkReport,
    BenchmarkSubmission,
    DataClassification,
    DatasetAuthorizationStatus,
    DatasetManifest,
    ExpectedField,
    GroundTruthCase,
    PredictedField,
    PredictionCase,
    PromotionDecision,
    StorageProtection,
)
from hcns_agent.domain.models import FieldStatus
from hcns_agent.domain.understanding import QualityStatus

JsonObject: TypeAlias = dict[str, object]
EnumT = TypeVar("EnumT", bound=Enum)


class BenchmarkJsonError(ValueError):
    """Raised for invalid benchmark JSON without echoing sensitive values."""


def load_ground_truth(path: Path) -> tuple[DatasetManifest, tuple[GroundTruthCase, ...]]:
    payload = _read_object(path)
    _only_keys(payload, {"schemaVersion", "manifest", "cases"}, "ground truth root")
    _require_schema_version(payload)
    manifest = _parse_manifest(_object(payload, "manifest"))
    cases = tuple(_parse_ground_truth_case(item) for item in _object_list(payload, "cases"))
    return manifest, cases


def load_submission(path: Path) -> BenchmarkSubmission:
    payload = _read_object(path)
    _only_keys(
        payload,
        {
            "schemaVersion",
            "datasetId",
            "datasetVersion",
            "backendName",
            "backendVersion",
            "modelIdentifiers",
            "cases",
        },
        "prediction root",
    )
    _require_schema_version(payload)
    return BenchmarkSubmission(
        dataset_id=_string(payload, "datasetId"),
        dataset_version=_string(payload, "datasetVersion"),
        backend_name=_string(payload, "backendName"),
        backend_version=_string(payload, "backendVersion"),
        model_identifiers=tuple(
            _string_item(item, "modelIdentifiers")
            for item in _list(payload, "modelIdentifiers")
        ),
        cases=tuple(_parse_prediction_case(item) for item in _object_list(payload, "cases")),
    )


def write_submission(path: Path, submission: BenchmarkSubmission) -> None:
    _write_object(
        path,
        {
            "schemaVersion": "1.0.0",
            "datasetId": submission.dataset_id,
            "datasetVersion": submission.dataset_version,
            "backendName": submission.backend_name,
            "backendVersion": submission.backend_version,
            "modelIdentifiers": list(submission.model_identifiers),
            "cases": [
                {
                    "caseId": case.case_id,
                    "documentType": case.document_type.value,
                    "fields": [
                        {
                            "name": field.name,
                            "value": field.value,
                            "status": field.status.value,
                            "sensitive": field.sensitive,
                        }
                        for field in case.fields
                    ],
                    "qualityStatus": case.quality_status.value,
                    "reviewRequired": case.review_required,
                    "latencyMs": case.latency_ms,
                    "failureCode": case.failure_code,
                    "ocrLines": list(case.ocr_lines),
                }
                for case in submission.cases
            ],
        },
    )


def write_report(path: Path, report: BenchmarkReport) -> None:
    _write_object(path, report_to_dict(report))


def write_promotion_decision(path: Path, decision: PromotionDecision) -> None:
    _write_object(
        path,
        {
            "schemaVersion": "1.0.0",
            "status": decision.status.value,
            "checks": [
                {
                    "code": check.code,
                    "passed": check.passed,
                    "message": check.message,
                }
                for check in decision.checks
            ],
        },
    )


def write_comparison(
    path: Path,
    baseline: BenchmarkReport,
    challenger: BenchmarkReport,
    decision: PromotionDecision,
) -> None:
    _write_object(
        path,
        {
            "schemaVersion": "1.0.0",
            "baseline": report_to_dict(baseline),
            "challenger": report_to_dict(challenger),
            "promotionDecision": {
                "status": decision.status.value,
                "checks": [
                    {
                        "code": check.code,
                        "passed": check.passed,
                        "message": check.message,
                    }
                    for check in decision.checks
                ],
            },
        },
    )


def report_to_dict(report: BenchmarkReport) -> JsonObject:
    """Project metrics only; raw expected/predicted values are intentionally absent."""
    return {
        "schemaVersion": "1.0.0",
        "dataset": {
            "id": report.dataset_id,
            "version": report.dataset_version,
            "contentDigest": report.dataset_content_digest,
            "caseCount": report.case_count,
        },
        "backend": {
            "name": report.backend_name,
            "version": report.backend_version,
            "modelIdentifiers": list(report.model_identifiers),
        },
        "classification": {
            "macroPrecision": report.classification.macro_precision,
            "macroRecall": report.classification.macro_recall,
            "macroF1": report.classification.macro_f1,
            "unknownRate": report.classification.unknown_rate,
            "perType": [
                {
                    "documentType": metric.document_type.value,
                    "support": metric.support,
                    "predicted": metric.predicted,
                    "truePositive": metric.true_positive,
                    "precision": metric.precision,
                    "recall": metric.recall,
                    "f1": metric.f1,
                }
                for metric in report.classification.per_type
            ],
        },
        "ocr": {
            "evaluatedCases": report.ocr.evaluated_cases,
            "referenceCharacterCount": report.ocr.reference_character_count,
            "characterErrorCount": report.ocr.character_error_count,
            "characterErrorRate": report.ocr.character_error_rate,
            "referenceWordCount": report.ocr.reference_word_count,
            "wordErrorCount": report.ocr.word_error_count,
            "wordErrorRate": report.ocr.word_error_rate,
            "readingOrderExactCount": report.ocr.reading_order_exact_count,
            "readingOrderAccuracy": report.ocr.reading_order_accuracy,
        },
        "extraction": {
            "expectedCount": report.extraction.expected_count,
            "predictedCount": report.extraction.predicted_count,
            "exactMatchCount": report.extraction.exact_match_count,
            "notFoundCount": report.extraction.not_found_count,
            "exactMatchRate": report.extraction.exact_match_rate,
            "precision": report.extraction.precision,
            "recall": report.extraction.recall,
            "notFoundRate": report.extraction.not_found_rate,
            "perField": [
                {
                    "documentType": metric.document_type.value,
                    "fieldName": metric.field_name,
                    "expectedCount": metric.expected_count,
                    "predictedCount": metric.predicted_count,
                    "exactMatchCount": metric.exact_match_count,
                    "notFoundCount": metric.not_found_count,
                    "exactMatchRate": metric.exact_match_rate,
                    "precision": metric.precision,
                    "recall": metric.recall,
                }
                for metric in report.extraction.per_field
            ],
        },
        "quality": {
            "totalCases": report.quality.total_cases,
            "falsePassCount": report.quality.false_pass_count,
            "falsePassRate": report.quality.false_pass_rate,
            "falseRejectCount": report.quality.false_reject_count,
            "falseRejectRate": report.quality.false_reject_rate,
            "reviewRequiredCount": report.quality.review_required_count,
            "reviewRate": report.quality.review_rate,
            "reviewPrecision": report.quality.review_precision,
            "sensitiveFieldCount": report.quality.sensitive_field_count,
            "sensitiveFalseAcceptanceCount": (
                report.quality.sensitive_false_acceptance_count
            ),
            "sensitiveFalseAcceptanceRate": report.quality.sensitive_false_acceptance_rate,
        },
        "system": {
            "latencyP50Ms": report.system.latency_p50_ms,
            "latencyP95Ms": report.system.latency_p95_ms,
            "failureCount": report.system.failure_count,
            "failureRate": report.system.failure_rate,
        },
    }


def _parse_manifest(payload: JsonObject) -> DatasetManifest:
    _only_keys(
        payload,
        {
            "datasetId",
            "version",
            "contentDigest",
            "purpose",
            "rightsBasis",
            "dataOwner",
            "approvedBy",
            "approvalReference",
            "approvedAt",
            "retentionUntil",
            "authorizationStatus",
            "storageProtection",
            "dataClassification",
            "documentCount",
            "pageCount",
        },
        "manifest",
    )
    return DatasetManifest(
        dataset_id=_string(payload, "datasetId"),
        version=_string(payload, "version"),
        content_digest=_string(payload, "contentDigest"),
        purpose=_string(payload, "purpose"),
        rights_basis=_string(payload, "rightsBasis"),
        data_owner=_string(payload, "dataOwner"),
        approved_by=_string(payload, "approvedBy"),
        approval_reference=_string(payload, "approvalReference"),
        approved_at=_date(payload, "approvedAt"),
        retention_until=_date(payload, "retentionUntil"),
        authorization_status=_enum(
            DatasetAuthorizationStatus,
            _string(payload, "authorizationStatus"),
            "authorizationStatus",
        ),
        storage_protection=_enum(
            StorageProtection,
            _string(payload, "storageProtection"),
            "storageProtection",
        ),
        data_classification=_enum(
            DataClassification, _string(payload, "dataClassification"), "dataClassification"
        ),
        document_count=_integer(payload, "documentCount"),
        page_count=_integer(payload, "pageCount"),
    )


def _parse_ground_truth_case(payload: JsonObject) -> GroundTruthCase:
    _only_keys(
        payload,
        {
            "caseId",
            "sourceRelativePath",
            "sourceSha256",
            "pageCount",
            "documentType",
            "fields",
            "expectedQualityStatus",
            "reviewRequired",
            "ocrLines",
        },
        "ground truth case",
    )
    return GroundTruthCase(
        case_id=_string(payload, "caseId"),
        source_relative_path=_string(payload, "sourceRelativePath"),
        source_sha256=_string(payload, "sourceSha256"),
        page_count=_integer(payload, "pageCount"),
        document_type=_enum(
            DocumentType, _string(payload, "documentType"), "documentType"
        ),
        fields=tuple(_parse_expected_field(item) for item in _object_list(payload, "fields")),
        expected_quality_status=_enum(
            QualityStatus,
            _string(payload, "expectedQualityStatus"),
            "expectedQualityStatus",
        ),
        review_required=_boolean(payload, "reviewRequired"),
        ocr_lines=_optional_string_tuple(payload, "ocrLines"),
    )


def _parse_expected_field(payload: JsonObject) -> ExpectedField:
    _only_keys(payload, {"name", "value", "sensitive"}, "expected field")
    return ExpectedField(
        name=_string(payload, "name"),
        value=_scalar(payload, "value"),
        sensitive=_boolean(payload, "sensitive"),
    )


def _parse_prediction_case(payload: JsonObject) -> PredictionCase:
    _only_keys(
        payload,
        {
            "caseId",
            "documentType",
            "fields",
            "qualityStatus",
            "reviewRequired",
            "latencyMs",
            "failureCode",
            "ocrLines",
        },
        "prediction case",
    )
    failure_value = payload.get("failureCode")
    if failure_value is not None and not isinstance(failure_value, str):
        raise BenchmarkJsonError("failureCode must be a string or null")
    return PredictionCase(
        case_id=_string(payload, "caseId"),
        document_type=_enum(
            DocumentType, _string(payload, "documentType"), "documentType"
        ),
        fields=tuple(_parse_predicted_field(item) for item in _object_list(payload, "fields")),
        quality_status=_enum(
            QualityStatus, _string(payload, "qualityStatus"), "qualityStatus"
        ),
        review_required=_boolean(payload, "reviewRequired"),
        latency_ms=_number(payload, "latencyMs"),
        failure_code=failure_value,
        ocr_lines=_optional_string_tuple(payload, "ocrLines"),
    )


def _parse_predicted_field(payload: JsonObject) -> PredictedField:
    _only_keys(
        payload,
        {"name", "value", "status", "sensitive"},
        "predicted field",
    )
    return PredictedField(
        name=_string(payload, "name"),
        value=_scalar(payload, "value"),
        status=_enum(FieldStatus, _string(payload, "status"), "status"),
        sensitive=_boolean(payload, "sensitive"),
    )


def _read_object(path: Path) -> JsonObject:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkJsonError(f"Could not read valid benchmark JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise BenchmarkJsonError("Benchmark JSON root must be an object")
    return cast(JsonObject, payload)


def _write_object(path: Path, payload: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _require_schema_version(payload: JsonObject) -> None:
    if _string(payload, "schemaVersion") != "1.0.0":
        raise BenchmarkJsonError("Unsupported benchmark schemaVersion")


def _only_keys(payload: JsonObject, allowed: set[str], context: str) -> None:
    unexpected = sorted(set(payload) - allowed)
    if unexpected:
        raise BenchmarkJsonError(f"{context} contains unsupported properties")


def _object(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise BenchmarkJsonError(f"{key} must be an object")
    return cast(JsonObject, value)


def _list(payload: JsonObject, key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise BenchmarkJsonError(f"{key} must be an array")
    return value


def _object_list(payload: JsonObject, key: str) -> tuple[JsonObject, ...]:
    result: list[JsonObject] = []
    for item in _list(payload, key):
        if not isinstance(item, dict):
            raise BenchmarkJsonError(f"{key} must contain objects")
        result.append(cast(JsonObject, item))
    return tuple(result)


def _string(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkJsonError(f"{key} must be a non-empty string")
    return value


def _string_item(value: object, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkJsonError(f"{key} must contain non-empty strings")
    return value


def _optional_string_tuple(payload: JsonObject, key: str) -> tuple[str, ...]:
    if key not in payload:
        return ()
    return tuple(_string_item(item, key) for item in _list(payload, key))


def _boolean(payload: JsonObject, key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise BenchmarkJsonError(f"{key} must be a boolean")
    return value


def _integer(payload: JsonObject, key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BenchmarkJsonError(f"{key} must be an integer")
    return value


def _number(payload: JsonObject, key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise BenchmarkJsonError(f"{key} must be a number")
    return float(value)


def _scalar(payload: JsonObject, key: str) -> ScalarValue:
    value = payload.get(key)
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise BenchmarkJsonError(f"{key} must be a scalar value")
    return value


def _date(payload: JsonObject, key: str) -> date:
    value = _string(payload, key)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BenchmarkJsonError(f"{key} must be an ISO date") from exc


def _enum(enum_type: type[EnumT], value: str, key: str) -> EnumT:
    try:
        return enum_type(value)
    except ValueError as exc:
        raise BenchmarkJsonError(f"{key} contains an unsupported enum value") from exc
