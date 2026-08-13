"""Application service for local multi-format template processing."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from pathlib import PurePath
from typing import cast

from hcns_agent.adapters.camunda7.contract import (
    ProcessVariables,
    validate_process_variables,
)
from hcns_agent.adapters.paddleocr import PaddleOcrEngine
from hcns_agent.application.intake import UniversalDocumentIntake
from hcns_agent.bootstrap import build_default_intake
from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.domain.documents import SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrEngine, OcrResult
from hcns_agent.templates.compatibility import (
    canonical_template_id,
    canonicalize_corrections,
    canonicalize_template_payload,
)
from hcns_agent.templates.model import (
    ParsedTemplate,
    RecommendedAction,
    TemplateDetection,
    TemplateProcessingResult,
    TemplateValidation,
)
from hcns_agent.templates.registry import TemplateRegistry, build_default_template_registry

_SUPPORTED_TEMPLATE_FORMATS = frozenset(
    {
        SourceFormat.PLAIN_TEXT,
        SourceFormat.DOCX,
        SourceFormat.PDF_TEXT,
        SourceFormat.PDF_SCAN,
        SourceFormat.IMAGE,
        SourceFormat.XLSX,
        SourceFormat.PPTX,
    }
)
_OCR_TEMPLATE_FORMATS = frozenset({SourceFormat.PDF_SCAN, SourceFormat.IMAGE})


class TemplateUnsupportedError(ValueError):
    """The upload is valid but outside the approved closed set."""

    def __init__(self, code: str = "UNSUPPORTED_TEMPLATE") -> None:
        super().__init__(code)
        self.code = code


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


class _LazyTemplatePaddleOcrEngine:
    def __init__(self, *, device: str = "cpu") -> None:
        self._device = device
        self._delegate: PaddleOcrEngine | None = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "paddleocr/pp-ocrv5-vi"

    @property
    def model_loaded(self) -> bool:
        return self._delegate is not None

    def recognize(self, source: DocumentSource) -> OcrResult:
        if self._delegate is None:
            with self._lock:
                if self._delegate is None:
                    try:
                        self._delegate = PaddleOcrEngine.from_default(device=self._device)
                    except RuntimeError as error:
                        raise TemplateTechnicalError("OCR_RUNTIME_UNAVAILABLE") from error
        try:
            return self._delegate.recognize(source)
        except RuntimeError as error:
            raise TemplateTechnicalError("OCR_PROCESSING_FAILED") from error


class _LazyTemplateEasyOcrEngine:
    """Load the evidence-backed Vietnamese recognizer only on OCR intake."""

    def __init__(self, *, device: str = "cpu") -> None:
        self._device = device
        self._delegate: OcrEngine | None = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "easyocr/vi-greedy"

    @property
    def model_loaded(self) -> bool:
        return self._delegate is not None

    def recognize(self, source: DocumentSource) -> OcrResult:
        if self._delegate is None:
            with self._lock:
                if self._delegate is None:
                    try:
                        from hcns_agent.adapters.easyocr import EasyOcrEngine

                        self._delegate = EasyOcrEngine.from_default(device=self._device)
                    except (ImportError, RuntimeError) as error:
                        raise TemplateTechnicalError("OCR_RUNTIME_UNAVAILABLE") from error
        try:
            return self._delegate.recognize(source)
        except RuntimeError as error:
            raise TemplateTechnicalError("OCR_PROCESSING_FAILED") from error


class TemplateProcessingService:
    def __init__(
        self,
        intake: UniversalDocumentIntake,
        registry: TemplateRegistry,
        ocr_engine: OcrEngine,
    ) -> None:
        self._intake = intake
        self._registry = registry
        self._ocr_engine = ocr_engine

    def list_templates(self) -> tuple[dict[str, object], ...]:
        return self._registry.list_templates()

    @property
    def ocr_model_loaded(self) -> bool:
        return bool(getattr(self._ocr_engine, "model_loaded", False))

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
        if canonical.source_format not in _SUPPORTED_TEMPLATE_FORMATS:
            raise TemplateUnsupportedError("Unsupported template source format")
        detection = self._registry.detect(canonical)
        if detection is None:
            raise TemplateUnsupportedError("Document does not match an approved template")
        parsed = detection.definition.parser.parse(canonical, detection)
        validation = detection.definition.validator.validate(
            parsed,
            detection,
            detection.definition.required_fields,
        )
        ocr_confidence = _ocr_confidence(canonical)
        if canonical.source_format in _OCR_TEMPLATE_FORMATS:
            validation = _require_ocr_review(validation, ocr_confidence)
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
            processing=_processing_metadata(canonical, ocr_confidence),
        )

    def apply_corrections(
        self,
        stored_payload: Mapping[str, object],
        corrections: Mapping[str, object],
    ) -> TemplateProcessingResult:
        """Apply private field corrections and rerun the frozen template validator."""

        template_id = _required_payload_string(stored_payload, "templateId")
        original_template_id = template_id
        stored_payload = canonicalize_template_payload(stored_payload)
        template_id = canonical_template_id(template_id)
        template_version = _required_payload_string(stored_payload, "templateVersion")
        definition = self._registry.get(template_id)
        if definition is None or definition.version != template_version:
            raise TemplateTechnicalError("STORED_TEMPLATE_VERSION_UNAVAILABLE")

        allowed_fields = frozenset(
            (*definition.required_fields, *definition.optional_fields)
        )
        corrections = canonicalize_corrections(original_template_id, corrections)
        if not corrections or not set(corrections).issubset(allowed_fields):
            raise TemplateUnsupportedError("Correction contains unsupported fields")
        if any(not _is_correction_value(value) for value in corrections.values()):
            raise TemplateUnsupportedError("Correction values must be scalar")

        original_data = _required_payload_mapping(stored_payload, "data")
        corrected_data = {
            key: value
            for key, value in original_data.items()
            if key
            not in {
                "missingFields",
                "validationErrors",
                "confidence",
                "recommendedAction",
            }
        }
        corrected_data.update(corrections)

        detection_payload = _required_payload_mapping(stored_payload, "detection")
        matched_anchors = detection_payload.get("matchedAnchors")
        confidence = detection_payload.get("detectionConfidence")
        if (
            not isinstance(matched_anchors, list)
            or any(not isinstance(item, str) for item in matched_anchors)
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
        ):
            raise TemplateTechnicalError("STORED_TEMPLATE_RESULT_INCONSISTENT")
        detection = TemplateDetection(
            definition=definition,
            matched_anchors=tuple(cast(list[str], matched_anchors)),
            confidence=float(confidence),
        )

        quality_payload = _required_payload_mapping(stored_payload, "quality")
        validation_errors = quality_payload.get("validationErrors")
        if not isinstance(validation_errors, list) or any(
            not isinstance(item, str) for item in validation_errors
        ):
            raise TemplateTechnicalError("STORED_TEMPLATE_RESULT_INCONSISTENT")
        corrected_fields = set(corrections)
        remaining_conflicts = tuple(
            error.partition(":")[2]
            for error in cast(list[str], validation_errors)
            if error.startswith("MULTIPLE_CANDIDATES:")
            and error.partition(":")[2] not in corrected_fields
        )
        validation = definition.validator.validate(
            ParsedTemplate(
                data=corrected_data,
                conflicting_fields=remaining_conflicts,
            ),
            detection,
            definition.required_fields,
        )

        processing = dict(_required_payload_mapping(stored_payload, "processing"))
        uses_ocr = processing.get("usesOcr")
        if type(uses_ocr) is not bool:
            raise TemplateTechnicalError("STORED_TEMPLATE_RESULT_INCONSISTENT")
        if uses_ocr:
            ocr_confidence = processing.get("ocrConfidence")
            if isinstance(ocr_confidence, bool) or not isinstance(
                ocr_confidence, (int, float)
            ):
                raise TemplateTechnicalError("STORED_TEMPLATE_RESULT_INCONSISTENT")
            validation = _require_ocr_review(validation, float(ocr_confidence))

        corrected_data.update(
            {
                "missingFields": list(validation.missing_fields),
                "validationErrors": list(validation.validation_errors),
                "confidence": validation.confidence,
                "recommendedAction": validation.recommended_action.value,
            }
        )
        variables = dict(
            _required_payload_mapping(stored_payload, "camundaVariables")
        )
        variables.update(
            {
                "missingFields": ",".join(validation.missing_fields),
                "validationErrors": ",".join(validation.validation_errors),
                "recommendedAction": validation.recommended_action.value,
            }
        )
        return TemplateProcessingResult(
            detection=detection,
            data=corrected_data,
            validation=validation,
            camunda_variables=variables,
            processing=processing,
        )


def build_default_template_processing_service() -> TemplateProcessingService:
    ocr_engine = _ForbiddenTemplateOcrEngine()
    return TemplateProcessingService(
        intake=build_default_intake(ocr_engine),
        registry=build_default_template_registry(),
        ocr_engine=ocr_engine,
    )


def build_local_template_processing_service(
    *,
    device: str = "cpu",
    ocr_backend: str | None = None,
) -> TemplateProcessingService:
    selected_backend = (
        ocr_backend or os.getenv("HCNS_TEMPLATE_OCR_BACKEND") or "easyocr"
    ).casefold()
    if selected_backend == "paddle":
        ocr_engine: OcrEngine = _LazyTemplatePaddleOcrEngine(device=device)
    elif selected_backend == "easyocr":
        ocr_engine = _LazyTemplateEasyOcrEngine(device=device)
    else:
        raise ValueError(f"Unsupported local OCR backend: {selected_backend}")
    return TemplateProcessingService(
        intake=build_default_intake(ocr_engine),
        registry=build_default_template_registry(),
        ocr_engine=ocr_engine,
    )


def _ocr_confidence(document: CanonicalDocument) -> float | None:
    values = [
        float(confidence)
        for page in document.content.pages
        for block in page.blocks
        if (confidence := getattr(block, "confidence", None)) is not None
    ]
    return round(sum(values) / len(values), 4) if values else None


def _require_ocr_review(
    validation: TemplateValidation,
    ocr_confidence: float | None,
) -> TemplateValidation:
    errors = tuple(
        dict.fromkeys((*validation.validation_errors, "OCR_REVIEW_REQUIRED"))
    )
    confidence = min(validation.confidence, ocr_confidence or 0.0)
    return TemplateValidation(
        missing_fields=validation.missing_fields,
        validation_errors=errors,
        confidence=confidence,
        recommended_action=RecommendedAction.MANUAL_REVIEW,
    )


def _processing_metadata(
    document: CanonicalDocument,
    ocr_confidence: float | None,
) -> dict[str, object]:
    source_format = document.source_format
    parser = document.provenance[-1] if document.provenance else None
    model_manifest = getattr(parser, "model_manifest", None)
    uses_ocr = source_format in _OCR_TEMPLATE_FORMATS
    metadata: dict[str, object] = {
        "sourceFormat": source_format.value,
        "parserName": getattr(parser, "parser_name", "unknown"),
        "parserVersion": getattr(parser, "parser_version", "unknown"),
        "usesOcr": uses_ocr,
        "ocrEngine": getattr(model_manifest, "engine", None) if uses_ocr else None,
        "ocrVersion": getattr(model_manifest, "version", None) if uses_ocr else None,
        "ocrModels": list(getattr(model_manifest, "model_identifiers", ())) if uses_ocr else [],
        "ocrDevice": getattr(model_manifest, "device", None) if uses_ocr else None,
        "ocrProfile": "template-first-review" if uses_ocr else "native-text",
        "ocrConfidence": ocr_confidence if uses_ocr else None,
    }
    provenance_metadata = getattr(parser, "metadata", {})
    raw_evidence = provenance_metadata.get("ocrRoiEvidence")
    if isinstance(raw_evidence, str):
        try:
            decoded = json.loads(raw_evidence)
        except json.JSONDecodeError:
            decoded = []
        if isinstance(decoded, list):
            metadata["ocrFieldEvidence"] = [
                {
                    key: item[key]
                    for key in ("field", "confidence", "box", "recognizer", "reason")
                    if key in item
                }
                for item in decoded
                if isinstance(item, dict)
            ]
    return metadata


def _required_payload_mapping(
    payload: Mapping[str, object],
    name: str,
) -> Mapping[str, object]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise TemplateTechnicalError("STORED_TEMPLATE_RESULT_INCONSISTENT")
    return cast(Mapping[str, object], value)


def _required_payload_string(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise TemplateTechnicalError("STORED_TEMPLATE_RESULT_INCONSISTENT")
    return value


def _is_correction_value(value: object) -> bool:
    return value is None or (
        isinstance(value, (str, int, float, bool))
        and not (isinstance(value, str) and len(value) > 16_384)
    )
