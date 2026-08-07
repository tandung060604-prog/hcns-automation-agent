"""Sanitized process-variable and DMN contracts for Camunda Platform 7."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from hcns_agent.domain.documents import DocumentType
from hcns_agent.domain.models import FieldStatus
from hcns_agent.domain.understanding import IdpResult, QualityStatus

ProcessValue: TypeAlias = str | int | float | bool | None
ProcessVariables: TypeAlias = dict[str, ProcessValue]


class CamundaWorkflowDocumentType(str, Enum):
    IDENTITY_DOCUMENT = "IDENTITY_DOCUMENT"
    EMPLOYEE_INFORMATION_FORM = "EMPLOYEE_INFORMATION_FORM"
    CV = "CV"
    DEGREE = "DEGREE"
    CERTIFICATE = "CERTIFICATE"
    EMPLOYMENT_CONTRACT = "EMPLOYMENT_CONTRACT"
    HR_DECISION = "HR_DECISION"
    LEAVE_REQUEST = "LEAVE_REQUEST"
    OVERTIME_REQUEST = "OVERTIME_REQUEST"
    HANDOVER_RECORD = "HANDOVER_RECORD"
    OTHER_HR_DOCUMENT = "OTHER_HR_DOCUMENT"


class CamundaQualityAction(str, Enum):
    AUTO_CONTINUE = "AUTO_CONTINUE"
    USER_REVIEW = "USER_REVIEW"
    HR_REVIEW = "HR_REVIEW"
    REQUEST_REUPLOAD = "REQUEST_REUPLOAD"


M4_CLOSED_SET_WORKFLOW_DOCUMENT_TYPES = frozenset(
    {
        CamundaWorkflowDocumentType.IDENTITY_DOCUMENT.value,
        CamundaWorkflowDocumentType.CV.value,
        CamundaWorkflowDocumentType.CERTIFICATE.value,
        CamundaWorkflowDocumentType.EMPLOYMENT_CONTRACT.value,
        CamundaWorkflowDocumentType.LEAVE_REQUEST.value,
        CamundaWorkflowDocumentType.OVERTIME_REQUEST.value,
    }
)

# M5 keeps the same six-value Camunda contract while adding four frozen templates.
M5_CLOSED_SET_WORKFLOW_DOCUMENT_TYPES = M4_CLOSED_SET_WORKFLOW_DOCUMENT_TYPES

DMN_QUALITY_INPUT_VARIABLES = frozenset(
    {
        "qualityStatus",
        "reviewRequired",
        "sensitiveFieldNeedsReview",
        "missingCriticalField",
        "businessInconsistency",
        "requiredFieldsComplete",
        "overallConfidence",
        "autoContinueEnabled",
    }
)


@dataclass(frozen=True, slots=True)
class CamundaRolloutPolicy:
    policy_id: str
    version: str
    mode: str
    auto_continue_enabled: bool
    real_side_effects_enabled: bool

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("Camunda rollout policy id and version are required")
        if self.mode == "SHADOW" and (
            self.auto_continue_enabled or self.real_side_effects_enabled
        ):
            raise ValueError("Shadow policy cannot enable automation or real side effects")


M4_SHADOW_POLICY = CamundaRolloutPolicy(
    policy_id="camunda-m4-shadow",
    version="1.0.0",
    mode="SHADOW",
    auto_continue_enabled=False,
    real_side_effects_enabled=False,
)

M5_SHADOW_POLICY = CamundaRolloutPolicy(
    policy_id="camunda-m5-shadow",
    version="1.0.0",
    mode="SHADOW",
    auto_continue_enabled=False,
    real_side_effects_enabled=False,
)


PROCESS_VARIABLE_WHITELIST = frozenset(
    {
        "applicationId",
        "documentType",
        "documentSourcePath",
        "documentReference",
        "declaredDocumentType",
        "confirmedDocumentType",
        "detectedDocumentType",
        "workflowDocumentType",
        "sourceFormat",
        "fileValidationStatus",
        "classificationStatus",
        "classificationConfidence",
        "parseStatus",
        "sourceFormat",
        "ocrStatus",
        "qualityStatus",
        "reviewRequired",
        "sensitiveFieldNeedsReview",
        "missingCriticalField",
        "missingFields",
        "businessInconsistency",
        "validationErrors",
        "requiredFieldsComplete",
        "overallConfidence",
        "resultReference",
        "resultPayloadHash",
        "schemaVersion",
        "errorCode",
        "idempotencyKey",
        "documentTypeDecision",
        "userReviewDecision",
        "correctionsReference",
        "hrReviewDecision",
        "hrReviewNoteReference",
        "reviewStage",
        "reviewerId",
        "reviewedAt",
        "caseVersion",
        "reviewAuditReference",
        "reviewedPayloadHash",
        "reviewReasonCodes",
        "reuploadCount",
        "maxReuploadAttempts",
        "finalHrDecision",
        "finalHrNoteReference",
        "recommendedAction",
        "templateId",
        "templateVersion",
        "parserName",
        "parserVersion",
        "ocrEngine",
        "extractionStatus",
        "extractedDataReference",
        "autoContinueEnabled",
        "hrisUpdateStatus",
        "notificationStatus",
        "processingOutcome",
    }
)

_MAX_PROCESS_STRING_LENGTH = 4096
_INCONSISTENCY_CODES = frozenset(
    {
        "FIELD_CONFLICT",
        "INVALID_DATE",
        "DATE_RANGE_CONFLICT",
    }
)


@dataclass(frozen=True, slots=True)
class QualityRoutingInputs:
    quality_status: str
    review_required: bool
    sensitive_field_needs_review: bool
    missing_critical_field: bool
    business_inconsistency: bool
    required_fields_complete: bool
    overall_confidence: float
    auto_continue_enabled: bool = False

    def __post_init__(self) -> None:
        if self.quality_status not in {status.value for status in QualityStatus}:
            raise ValueError("quality_status is not supported")
        if not 0.0 <= self.overall_confidence <= 1.0:
            raise ValueError("overall_confidence must be between 0 and 1")


def map_document_type(document_type: DocumentType) -> CamundaWorkflowDocumentType:
    mapping = {
        DocumentType.IDENTITY_CARD: CamundaWorkflowDocumentType.IDENTITY_DOCUMENT,
        DocumentType.PASSPORT: CamundaWorkflowDocumentType.IDENTITY_DOCUMENT,
        DocumentType.EMPLOYEE_PROFILE: CamundaWorkflowDocumentType.EMPLOYEE_INFORMATION_FORM,
        DocumentType.CV: CamundaWorkflowDocumentType.CV,
        DocumentType.DEGREE: CamundaWorkflowDocumentType.DEGREE,
        DocumentType.CERTIFICATE: CamundaWorkflowDocumentType.CERTIFICATE,
        DocumentType.EMPLOYMENT_CONTRACT: CamundaWorkflowDocumentType.EMPLOYMENT_CONTRACT,
        DocumentType.CONTRACT_APPENDIX: CamundaWorkflowDocumentType.EMPLOYMENT_CONTRACT,
        DocumentType.HR_DECISION: CamundaWorkflowDocumentType.HR_DECISION,
        DocumentType.LEAVE_REQUEST: CamundaWorkflowDocumentType.LEAVE_REQUEST,
        DocumentType.OVERTIME_REQUEST: CamundaWorkflowDocumentType.OVERTIME_REQUEST,
    }
    return mapping.get(document_type, CamundaWorkflowDocumentType.OTHER_HR_DOCUMENT)


def classification_status(
    declared_document_type: str,
    detected_document_type: DocumentType,
) -> str:
    try:
        declared = CamundaWorkflowDocumentType(declared_document_type)
    except ValueError:
        return "INVALID"
    if detected_document_type is DocumentType.UNKNOWN:
        return "UNKNOWN"
    if declared is map_document_type(detected_document_type):
        return "CONFIRMED"
    return "MISMATCH"


def build_quality_process_variables(
    result: IdpResult,
    *,
    rollout_policy: CamundaRolloutPolicy = M4_SHADOW_POLICY,
) -> ProcessVariables:
    issue_codes = {issue.code for issue in result.quality.issues}
    missing_critical = "REQUIRED_FIELD_MISSING" in issue_codes
    inconsistent = bool(issue_codes & _INCONSISTENCY_CODES)
    sensitive_review = any(
        field.sensitive and field.status is not FieldStatus.ACCEPTED for field in result.fields
    )
    variables: ProcessVariables = {
        "detectedDocumentType": result.classification.document_type.value,
        "workflowDocumentType": map_document_type(result.classification.document_type).value,
        "classificationConfidence": result.classification.confidence,
        "sourceFormat": result.canonical_document.source_format.value,
        "parseStatus": result.canonical_document.parse_status.value,
        "qualityStatus": result.quality.status.value,
        "reviewRequired": result.quality.review_required,
        "sensitiveFieldNeedsReview": sensitive_review,
        "missingCriticalField": missing_critical,
        "businessInconsistency": inconsistent,
        "requiredFieldsComplete": not missing_critical,
        "overallConfidence": result.quality.score,
        "schemaVersion": result.schema_version,
        "autoContinueEnabled": rollout_policy.auto_continue_enabled,
    }
    validate_process_variables(variables)
    return variables


def route_quality(inputs: QualityRoutingInputs) -> CamundaQualityAction:
    if inputs.quality_status == QualityStatus.REJECTED.value:
        return CamundaQualityAction.REQUEST_REUPLOAD
    if inputs.missing_critical_field:
        return CamundaQualityAction.REQUEST_REUPLOAD
    if inputs.sensitive_field_needs_review or inputs.business_inconsistency:
        return CamundaQualityAction.HR_REVIEW
    if not inputs.required_fields_complete:
        return CamundaQualityAction.HR_REVIEW
    if inputs.overall_confidence < 0.6:
        return CamundaQualityAction.REQUEST_REUPLOAD
    if (
        inputs.quality_status == QualityStatus.PASS.value
        and not inputs.review_required
        and inputs.overall_confidence >= 0.9
        and inputs.auto_continue_enabled
    ):
        return CamundaQualityAction.AUTO_CONTINUE
    return CamundaQualityAction.USER_REVIEW


def validate_process_variables(variables: dict[str, ProcessValue]) -> None:
    unexpected = set(variables) - PROCESS_VARIABLE_WHITELIST
    if unexpected:
        raise ValueError(f"Process variables are not allowed: {sorted(unexpected)}")
    for name, value in variables.items():
        if isinstance(value, str) and len(value) > _MAX_PROCESS_STRING_LENGTH:
            raise ValueError(f"Process variable {name} exceeds the string length limit")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise TypeError(f"Process variable {name} must contain a scalar value")


def validate_dmn_quality_variables(variables: ProcessVariables) -> None:
    missing = DMN_QUALITY_INPUT_VARIABLES - set(variables)
    unexpected = set(variables) - DMN_QUALITY_INPUT_VARIABLES
    if missing or unexpected:
        raise ValueError(
            f"DMN quality variable mismatch; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    validate_process_variables(variables)
    if variables["qualityStatus"] not in {status.value for status in QualityStatus}:
        raise ValueError("DMN qualityStatus is not supported")
    boolean_names = DMN_QUALITY_INPUT_VARIABLES - {
        "qualityStatus",
        "overallConfidence",
    }
    if any(type(variables[name]) is not bool for name in boolean_names):
        raise TypeError("DMN quality flags must be booleans")
    confidence = variables["overallConfidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise ValueError("DMN overallConfidence must be between 0 and 1")
