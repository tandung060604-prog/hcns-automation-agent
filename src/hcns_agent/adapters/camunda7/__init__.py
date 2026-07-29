"""Camunda Platform 7 adapters kept outside the domain/application layers."""

from hcns_agent.adapters.camunda7.client import (
    Camunda7ExternalTaskClient,
    Camunda7RestConfig,
    ExternalTask,
    TopicSubscription,
    UrllibCamundaRestTransport,
)
from hcns_agent.adapters.camunda7.contract import (
    M4_SHADOW_POLICY,
    CamundaQualityAction,
    CamundaRolloutPolicy,
    CamundaWorkflowDocumentType,
    QualityRoutingInputs,
    build_quality_process_variables,
    classification_status,
    map_document_type,
    route_quality,
    validate_process_variables,
)
from hcns_agent.adapters.camunda7.handlers import (
    ALL_EXTERNAL_TASK_TOPICS,
    MockSideEffectHandler,
    ReferenceStageHandler,
    ReuploadControlHandler,
    build_m4_shadow_handlers,
)
from hcns_agent.adapters.camunda7.worker import (
    Camunda7ExternalTaskWorker,
    CamundaBusinessError,
    CamundaTechnicalError,
)

__all__ = [
    "ALL_EXTERNAL_TASK_TOPICS",
    "Camunda7ExternalTaskClient",
    "Camunda7RestConfig",
    "Camunda7ExternalTaskWorker",
    "CamundaBusinessError",
    "CamundaQualityAction",
    "CamundaRolloutPolicy",
    "CamundaTechnicalError",
    "CamundaWorkflowDocumentType",
    "ExternalTask",
    "M4_SHADOW_POLICY",
    "MockSideEffectHandler",
    "QualityRoutingInputs",
    "ReferenceStageHandler",
    "ReuploadControlHandler",
    "TopicSubscription",
    "UrllibCamundaRestTransport",
    "build_quality_process_variables",
    "build_m4_shadow_handlers",
    "classification_status",
    "map_document_type",
    "route_quality",
    "validate_process_variables",
]
