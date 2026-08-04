"""Camunda Platform 7 adapters kept outside the domain/application layers."""

from hcns_agent.adapters.camunda7.client import (
    Camunda7ExternalTaskClient,
    Camunda7RestConfig,
    ExternalTask,
    TopicSubscription,
    UrllibCamundaRestTransport,
)
from hcns_agent.adapters.camunda7.contract import (
    DMN_QUALITY_INPUT_VARIABLES,
    M4_SHADOW_POLICY,
    M5_SHADOW_POLICY,
    CamundaQualityAction,
    CamundaRolloutPolicy,
    CamundaWorkflowDocumentType,
    QualityRoutingInputs,
    build_quality_process_variables,
    classification_status,
    map_document_type,
    route_quality,
    validate_dmn_quality_variables,
    validate_process_variables,
)
from hcns_agent.adapters.camunda7.handlers import (
    ALL_EXTERNAL_TASK_TOPICS,
    MockSideEffectHandler,
    ReferenceStageHandler,
    ReuploadControlHandler,
    build_m4_shadow_handlers,
)
from hcns_agent.adapters.camunda7.review import (
    JsonFileCorrectionStore,
    JsonFileReviewAuditStore,
)
from hcns_agent.adapters.camunda7.worker import (
    Camunda7ExternalTaskWorker,
    CamundaBusinessError,
    CamundaTechnicalError,
    LockExtensionPolicy,
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
    "DMN_QUALITY_INPUT_VARIABLES",
    "ExternalTask",
    "JsonFileTemplateResultStore",
    "JsonFileCorrectionStore",
    "JsonFileReviewAuditStore",
    "LocalSessionDocumentSourceStore",
    "LockExtensionPolicy",
    "M4_SHADOW_POLICY",
    "M5_SHADOW_POLICY",
    "M4CamundaRuntimeConfig",
    "M4TemplateStageOperations",
    "MockSideEffectHandler",
    "QualityRoutingInputs",
    "ReferenceStageHandler",
    "ReuploadControlHandler",
    "StoredTemplateResult",
    "TopicSubscription",
    "UrllibCamundaRestTransport",
    "build_quality_process_variables",
    "build_m4_shadow_handlers",
    "build_m4_worker",
    "build_m4_worker_from_environment",
    "classification_status",
    "map_document_type",
    "route_quality",
    "validate_dmn_quality_variables",
    "validate_process_variables",
]

_RUNTIME_EXPORTS = frozenset(
    {
        "JsonFileTemplateResultStore",
        "LocalSessionDocumentSourceStore",
        "M4CamundaRuntimeConfig",
        "M4TemplateStageOperations",
        "StoredTemplateResult",
        "build_m4_worker",
        "build_m4_worker_from_environment",
    }
)


def __getattr__(name: str) -> object:
    """Load the runtime composition root only after package initialization.

    ``runtime`` imports ``templates.service``.  Eagerly importing it here
    makes the reverse import from ``templates.service`` circular, so runtime
    exports remain public but are resolved lazily.
    """

    if name not in _RUNTIME_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from hcns_agent.adapters.camunda7 import runtime

    value = getattr(runtime, name)
    globals()[name] = value
    return value
