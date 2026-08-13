"""Image parser that maps OCR observations into the canonical model."""

from __future__ import annotations

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
from hcns_agent.ports.document_parser import (
    DocumentSource,
    ParseContext,
    ParserCapabilities,
)
from hcns_agent.ports.ocr import OcrEngine, OcrLine


class ImageDocumentParser:
    name = "image/ocr"
    version = "1.0.0"
    capabilities = ParserCapabilities(
        source_formats=frozenset({SourceFormat.IMAGE}),
        preserves_layout=True,
        uses_ocr=True,
    )

    def __init__(self, ocr_engine: OcrEngine) -> None:
        self._ocr_engine = ocr_engine

    def supports(self, source_format: SourceFormat) -> bool:
        return source_format in self.capabilities.source_formats

    def parse(self, source: DocumentSource, context: ParseContext) -> CanonicalDocument:
        result = self._ocr_engine.recognize(source)
        pages: list[Page] = []
        for ocr_page in result.pages:
            blocks = tuple(
                _line_to_paragraph(
                    line,
                    page_index=ocr_page.page_index,
                    block_index=line_index,
                    source_reference=source.source_reference,
                )
                for line_index, line in enumerate(ocr_page.lines)
            )
            pages.append(Page(page_index=ocr_page.page_index, blocks=blocks))

        warnings: tuple[ParseWarning, ...] = ()
        status = ParseStatus.SUCCESS
        if not any(page.blocks for page in pages):
            warnings = (
                ParseWarning(
                    code="OCR_NO_TEXT",
                    message="OCR completed but produced no readable text",
                ),
            )
            status = ParseStatus.PARTIAL

        manifest = ModelManifest(
            engine=result.engine,
            version=result.model_manifest.get("version", "unknown"),
            model_identifiers=tuple(
                value
                for key, value in sorted(result.model_manifest.items())
                if "model" in key.lower()
            ),
            device=result.model_manifest.get("device"),
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
                        "ocrDurationMs": result.duration_ms,
                        "ocrRoiEvidence": result.model_manifest.get(
                            "roiRecovery", "[]"
                        )
                    },
                ),
            ),
            warnings=warnings,
        )


def _line_to_paragraph(
    line: OcrLine,
    *,
    page_index: int,
    block_index: int,
    source_reference: str | None,
) -> Paragraph:
    box = _bounding_box(line)
    return Paragraph(
        block_id=f"page-{page_index}-ocr-{block_index}",
        text=line.text,
        confidence=line.confidence,
        unreadable=not line.text.strip(),
        source=SourceLocation(
            source_reference=source_reference,
            page_index=page_index,
            block_index=block_index,
            bounding_box=box,
        ),
    )


def _bounding_box(line: OcrLine) -> BoundingBox | None:
    if not line.box:
        return None
    xs = [point[0] for point in line.box]
    ys = [point[1] for point in line.box]
    return BoundingBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))
