"""Universal Document Intake use case."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from hcns_agent.application.format_detection import FormatDetector
from hcns_agent.application.parser_registry import DocumentParserRegistry
from hcns_agent.application.safety import FileSafetyValidator
from hcns_agent.domain.canonical import CanonicalDocument, SourceDescriptor
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

    def execute(self, source: DocumentSource) -> CanonicalDocument:
        self._safety_validator.preflight(source)
        detection = self._detector.detect(source)
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
        )
        document = parser.parse(source, context)
        if document.source_format is not detection.source_format:
            raise ValueError("Parser returned a CanonicalDocument with the wrong source format")
        return replace(
            document,
            warnings=(*detection.warnings, *safety.warnings, *document.warnings),
        )
