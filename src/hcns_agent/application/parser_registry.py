"""Deterministic parser registration and lookup."""

from __future__ import annotations

from hcns_agent.domain.documents import SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import DocumentParser


class DocumentParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[SourceFormat, DocumentParser] = {}

    def register(self, parser: DocumentParser) -> None:
        for source_format in sorted(
            parser.capabilities.source_formats,
            key=lambda item: item.value,
        ):
            existing = self._parsers.get(source_format)
            if existing is not None:
                raise ValueError(
                    f"Parser already registered for {source_format.value}: {existing.name}"
                )
            if not parser.supports(source_format):
                raise ValueError(
                    f"Parser {parser.name} capability and supports() disagree for "
                    f"{source_format.value}"
                )
            self._parsers[source_format] = parser

    def resolve(self, source_format: SourceFormat) -> DocumentParser:
        parser = self._parsers.get(source_format)
        if parser is None:
            raise DocumentIntakeError(
                IntakeErrorCode.NO_PARSER,
                f"No document parser is registered for {source_format.value}",
            )
        return parser

    @property
    def registered_formats(self) -> tuple[SourceFormat, ...]:
        return tuple(sorted(self._parsers, key=lambda item: item.value))
