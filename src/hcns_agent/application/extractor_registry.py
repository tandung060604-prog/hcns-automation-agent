"""Deterministic field extractor registration by DocumentType."""

from __future__ import annotations

from hcns_agent.domain.documents import DocumentType
from hcns_agent.ports.understanding import FieldExtractor


class FieldExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: dict[DocumentType, FieldExtractor] = {}

    def register(self, extractor: FieldExtractor) -> None:
        for document_type in sorted(
            extractor.document_types,
            key=lambda item: item.value,
        ):
            existing = self._extractors.get(document_type)
            if existing is not None:
                raise ValueError(
                    f"Extractor already registered for {document_type.value}: {existing.name}"
                )
            if not extractor.supports(document_type):
                raise ValueError(
                    f"Extractor {extractor.name} capability and supports() disagree for "
                    f"{document_type.value}"
                )
            self._extractors[document_type] = extractor

    def resolve(self, document_type: DocumentType) -> FieldExtractor | None:
        return self._extractors.get(document_type)

    @property
    def registered_types(self) -> tuple[DocumentType, ...]:
        return tuple(sorted(self._extractors, key=lambda item: item.value))
