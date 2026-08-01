"""Native PDF text parsing, inspection, and bounded rasterization."""

from __future__ import annotations

from typing import Any

from hcns_agent.domain.canonical import (
    BoundingBox,
    CanonicalDocument,
    DocumentContent,
    ModelManifest,
    Page,
    Paragraph,
    ParserProvenance,
    ParseWarning,
    SourceLocation,
)
from hcns_agent.domain.documents import ParseStatus, SourceFormat
from hcns_agent.domain.errors import (
    DocumentIntakeError,
    ErrorKind,
    IntakeErrorCode,
)
from hcns_agent.ports.document_parser import (
    DocumentSource,
    ParseContext,
    ParserCapabilities,
)
from hcns_agent.ports.inspection import (
    PdfInspection,
    PdfPageRasterizer,
    RasterizedPage,
)
from hcns_agent.ports.ocr import OcrEngine


def _fitz() -> Any:
    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError("PyMuPDF is required for PDF inspection and parsing") from error
    return fitz


class PyMuPdfInspector:
    def __init__(self, minimum_text_characters: int = 8) -> None:
        self._minimum_text_characters = minimum_text_characters

    def inspect(self, source: DocumentSource) -> PdfInspection:
        fitz = _fitz()
        try:
            with fitz.open(stream=source.content, filetype="pdf") as document:
                encrypted = bool(document.needs_pass)
                page_count = int(document.page_count)
                if encrypted:
                    return PdfInspection(
                        page_count=page_count,
                        has_usable_text=False,
                        encrypted=True,
                    )
                text_characters = 0
                for page in document:
                    text_characters += sum(
                        1 for character in page.get_text("text") if not character.isspace()
                    )
                    if text_characters >= self._minimum_text_characters:
                        break
                return PdfInspection(
                    page_count=page_count,
                    has_usable_text=text_characters >= self._minimum_text_characters,
                )
        except Exception:
            return PdfInspection(
                page_count=0,
                has_usable_text=False,
                corrupted=True,
            )


class NativePdfDocumentParser:
    name = "pdf/pymupdf-native"
    version = "1.0.0"
    capabilities = ParserCapabilities(
        source_formats=frozenset({SourceFormat.PDF_TEXT}),
        preserves_layout=True,
    )

    def supports(self, source_format: SourceFormat) -> bool:
        return source_format in self.capabilities.source_formats

    def parse(self, source: DocumentSource, context: ParseContext) -> CanonicalDocument:
        fitz = _fitz()
        pages: list[Page] = []
        try:
            with fitz.open(stream=source.content, filetype="pdf") as document:
                for page_index, native_page in enumerate(document):
                    blocks: list[Paragraph] = []
                    for block_index, raw_block in enumerate(
                        native_page.get_text("blocks", sort=True)
                    ):
                        text = str(raw_block[4]).strip()
                        if not text:
                            continue
                        blocks.append(
                            Paragraph(
                                block_id=f"page-{page_index}-block-{block_index}",
                                text=text,
                                source=SourceLocation(
                                    source_reference=source.source_reference,
                                    page_index=page_index,
                                    block_index=block_index,
                                    bounding_box=BoundingBox(
                                        x0=float(raw_block[0]),
                                        y0=float(raw_block[1]),
                                        x1=float(raw_block[2]),
                                        y1=float(raw_block[3]),
                                        coordinate_space="PDF_POINT",
                                    ),
                                ),
                            )
                        )
                    pages.append(
                        Page(
                            page_index=page_index,
                            blocks=tuple(blocks),
                            width=float(native_page.rect.width),
                            height=float(native_page.rect.height),
                        )
                    )
        except Exception as error:
            raise DocumentIntakeError(
                IntakeErrorCode.PARSE_FAILED,
                "Native PDF parser failed",
                kind=ErrorKind.TECHNICAL,
                retryable=False,
            ) from error

        warnings: tuple[ParseWarning, ...] = ()
        status = ParseStatus.SUCCESS
        if not any(page.blocks for page in pages):
            warnings = (
                ParseWarning(
                    code="PDF_TEXT_EMPTY",
                    message="PDF text parser did not find readable text blocks",
                ),
            )
            status = ParseStatus.PARTIAL

        return CanonicalDocument(
            document_id=source.document_id,
            source=context.source_descriptor,
            source_format=context.source_format,
            content=DocumentContent(pages=tuple(pages)),
            parse_status=status,
            provenance=(
                ParserProvenance(
                    parser_name=self.name,
                    parser_version=self.version,
                    source_format=context.source_format,
                    metadata={"library": "PyMuPDF"},
                ),
            ),
            warnings=warnings,
        )


