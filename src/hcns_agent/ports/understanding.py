"""Vendor-neutral classification and field extraction contracts."""

from __future__ import annotations

from typing import Protocol

from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.domain.documents import DocumentType
from hcns_agent.domain.understanding import BusinessField, DocumentClassification


class DocumentClassifier(Protocol):
    @property
    def name(self) -> str:
        """Stable classifier name."""

    @property
    def version(self) -> str:
        """Stable classifier version."""

    def classify(self, document: CanonicalDocument) -> DocumentClassification:
        """Classify business document type without changing technical parser routing."""


class FieldExtractor(Protocol):
    @property
    def name(self) -> str:
        """Stable extractor name."""

    @property
    def version(self) -> str:
        """Stable extractor version."""

    @property
    def document_types(self) -> frozenset[DocumentType]:
        """Business types supported by this extractor."""

    def supports(self, document_type: DocumentType) -> bool:
        """Return whether this extractor supports the classified business type."""

    def extract(
        self,
        document: CanonicalDocument,
        classification: DocumentClassification,
    ) -> tuple[BusinessField, ...]:
        """Extract normalized fields with source evidence."""
