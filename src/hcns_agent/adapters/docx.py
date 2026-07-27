"""Native DOCX parser based on the OOXML package structure."""

from __future__ import annotations

import re
from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from hcns_agent.domain.canonical import (
    CanonicalDocument,
    DocumentContent,
    EmbeddedImage,
    Heading,
    ListBlock,
    Paragraph,
    ParserProvenance,
    ScalarValue,
    SourceLocation,
    Table,
    TableCell,
    TableRow,
)
from hcns_agent.domain.documents import ParseStatus, SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import (
    DocumentSource,
    ParseContext,
    ParserCapabilities,
)

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS = {"w": _W, "a": _A, "r": _R}


class DocxDocumentParser:
    name = "docx/ooxml-native"
    version = "1.0.0"
    capabilities = ParserCapabilities(
        source_formats=frozenset({SourceFormat.DOCX}),
        preserves_layout=True,
        preserves_tables=True,
    )

    def supports(self, source_format: SourceFormat) -> bool:
        return source_format in self.capabilities.source_formats

    def parse(self, source: DocumentSource, context: ParseContext) -> CanonicalDocument:
        try:
            with ZipFile(BytesIO(source.content)) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
                metadata = _core_properties(archive)
        except (BadZipFile, KeyError, ElementTree.ParseError) as error:
            raise DocumentIntakeError(
                IntakeErrorCode.CORRUPTED_FILE,
                "DOCX document.xml could not be parsed",
            ) from error

        body = root.find("w:body", _NS)
        blocks: list[Paragraph | Heading | ListBlock | Table | EmbeddedImage] = []
        pending_list: list[str] = []

        def flush_list() -> None:
            if not pending_list:
                return
            block_index = len(blocks)
            blocks.append(
                ListBlock(
                    block_id=f"docx-block-{block_index}",
                    items=tuple(pending_list),
                    ordered=True,
                    source=_location(source, block_index),
                )
            )
            pending_list.clear()

        if body is not None:
            for element in body:
                if element.tag == f"{{{_W}}}p":
                    text = _text(element)
                    is_list = element.find("w:pPr/w:numPr", _NS) is not None
                    if is_list and text:
                        pending_list.append(text)
                    else:
                        flush_list()
                        style = _paragraph_style(element)
                        if text:
                            block_index = len(blocks)
                            heading_level = _heading_level(style)
                            if heading_level is not None:
                                blocks.append(
                                    Heading(
                                        block_id=f"docx-block-{block_index}",
                                        text=text,
                                        level=heading_level,
                                        style=style,
                                        source=_location(source, block_index),
                                    )
                                )
                            else:
                                blocks.append(
                                    Paragraph(
                                        block_id=f"docx-block-{block_index}",
                                        text=text,
                                        style=style,
                                        source=_location(source, block_index),
                                    )
                                )
                        for blip in element.findall(".//a:blip", _NS):
                            block_index = len(blocks)
                            blocks.append(
                                EmbeddedImage(
                                    block_id=f"docx-block-{block_index}",
                                    relationship_id=blip.get(f"{{{_R}}}embed"),
                                    source=_location(source, block_index),
                                )
                            )
                elif element.tag == f"{{{_W}}}tbl":
                    flush_list()
                    block_index = len(blocks)
                    blocks.append(_table(element, source, block_index))
            flush_list()

        return CanonicalDocument(
            document_id=source.document_id,
            source=context.source_descriptor,
            source_format=context.source_format,
            content=DocumentContent(blocks=tuple(blocks)),
            parse_status=ParseStatus.SUCCESS,
            provenance=(
                ParserProvenance(
                    parser_name=self.name,
                    parser_version=self.version,
                    source_format=context.source_format,
                    metadata={"library": "stdlib-ooxml"},
                ),
            ),
            metadata=metadata,
        )


def _text(element: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//w:t", _NS)).strip()


def _core_properties(archive: ZipFile) -> dict[str, ScalarValue]:
    try:
        root = ElementTree.fromstring(archive.read("docProps/core.xml"))
    except KeyError:
        return {}
    except ElementTree.ParseError as error:
        raise DocumentIntakeError(
            IntakeErrorCode.CORRUPTED_FILE,
            "DOCX core properties could not be parsed",
        ) from error
    properties: dict[str, ScalarValue] = {}
    for child in root:
        value = (child.text or "").strip()
        if value:
            properties[child.tag.rsplit("}", maxsplit=1)[-1]] = value
    return properties


def _paragraph_style(element: ElementTree.Element) -> str | None:
    style = element.find("w:pPr/w:pStyle", _NS)
    return style.get(f"{{{_W}}}val") if style is not None else None


def _heading_level(style: str | None) -> int | None:
    if style is None:
        return None
    match = re.match(r"heading\s*(\d+)", style, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _location(source: DocumentSource, block_index: int) -> SourceLocation:
    return SourceLocation(
        source_reference=source.source_reference,
        block_index=block_index,
    )


def _table(element: ElementTree.Element, source: DocumentSource, block_index: int) -> Table:
    rows: list[TableRow] = []
    for row_index, row_element in enumerate(element.findall("w:tr", _NS)):
        cells: list[TableCell] = []
        for column_index, cell_element in enumerate(row_element.findall("w:tc", _NS)):
            location = SourceLocation(
                source_reference=source.source_reference,
                block_index=block_index,
                row_index=row_index,
                column_index=column_index,
            )
            cells.append(
                TableCell(
                    row_index=row_index,
                    column_index=column_index,
                    text=_text(cell_element),
                    source=location,
                )
            )
        rows.append(TableRow(row_index=row_index, cells=tuple(cells)))
    return Table(
        block_id=f"docx-block-{block_index}",
        rows=tuple(rows),
        source=_location(source, block_index),
    )
