"""Reference-only stage handlers and mock side effects for the M4 shadow pilot."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from hcns_agent.adapters.camunda7.contract import (
    M4_CLOSED_SET_WORKFLOW_DOCUMENT_TYPES,
    ProcessValue,
    ProcessVariables,
    validate_process_variables,
)
from hcns_agent.adapters.camunda7.worker import CamundaBusinessError

StageOperation = Callable[[Mapping[str, ProcessValue]], ProcessVariables]

DOCUMENT_STAGE_TOPICS = (
    "document_validate_file",
    "document_parse_content",
    "document_detect_type",
    "document_extract",
    "document_normalize_validate",
    "document_apply_corrections",
)
ALL_EXTERNAL_TASK_TOPICS = (
    *DOCUMENT_STAGE_TOPICS,
    "document_record_review_audit",
    "document_reupload_control",
    "hris_update_employee_record",
    "hr_notify_processing_result",
)
_REQUIRED_STAGE_VARIABLES = {
    "document_validate_file": frozenset(
        {"applicationId", "documentReference", "idempotencyKey"}
    ),
    "document_parse_content": frozenset({"documentReference", "idempotencyKey"}),
    "document_detect_type": frozenset(
        {"resultReference", "declaredDocumentType", "idempotencyKey"}
    ),
    "document_extract": frozenset(
        {"resultReference", "workflowDocumentType", "idempotencyKey"}
    ),
    "document_normalize_validate": frozenset({"resultReference", "idempotencyKey"}),
    "document_apply_corrections": frozenset(
        {"resultReference", "correctionsReference", "idempotencyKey"}
    ),
}


@dataclass(frozen=True, slots=True)
class ReferenceStageHandler:
    topic_name: str
    required_variables: frozenset[str]
    operation: StageOperation
    allowed_workflow_document_types: frozenset[str] | None = None

    def handle(self, variables: Mapping[str, ProcessValue]) -> ProcessVariables:
        missing = sorted(
            name
            for name in self.required_variables
            if name not in variables or variables[name] in {None, ""}
        )
        if missing:
            raise CamundaBusinessError(
                "DOCUMENT_INPUT_INVALID",
                "Required document task references are missing",
                variables={"errorCode": "DOCUMENT_INPUT_INVALID"},
            )
        if self.allowed_workflow_document_types is not None:
            workflow_document_type = variables.get("workflowDocumentType")
            if workflow_document_type not in self.allowed_workflow_document_types:
                raise CamundaBusinessError(
                    "DOCUMENT_INPUT_INVALID",
                    "Document type is outside the M4 closed set",
                    variables={"errorCode": "DOCUMENT_INPUT_INVALID"},
                )
        result = self.operation(variables)
        validate_process_variables(result)
        return result


@dataclass(frozen=True, slots=True)
class ReuploadControlHandler:
    topic_name: str = "document_reupload_control"

    def handle(self, variables: Mapping[str, ProcessValue]) -> ProcessVariables:
        current = variables.get("reuploadCount", 0)
        maximum = variables.get("maxReuploadAttempts", 3)
        case_version = variables.get("caseVersion", 1)
        if not isinstance(current, int) or isinstance(current, bool) or current < 0:
            raise CamundaBusinessError(
                "DOCUMENT_INPUT_INVALID",
                "Re-upload counter is invalid",
                variables={"errorCode": "DOCUMENT_INPUT_INVALID"},
            )
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
            raise CamundaBusinessError(
                "DOCUMENT_INPUT_INVALID",
                "Maximum re-upload attempts is invalid",
                variables={"errorCode": "DOCUMENT_INPUT_INVALID"},
            )
        if (
            not isinstance(case_version, int)
            or isinstance(case_version, bool)
            or case_version <= 0
        ):
            raise CamundaBusinessError(
                "DOCUMENT_INPUT_INVALID",
                "Case version is invalid",
                variables={"errorCode": "DOCUMENT_INPUT_INVALID"},
            )
        return {
            "reuploadCount": current + 1,
            "maxReuploadAttempts": maximum,
            "caseVersion": case_version + 1,
        }


@dataclass(frozen=True, slots=True)
class MockSideEffectHandler:
    topic_name: str
    status_variable: str
    status_value: str = "SIMULATED"

    def handle(self, variables: Mapping[str, ProcessValue]) -> ProcessVariables:
        idempotency_key = variables.get("idempotencyKey")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise CamundaBusinessError(
                "DOCUMENT_INPUT_INVALID",
                "Idempotency key is required for side effects",
                variables={"errorCode": "DOCUMENT_INPUT_INVALID"},
            )
        result: ProcessVariables = {self.status_variable: self.status_value}
        validate_process_variables(result)
        return result


def build_m4_shadow_handlers(
    stage_operations: Mapping[str, StageOperation],
    review_audit_operation: StageOperation,
) -> tuple[ReferenceStageHandler | ReuploadControlHandler | MockSideEffectHandler, ...]:
    missing = sorted(set(DOCUMENT_STAGE_TOPICS) - set(stage_operations))
    unexpected = sorted(set(stage_operations) - set(DOCUMENT_STAGE_TOPICS))
    if missing or unexpected:
        raise ValueError(
            f"Stage operation registry mismatch; missing={missing}, unexpected={unexpected}"
        )
    stages = tuple(
        ReferenceStageHandler(
            topic_name=topic,
            required_variables=_REQUIRED_STAGE_VARIABLES[topic],
            operation=stage_operations[topic],
            allowed_workflow_document_types=(
                M4_CLOSED_SET_WORKFLOW_DOCUMENT_TYPES
                if topic == "document_extract"
                else None
            ),
        )
        for topic in DOCUMENT_STAGE_TOPICS
    )
    return (
        *stages,
        ReferenceStageHandler(
            topic_name="document_record_review_audit",
            required_variables=frozenset(
                {
                    "resultReference",
                    "resultPayloadHash",
                    "reviewStage",
                    "reviewerId",
                    "reviewedAt",
                    "caseVersion",
                    "idempotencyKey",
                }
            ),
            operation=review_audit_operation,
        ),
        ReuploadControlHandler(),
        MockSideEffectHandler(
            topic_name="hris_update_employee_record",
            status_variable="hrisUpdateStatus",
        ),
        MockSideEffectHandler(
            topic_name="hr_notify_processing_result",
            status_variable="notificationStatus",
        ),
    )
