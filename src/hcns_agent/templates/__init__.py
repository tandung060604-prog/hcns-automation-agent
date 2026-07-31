"""Closed-set template processing for approved HCNS forms."""

from hcns_agent.templates.model import (
    RecommendedAction,
    TemplateDefinition,
    TemplateDetection,
    TemplateProcessingResult,
)
from hcns_agent.templates.registry import TemplateRegistry, build_default_template_registry
from hcns_agent.templates.service import (
    TemplateProcessingService,
    TemplateTechnicalError,
    TemplateUnsupportedError,
    build_default_template_processing_service,
)

__all__ = [
    "RecommendedAction",
    "TemplateDefinition",
    "TemplateDetection",
    "TemplateProcessingResult",
    "TemplateProcessingService",
    "TemplateRegistry",
    "TemplateTechnicalError",
    "TemplateUnsupportedError",
    "build_default_template_processing_service",
    "build_default_template_registry",
]