class PyMuPdfRasterizer:
    def __init__(self, *, dpi: int = 150, maximum_page_pixels: int = 40_000_000) -> None:
        if dpi <= 0:
            raise ValueError("dpi must be positive")
        self._dpi = dpi
        self._maximum_page_pixels = maximum_page_pixels

    def rasterize(self, source: DocumentSource) -> tuple[RasterizedPage, ...]:
        fitz = _fitz()
        rendered: list[RasterizedPage] = []
        try:
            with fitz.open(stream=source.content, filetype="pdf") as document:
                matrix = fitz.Matrix(self._dpi / 72.0, self._dpi / 72.0)
                for page_index, page in enumerate(document):
                    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                    if pixmap.width * pixmap.height > self._maximum_page_pixels:
                        raise DocumentIntakeError(
                            IntakeErrorCode.FILE_TOO_LARGE,
                            "Rasterized PDF page exceeds the configured pixel limit",
                        )
                    rendered.append(
                        RasterizedPage(
                            page_index=page_index,
                            content=pixmap.tobytes("png"),
                            width=int(pixmap.width),
                            height=int(pixmap.height),
                        )
                    )
        except DocumentIntakeError:
            raise
        except Exception as error:
            raise DocumentIntakeError(
                IntakeErrorCode.PARSE_FAILED,
                "PDF rasterization failed",
                kind=ErrorKind.TECHNICAL,
                retryable=False,
            ) from error
        return tuple(rendered)


class ScannedPdfDocumentParser:
    name = "pdf/scan-ocr"
    version = "1.0.0"
    capabilities = ParserCapabilities(
        source_formats=frozenset({SourceFormat.PDF_SCAN}),
        preserves_layout=True,
        uses_ocr=True,
    )

    def __init__(self, rasterizer: PdfPageRasterizer, ocr_engine: OcrEngine) -> None:
        self._rasterizer = rasterizer
        self._ocr_engine = ocr_engine

    def supports(self, source_format: SourceFormat) -> bool:
        return source_format in self.capabilities.source_formats

    def parse(self, source: DocumentSource, context: ParseContext) -> CanonicalDocument:
        pages: list[Page] = []
        manifest_data: dict[str, str] = {}
        engine_name = self._ocr_engine.name
        for rasterized in self._rasterizer.rasterize(source):
            page_source = DocumentSource(
                document_id=f"{source.document_id}-page-{rasterized.page_index}",
                filename=f"{source.document_id}-page-{rasterized.page_index}.png",
                content=rasterized.content,
                declared_media_type=rasterized.media_type,
                source_reference=source.source_reference,
            )
            result = self._ocr_engine.recognize(page_source)
            manifest_data = result.model_manifest
            blocks: list[Paragraph] = []
            block_index = 0
            for ocr_page in result.pages:
                for line in ocr_page.lines:
                    box = None
                    if line.box:
                        xs = [point[0] for point in line.box]
                        ys = [point[1] for point in line.box]
                        box = BoundingBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))
                    blocks.append(
                        Paragraph(
                            block_id=f"page-{rasterized.page_index}-ocr-{block_index}",
                            text=line.text,
                            confidence=line.confidence,
                            unreadable=not line.text.strip(),
                            source=SourceLocation(
                                source_reference=source.source_reference,
                                page_index=rasterized.page_index,
                                block_index=block_index,
                                bounding_box=box,
                            ),
                        )
                    )
                    block_index += 1
            pages.append(
                Page(
                    page_index=rasterized.page_index,
                    blocks=tuple(blocks),
                    width=float(rasterized.width),
                    height=float(rasterized.height),
                )
            )

        warnings: tuple[ParseWarning, ...] = ()
        status = ParseStatus.SUCCESS
        if not any(page.blocks for page in pages):
            warnings = (
                ParseWarning(
                    code="PDF_SCAN_OCR_NO_TEXT",
                    message="Scanned PDF OCR produced no readable text",
                ),
            )
            status = ParseStatus.PARTIAL

        manifest = ModelManifest(
            engine=engine_name,
            version=manifest_data.get("version", "unknown"),
            model_identifiers=tuple(
                value for key, value in sorted(manifest_data.items()) if "model" in key.lower()
            ),
            device=manifest_data.get("device"),
        )
        return CanonicalDocument(
            document_id=source.document_id,
            source=context.source_descriptor,
            source_format=context.source_format,
            content=DocumentContent(pages=tuple(pages)),
            parse_status=status,
            provenance=(
                ParserProvenance(
                    parser_name=self.name,
                    parser_version=self.version,
                    source_format=context.source_format,
                    model_manifest=manifest,
                    metadata={
                        "rasterizer": "PyMuPDF",
                        "ocrRoiEvidence": manifest_data.get("roiRecovery", "[]"),
                    },
                ),
            ),
            warnings=warnings,
        )
