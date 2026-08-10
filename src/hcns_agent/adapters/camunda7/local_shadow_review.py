"""Projection-only M5 shadow review for an existing local prediction inventory.

The review path intentionally stops at the Camunda boundary. It reads only
document metadata, creates deterministic opaque references and scalar process
variables, and never starts a process or performs a side effect.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from hcns_agent.adapters.camunda7.contract import (
    PROCESS_VARIABLE_WHITELIST,
    ProcessVariables,
    validate_process_variables,
)

_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_CATEGORY_TO_WORKFLOW = {
    "contract": "EMPLOYMENT_CONTRACT",
    "cv": "CV",
    "ielts": "CERTIFICATE",
}
_UNSUPPORTED_FORMATS = frozenset({"PLAIN_TEXT", "PPTX"})
_SCAN_FORMATS = frozenset({"IMAGE", "PDF_SCAN"})
_SCALAR_TYPES = (str, int, float, bool, type(None))
_REPORT_KEYS = (
    "milestone",
    "evaluationKind",
    "mode",
    "passed",
    "datasetDigest",
    "documentCount",
    "categoryCounts",
    "sourceFormatCounts",
    "manualReviewCount",
    "scanManualReviewCount",
    "unsupportedManualReviewCount",
    "idempotencyMismatchCount",
    "duplicateReferenceCount",
    "rawExposureCount",
    "autoContinueCount",
    "camundaProcessStartAttempts",
    "realSideEffectCount",
    "groundTruthUsed",
    "evaluateOnceArtifactTouched",
    "containsRawFieldValues",
    "promotionAllowed",
)


class LocalShadowReviewError(ValueError):
    """The private projection cannot be safely used for shadow review."""


@dataclass(frozen=True, slots=True)
class ShadowReviewProjection:
    workflow_document_type: str
    source_format: str
    document_reference: str
    result_reference: str
    idempotency_key: str
    variables: ProcessVariables


@dataclass(frozen=True, slots=True)
class LocalShadowReviewReport:
    dataset_digest: str
    document_count: int
    category_counts: dict[str, int]
    source_format_counts: dict[str, int]
    manual_review_count: int
    scan_manual_review_count: int
    unsupported_manual_review_count: int
    idempotency_mismatch_count: int
    duplicate_reference_count: int
    raw_exposure_count: int
    auto_continue_count: int
    camunda_process_start_attempts: int
    real_side_effect_count: int
    ground_truth_used: bool
    evaluate_once_artifact_touched: bool

    @property
    def passed(self) -> bool:
        return (
            self.document_count > 0
            and self.manual_review_count == self.document_count
            and self.idempotency_mismatch_count == 0
            and self.duplicate_reference_count == 0
            and self.raw_exposure_count == 0
            and self.auto_continue_count == 0
            and self.camunda_process_start_attempts == 0
            and self.real_side_effect_count == 0
            and not self.ground_truth_used
            and not self.evaluate_once_artifact_touched
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "milestone": "M5-CAM-001D",
            "evaluationKind": "m5-local-shadow-review-only",
            "mode": "LOCAL_SHADOW_REVIEW_ONLY",
            "passed": self.passed,
            "datasetDigest": self.dataset_digest,
            "documentCount": self.document_count,
            "categoryCounts": self.category_counts,
            "sourceFormatCounts": self.source_format_counts,
            "manualReviewCount": self.manual_review_count,
            "scanManualReviewCount": self.scan_manual_review_count,
            "unsupportedManualReviewCount": self.unsupported_manual_review_count,
            "idempotencyMismatchCount": self.idempotency_mismatch_count,
            "duplicateReferenceCount": self.duplicate_reference_count,
            "rawExposureCount": self.raw_exposure_count,
            "autoContinueCount": self.auto_continue_count,
            "camundaProcessStartAttempts": self.camunda_process_start_attempts,
            "realSideEffectCount": self.real_side_effect_count,
            "groundTruthUsed": self.ground_truth_used,
            "evaluateOnceArtifactTouched": self.evaluate_once_artifact_touched,
            "containsRawFieldValues": False,
            "promotionAllowed": False,
        }


def project_local_prediction_record(
    record: Mapping[str, object],
    *,
    dataset_digest: str,
) -> ShadowReviewProjection:
    """Project metadata from one private prediction record into safe scalars."""

    case_id = _opaque(record.get("caseId"), "caseId")
    category = record.get("category")
    if not isinstance(category, str) or category not in _CATEGORY_TO_WORKFLOW:
        raise LocalShadowReviewError("unsupported local prediction category")
    source_format = record.get("sourceFormat")
    if not isinstance(source_format, str) or not source_format.strip():
        raise LocalShadowReviewError("prediction source format is missing")
    workflow_type = _CATEGORY_TO_WORKFLOW[category]
    digest = sha256(
        f"{dataset_digest}:{case_id}:{category}:{source_format}".encode()
    ).hexdigest()
    document_reference = f"m5d-doc-{digest[:24]}"
    result_reference = f"m5d-result-{digest}"
    idempotency_key = f"m5d-idem-{digest[:32]}"
    predicted_category = record.get("predictedCategory")
    classification_status = "CONFIRMED" if predicted_category == category else "UNKNOWN"
    variables: ProcessVariables = {
        "applicationId": f"m5d-app-{digest[:24]}",
        "documentReference": document_reference,
        "declaredDocumentType": workflow_type,
        "workflowDocumentType": workflow_type,
        "resultReference": result_reference,
        "sourceFormat": source_format,
        "classificationStatus": classification_status,
        "classificationConfidence": 0.0,
        "parseStatus": "NOT_RUN",
        "qualityStatus": "REVIEW_REQUIRED",
        "reviewRequired": True,
        "sensitiveFieldNeedsReview": True,
        "missingCriticalField": True,
        "businessInconsistency": False,
        "requiredFieldsComplete": False,
        "overallConfidence": 0.0,
        "autoContinueEnabled": False,
        "recommendedAction": "MANUAL_REVIEW",
        "reviewStage": "MANUAL_REVIEW",
        "processingOutcome": "SHADOW_REVIEW_ONLY",
        "idempotencyKey": idempotency_key,
    }
    validate_process_variables(variables)
    if any(not isinstance(value, _SCALAR_TYPES) for value in variables.values()):
        raise LocalShadowReviewError("shadow projection contains a non-scalar value")
    if set(variables) - PROCESS_VARIABLE_WHITELIST:
        raise LocalShadowReviewError("shadow projection contains an unexpected variable")
    return ShadowReviewProjection(
        workflow_document_type=workflow_type,
        source_format=source_format,
        document_reference=document_reference,
        result_reference=result_reference,
        idempotency_key=idempotency_key,
        variables=variables,
    )


def run_local_shadow_review(payload: Mapping[str, object]) -> LocalShadowReviewReport:
    """Validate an existing prediction projection without opening Camunda."""

    if payload.get("localOnly") is not True:
        raise LocalShadowReviewError("local-only projection is required")
    dataset_digest = payload.get("datasetDigest")
    if not isinstance(dataset_digest, str) or not dataset_digest.strip():
        raise LocalShadowReviewError("dataset digest is missing")
    review_projection = payload.get("reviewProjection")
    if not isinstance(review_projection, Mapping):
        raise LocalShadowReviewError("review projection metadata is missing")
    ground_truth_used = review_projection.get("groundTruthUsed") is True
    evaluate_once_touched = review_projection.get("evaluateOnceArtifactTouched") is True
    if ground_truth_used or evaluate_once_touched:
        raise LocalShadowReviewError("GroundTruth/evaluate-once access is forbidden")
    records = payload.get("documents")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise LocalShadowReviewError("prediction documents are missing")

    projections: list[ShadowReviewProjection] = []
    case_ids: set[str] = set()
    category_counts: Counter[str] = Counter()
    source_format_counts: Counter[str] = Counter()
    for record in records:
        if not isinstance(record, Mapping):
            raise LocalShadowReviewError("prediction record is invalid")
        case_id = _opaque(record.get("caseId"), "caseId")
        if case_id in case_ids:
            raise LocalShadowReviewError("duplicate prediction caseId")
        case_ids.add(case_id)
        projection = project_local_prediction_record(record, dataset_digest=dataset_digest)
        projections.append(projection)
        category_counts[projection.workflow_document_type] += 1
        source_format_counts[projection.source_format] += 1

    replayed = [
        project_local_prediction_record(record, dataset_digest=dataset_digest)
        for record in records
        if isinstance(record, Mapping)
    ]
    idempotency_mismatch_count = sum(
        first != second for first, second in zip(projections, replayed, strict=True)
    )
    references = [projection.document_reference for projection in projections]
    duplicate_reference_count = len(references) - len(set(references))
    scan_count = sum(
        count
        for source_format, count in source_format_counts.items()
        if source_format in _SCAN_FORMATS
    )
    unsupported_count = sum(
        count
        for source_format, count in source_format_counts.items()
        if source_format in _UNSUPPORTED_FORMATS
    )
    return LocalShadowReviewReport(
        dataset_digest=dataset_digest,
        document_count=len(projections),
        category_counts=dict(sorted(category_counts.items())),
        source_format_counts=dict(sorted(source_format_counts.items())),
        manual_review_count=len(projections),
        scan_manual_review_count=scan_count,
        unsupported_manual_review_count=unsupported_count,
        idempotency_mismatch_count=idempotency_mismatch_count,
        duplicate_reference_count=duplicate_reference_count,
        raw_exposure_count=0,
        auto_continue_count=0,
        camunda_process_start_attempts=0,
        real_side_effect_count=0,
        ground_truth_used=ground_truth_used,
        evaluate_once_artifact_touched=evaluate_once_touched,
    )


def load_projection(path: str) -> dict[str, Any]:
    """Read one private JSON projection; callers must keep it outside Git."""

    with open(path, encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise LocalShadowReviewError("projection root must be an object")
    return payload


def load_shadow_review_report(path: str) -> dict[str, object]:
    """Read and whitelist one aggregate-only shadow report for local UI."""

    with open(path, encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise LocalShadowReviewError("shadow report root must be an object")
    if payload.get("evaluationKind") != "m5-local-shadow-review-only":
        raise LocalShadowReviewError("unexpected shadow report kind")
    if payload.get("containsRawFieldValues") is not False:
        raise LocalShadowReviewError("shadow report is not aggregate-only")
    return {key: payload[key] for key in _REPORT_KEYS if key in payload}


def _opaque(value: object, name: str) -> str:
    if not isinstance(value, str) or _OPAQUE_ID.fullmatch(value) is None:
        raise LocalShadowReviewError(f"{name} must be an opaque identifier")
    return value
