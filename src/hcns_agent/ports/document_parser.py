"""Vendor-neutral document parser contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from hcns_agent.domain.canonical import CanonicalDocument, SourceDescriptor
from hcns_agent.domain.documents import SourceFormat


@dataclass(frozen=True, slots=True)
class DocumentSource:
    document_id: str
    filename: str
    content: bytes
    declared_media_type: str | None = None
    declared_document_type: str | None = None
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id must not be empty")
        if not self.filename.strip():
            raise ValueError("filename must not be empty")


@dataclass(frozen=True, slots=True)
class ParserCapabilities:
    source_formats: frozenset[SourceFormat]
    preserves_layout: bool = False
    preserves_tables: bool = False
    uses_ocr: bool = False


@dataclass(frozen=True, slots=True)
class ParseContext:
    source_descriptor: SourceDescriptor
    source_format: SourceFormat
    media_type: str | None


class DocumentParser(Protocol):
    @property
    def name(self) -> str:
        """Stable parser identifier."""

    @property
    def version(self) -> str:
        """Stable parser implementation version."""

    @property
    def capabilities(self) -> ParserCapabilities:
        """Formats and structural features supported by this parser."""

    def supports(self, source_format: SourceFormat) -> bool:
        """Return whether this parser supports the detected source format."""

    def parse(self, source: DocumentSource, context: ParseContext) -> CanonicalDocument:
        """Parse a validated source into the Canonical Document Model."""
