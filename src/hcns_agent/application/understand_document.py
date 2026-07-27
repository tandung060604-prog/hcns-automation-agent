"""Classify a canonical document, extract fields, and apply the quality gate."""

from __future__ import annotations

from hcns_agent.application.extractor_registry import FieldExtractorRegistry
from hcns_agent.application.intake import UniversalDocumentIntake
from hcns_agent.application.quality_gate import ValidationQualityGate
from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.domain.understanding import IdpResult
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.understanding import DocumentClassifier


class DocumentUnderstandingService:
    def __init__(
        self,
        classifier: DocumentClassifier,
        extractors: FieldExtractorRegistry,
        quality_gate: ValidationQualityGate,
    ) -> None:
        self._classifier = classifier
        self._extractors = extractors
        self._quality_gate = quality_gate

    def execute(self, document: CanonicalDocument) -> IdpResult:
        classification = self._classifier.classify(document)
        extractor = self._extractors.resolve(classification.document_type)
        fields = extractor.extract(document, classification) if extractor is not None else ()
        validated_fields, quality = self._quality_gate.evaluate(
            document,
            classification,
            fields,
            extractor_available=extractor is not None,
        )
        return IdpResult(
            canonical_document=document,
            classification=classification,
            fields=validated_fields,
            quality=quality,
        )


class IdpPipeline:
    def __init__(
        self,
        intake: UniversalDocumentIntake,
        understanding: DocumentUnderstandingService,
    ) -> None:
        self._intake = intake
        self._understanding = understanding

    def execute(self, source: DocumentSource) -> IdpResult:
        canonical_document = self._intake.execute(source)
        return self._understanding.execute(canonical_document)
