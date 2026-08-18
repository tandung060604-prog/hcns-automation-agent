"""Universal Document Intake use case."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from hcns_agent.application.format_detection import FormatDetector
from hcns_agent.application.ocr_scope import ocr_scope_for
from hcns_agent.application.parser_registry import DocumentParserRegistry
from hcns_agent.application.safety import FileSafetyValidator
from hcns_agent.domain.canonical import CanonicalDocument, SourceDescriptor
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import DocumentSource, ParseContext


class UniversalDocumentIntake:
    def __init__(
        self,
        detector: FormatDetector,
        safety_validator: FileSafetyValidator,
        registry: DocumentParserRegistry,
    ) -> None:
        self._detector = detector
        self._safety_validator = safety_validator
        self._registry = registry

    def execute(self, source: DocumentSource, *, allow_ocr: bool = True) -> CanonicalDocument:
        self._safety_validator.preflight(source)
        detection = self._detector.detect(source)
        if not allow_ocr and ocr_scope_for(detection.source_format, None) == "UNSUPPORTED_NO_OCR":
            raise DocumentIntakeError(
                IntakeErrorCode.UNSUPPORTED_FORMAT,
                "OCR is disabled for this document scope",
                details={"reason": "OCR_DISABLED_BY_POLICY"},
            )
        safety = self._safety_validator.validate(source, detection)
        parser = self._registry.resolve(detection.source_format)
        descriptor = SourceDescriptor(
            document_id=source.document_id,
            filename=source.filename,
            media_type=detection.media_type,
            size_bytes=len(source.content),
            checksum_sha256=sha256(source.content).hexdigest(),
            source_reference=source.source_reference,
        )
        context = ParseContext(
            source_descriptor=descriptor,
            source_format=detection.source_format,
            media_type=detection.media_type,
            pdf_content_profile=(
                detection.pdf_inspection.content_profile
                if detection.pdf_inspection is not None
                else None
            ),
        )
        document = parser.parse(source, context)
        if document.source_format is not detection.source_format:
            raise ValueError("Parser returned a CanonicalDocument with the wrong source format")
        return replace(
            document,
            warnings=(*detection.warnings, *safety.warnings, *document.warnings),
        )
