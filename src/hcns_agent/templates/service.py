"""Application service for local, native-DOCX template processing."""

from __future__ import annotations

from pathlib import PurePath

from hcns_agent.adapters.camunda7.contract import (
    ProcessVariables,
    validate_process_variables,
)
from hcns_agent.application.intake import UniversalDocumentIntake
from hcns_agent.bootstrap import build_default_intake
from hcns_agent.domain.documents import SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrResult
from hcns_agent.templates.model import TemplateProcessingResult
from hcns_agent.templates.registry import TemplateRegistry, build_default_template_registry


class TemplateUnsupportedError(ValueError):
    """The upload is valid but outside the approved closed set."""


class TemplateTechnicalError(RuntimeError):
    """The upload could not be safely parsed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _ForbiddenTemplateOcrEngine:
    @property
    def name(self) -> str:
        return "template-first/ocr-forbidden"

    def recognize(self, source: DocumentSource) -> OcrResult:
        raise RuntimeError("OCR is outside template-first Phase 1")


class TemplateProcessingService:
    def __init__(
        self,
        intake: UniversalDocumentIntake,
        registry: TemplateRegistry,
    ) -> None:
        self._intake = intake
        self._registry = registry

    def list_templates(self) -> tuple[dict[str, object], ...]:
        return self._registry.list_templates()

    def process(
        self,
        source: DocumentSource,
        *,
        result_reference: str | None = None,
    ) -> TemplateProcessingResult:
        try:
            canonical = self._intake.execute(source)
        except DocumentIntakeError as error:
            if (
                error.code is IntakeErrorCode.UNSUPPORTED_FORMAT
                and PurePath(source.filename).suffix.casefold() == ".docx"
            ):
                raise TemplateTechnicalError(IntakeErrorCode.CORRUPTED_FILE.value) from error
            if error.code in {
                IntakeErrorCode.UNSUPPORTED_FORMAT,
                IntakeErrorCode.NO_PARSER,
                IntakeErrorCode.CONVERSION_REQUIRED,
            }:
                raise TemplateUnsupportedError("Unsupported file type") from error
            raise TemplateTechnicalError(error.code.value) from error
        if canonical.source_format is not SourceFormat.DOCX:
            raise TemplateUnsupportedError("Only native-text DOCX is supported")
        detection = self._registry.detect(canonical)
        if detection is None:
            raise TemplateUnsupportedError("Document does not match an approved template")
        parsed = detection.definition.parser.parse(canonical, detection)
        validation = detection.definition.validator.validate(
            parsed,
            detection,
            detection.definition.required_fields,
        )
        data = dict(parsed.data)
        data.update(
            {
                "missingFields": list(validation.missing_fields),
                "validationErrors": list(validation.validation_errors),
                "confidence": validation.confidence,
                "recommendedAction": validation.recommended_action.value,
            }
        )
        variables: ProcessVariables = {
            "documentType": detection.definition.document_type.value,
            "templateId": detection.definition.template_id,
            "templateVersion": detection.definition.version,
            "extractionStatus": "SUCCESS",
            "missingFields": ",".join(validation.missing_fields),
            "validationErrors": ",".join(validation.validation_errors),
            "recommendedAction": validation.recommended_action.value,
            "extractedDataReference": result_reference
            or f"template_first/results/{canonical.document_id}.json",
        }
        validate_process_variables(variables)
        return TemplateProcessingResult(
            detection=detection,
            data=data,
            validation=validation,
            camunda_variables=dict(variables),
        )


def build_default_template_processing_service() -> TemplateProcessingService:
    return TemplateProcessingService(
        intake=build_default_intake(_ForbiddenTemplateOcrEngine()),
        registry=build_default_template_registry(),
    )
