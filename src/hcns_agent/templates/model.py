"""Contracts shared by closed-set template implementations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.domain.documents import DocumentType


class RecommendedAction(str, Enum):
    AUTO_CONTINUE = "AUTO_CONTINUE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECT_UNSUPPORTED = "REJECT_UNSUPPORTED"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"


@dataclass(frozen=True, slots=True)
class ParsedTemplate:
    data: dict[str, object]
    conflicting_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TemplateValidation:
    missing_fields: tuple[str, ...]
    validation_errors: tuple[str, ...]
    confidence: float
    recommended_action: RecommendedAction


class TemplateParser(Protocol):
    def parse(
        self,
        document: CanonicalDocument,
        detection: TemplateDetection,
    ) -> ParsedTemplate:
        """Extract values that appear directly in the canonical document."""


class TemplateValidator(Protocol):
    def validate(
        self,
        parsed: ParsedTemplate,
        detection: TemplateDetection,
        required_fields: tuple[str, ...],
    ) -> TemplateValidation:
        """Validate one parsed template without inventing missing values."""


@dataclass(frozen=True, slots=True)
class TemplateDefinition:
    template_id: str
    document_type: DocumentType
    version: str
    supported_file_types: tuple[str, ...]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    anchors: tuple[str, ...]
    minimum_anchor_matches: int
    parser: TemplateParser
    validator: TemplateValidator

    def __post_init__(self) -> None:
        if not self.template_id or not self.version:
            raise ValueError("Template id and version are required")
        if not 1 <= self.minimum_anchor_matches <= len(self.anchors):
            raise ValueError("Template anchor threshold is invalid")

    def public_dict(self) -> dict[str, object]:
        return {
            "templateId": self.template_id,
            "documentType": self.document_type.value,
            "version": self.version,
            "supportedFileTypes": list(self.supported_file_types),
            "requiredFields": list(self.required_fields),
            "optionalFields": list(self.optional_fields),
        }


@dataclass(frozen=True, slots=True)
class TemplateDetection:
    definition: TemplateDefinition
    matched_anchors: tuple[str, ...]
    confidence: float

    @property
    def is_exact(self) -> bool:
        return len(self.matched_anchors) == len(self.definition.anchors)

    def public_dict(self) -> dict[str, object]:
        return {
            "templateId": self.definition.template_id,
            "documentType": self.definition.document_type.value,
            "matchedAnchors": list(self.matched_anchors),
            "detectionConfidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class TemplateProcessingResult:
    detection: TemplateDetection
    data: dict[str, object]
    validation: TemplateValidation
    camunda_variables: dict[str, object]

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "SUCCESS",
            "documentType": self.detection.definition.document_type.value,
            "templateId": self.detection.definition.template_id,
            "templateVersion": self.detection.definition.version,
            "detection": self.detection.public_dict(),
            "data": self.data,
            "quality": {
                "missingFields": list(self.validation.missing_fields),
                "validationErrors": list(self.validation.validation_errors),
                "confidence": self.validation.confidence,
                "recommendedAction": self.validation.recommended_action.value,
            },
            "camundaVariables": self.camunda_variables,
        }
