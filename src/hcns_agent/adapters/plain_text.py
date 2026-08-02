"""Native UTF-8 plain-text parser for controlled dataset intake."""

from __future__ import annotations

from hcns_agent.domain.canonical import (
    CanonicalDocument,
    DocumentContent,
    Page,
    Paragraph,
    ParserProvenance,
    SourceLocation,
)
from hcns_agent.domain.documents import ParseStatus, SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import DocumentSource, ParseContext, ParserCapabilities


class PlainTextDocumentParser:
    name = "text/utf8-native"
    version = "1.0.0"
    capabilities = ParserCapabilities(
        source_formats=frozenset({SourceFormat.PLAIN_TEXT}),
        preserves_layout=False,
    )

    def supports(self, source_format: SourceFormat) -> bool:
        return source_format in self.capabilities.source_formats

    def parse(self, source: DocumentSource, context: ParseContext) -> CanonicalDocument:
        try:
            text = source.content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DocumentIntakeError(
                IntakeErrorCode.CORRUPTED_FILE,
                "Plain-text source is not valid UTF-8",
            ) from error

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        blocks = tuple(
            Paragraph(
                block_id=f"text-block-{index}",
                text=line,
                source=SourceLocation(
                    source_reference=source.source_reference,
                    page_index=0,
                    block_index=index,
                ),
            )
            for index, line in enumerate(lines)
        )
        return CanonicalDocument(
            document_id=source.document_id,
            source=context.source_descriptor,
            source_format=context.source_format,
            content=DocumentContent(pages=(Page(page_index=0, blocks=blocks),)),
            parse_status=ParseStatus.SUCCESS,
            provenance=(
                ParserProvenance(
                    parser_name=self.name,
                    parser_version=self.version,
                    source_format=context.source_format,
                    metadata={"encoding": "utf-8"},
                ),
            ),
        )
