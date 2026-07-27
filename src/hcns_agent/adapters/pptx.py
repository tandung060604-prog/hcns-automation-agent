"""Limited native PPTX extension using the common DocumentParser contract."""

from __future__ import annotations

import re
from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from hcns_agent.domain.canonical import (
    CanonicalDocument,
    DocumentContent,
    Page,
    Paragraph,
    ParserProvenance,
    ParseWarning,
    SourceLocation,
)
from hcns_agent.domain.documents import ParseStatus, SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import (
    DocumentSource,
    ParseContext,
    ParserCapabilities,
)

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS = {"a": _A}


class PptxDocumentParser:
    """Text-only extension point; advanced shape/table fidelity is a later milestone."""

    name = "pptx/ooxml-text"
    version = "0.1.0"
    capabilities = ParserCapabilities(
        source_formats=frozenset({SourceFormat.PPTX}),
        preserves_layout=False,
    )

    def supports(self, source_format: SourceFormat) -> bool:
        return source_format in self.capabilities.source_formats

    def parse(self, source: DocumentSource, context: ParseContext) -> CanonicalDocument:
        pages: list[Page] = []
        try:
            with ZipFile(BytesIO(source.content)) as archive:
                slide_names = sorted(
                    (
                        name
                        for name in archive.namelist()
                        if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                    ),
                    key=_slide_number,
                )
                for page_index, slide_name in enumerate(slide_names):
                    root = ElementTree.fromstring(archive.read(slide_name))
                    blocks: list[Paragraph] = []
                    for paragraph in root.findall(".//a:p", _NS):
                        text = "".join(
                            node.text or "" for node in paragraph.findall(".//a:t", _NS)
                        ).strip()
                        if not text:
                            continue
                        block_index = len(blocks)
                        blocks.append(
                            Paragraph(
                                block_id=f"slide-{page_index}-block-{block_index}",
                                text=text,
                                source=SourceLocation(
                                    source_reference=source.source_reference,
                                    page_index=page_index,
                                    block_index=block_index,
                                ),
                            )
                        )
                    pages.append(Page(page_index=page_index, blocks=tuple(blocks)))
        except (BadZipFile, ElementTree.ParseError) as error:
            raise DocumentIntakeError(
                IntakeErrorCode.CORRUPTED_FILE,
                "PPTX slide XML could not be parsed",
            ) from error

        return CanonicalDocument(
            document_id=source.document_id,
            source=context.source_descriptor,
            source_format=context.source_format,
            content=DocumentContent(pages=tuple(pages)),
            parse_status=ParseStatus.PARTIAL,
            provenance=(
                ParserProvenance(
                    parser_name=self.name,
                    parser_version=self.version,
                    source_format=context.source_format,
                    metadata={"library": "stdlib-ooxml"},
                ),
            ),
            warnings=(
                ParseWarning(
                    code="PPTX_LIMITED_SUPPORT",
                    message="PPTX parser currently preserves text by slide only",
                ),
            ),
        )


def _slide_number(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0
