"""Canonical Document Model shared by all document parsers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

from hcns_agent.domain.documents import ParseStatus, SourceFormat, WarningSeverity

ScalarValue: TypeAlias = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float
    coordinate_space: str = "PIXEL"

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("BoundingBox coordinates must be ordered")


@dataclass(frozen=True, slots=True)
class SourceLocation:
    source_reference: str | None = None
    page_index: int | None = None
    block_index: int | None = None
    sheet_name: str | None = None
    row_index: int | None = None
    column_index: int | None = None
    bounding_box: BoundingBox | None = None


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    document_id: str
    filename: str
    media_type: str | None
    size_bytes: int
    checksum_sha256: str
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id must not be empty")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")


@dataclass(frozen=True, slots=True)
class ModelManifest:
    engine: str
    version: str
    model_identifiers: tuple[str, ...] = ()
    parameters_hash: str | None = None
    device: str | None = None


@dataclass(frozen=True, slots=True)
class ParserProvenance:
    parser_name: str
    parser_version: str
    source_format: SourceFormat
    model_manifest: ModelManifest | None = None
    metadata: dict[str, ScalarValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParseWarning:
    code: str
    message: str
    severity: WarningSeverity = WarningSeverity.WARNING
    source: SourceLocation | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentBlock:
    block_id: str
    source: SourceLocation
    confidence: float | None = None
    unreadable: bool = False

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class Paragraph(ContentBlock):
    text: str = ""
    style: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Heading(ContentBlock):
    text: str = ""
    level: int = 1
    style: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ListBlock(ContentBlock):
    items: tuple[str, ...] = ()
    ordered: bool = False


@dataclass(frozen=True, slots=True)
class TableCell:
    row_index: int
    column_index: int
    text: str
    source: SourceLocation
    row_span: int = 1
    column_span: int = 1


@dataclass(frozen=True, slots=True)
class TableRow:
    row_index: int
    cells: tuple[TableCell, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Table(ContentBlock):
    rows: tuple[TableRow, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddedImage(ContentBlock):
    media_type: str | None = None
    relationship_id: str | None = None
    alt_text: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class KeyValue(ContentBlock):
    key: str = ""
    value: str = ""


@dataclass(frozen=True, slots=True)
class SpreadsheetCell:
    row_index: int
    column_index: int
    coordinate: str
    value: ScalarValue
    data_type: str
    formula: str | None
    source: SourceLocation


@dataclass(frozen=True, slots=True)
class SpreadsheetRow:
    row_index: int
    cells: tuple[SpreadsheetCell, ...]


@dataclass(frozen=True, slots=True)
class Sheet:
    name: str
    index: int
    rows: tuple[SpreadsheetRow, ...]
    merged_ranges: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Workbook:
    sheets: tuple[Sheet, ...]
    properties: dict[str, ScalarValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Page:
    page_index: int
    blocks: tuple[ContentBlock, ...]
    width: float | None = None
    height: float | None = None


@dataclass(frozen=True, slots=True)
class DocumentContent:
    pages: tuple[Page, ...] = ()
    blocks: tuple[ContentBlock, ...] = ()
    workbook: Workbook | None = None


@dataclass(frozen=True, slots=True)
class ResultReference:
    uri: str
    checksum_sha256: str
    schema_version: str
    storage_version: str


@dataclass(frozen=True, slots=True)
class CanonicalDocument:
    document_id: str
    source: SourceDescriptor
    source_format: SourceFormat
    content: DocumentContent
    parse_status: ParseStatus
    provenance: tuple[ParserProvenance, ...]
    warnings: tuple[ParseWarning, ...] = ()
    metadata: dict[str, ScalarValue] = field(default_factory=dict)
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if self.document_id != self.source.document_id:
            raise ValueError("CanonicalDocument and source document IDs must match")
        if not self.provenance:
            raise ValueError("CanonicalDocument requires parser provenance")
