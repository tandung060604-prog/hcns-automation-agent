"""MinerU CLI challenger mapped into the vendor-neutral canonical model."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from hcns_agent.adapters.image_inspection import PillowImageInspector
from hcns_agent.adapters.pdf import PyMuPdfInspector
from hcns_agent.application.format_detection import FormatDetector
from hcns_agent.application.safety import FileSafetyValidator
from hcns_agent.application.understand_document import DocumentUnderstandingService
from hcns_agent.domain.canonical import (
    CanonicalDocument,
    DocumentContent,
    ModelManifest,
    Page,
    Paragraph,
    ParserProvenance,
    ParseWarning,
    SourceDescriptor,
    SourceLocation,
)
from hcns_agent.domain.documents import ParseStatus, SourceFormat
from hcns_agent.domain.understanding import IdpResult
from hcns_agent.ports.document_parser import DocumentSource


class MineruBenchmarkBackend:
    """Run the official local MinerU CLI with the pipeline backend."""

    def __init__(
        self,
        understanding: DocumentUnderstandingService,
        *,
        timeout_seconds: int = 900,
        device: str = "cpu",
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._understanding = understanding
        self._timeout_seconds = timeout_seconds
        self._device = device
        self._detector = FormatDetector(PyMuPdfInspector())
        self._safety = FileSafetyValidator(PillowImageInspector())

    @property
    def name(self) -> str:
        return "mineru-challenger"

    @property
    def version(self) -> str:
        try:
            return version("mineru")
        except PackageNotFoundError:
            return "not-installed"

    @property
    def model_identifiers(self) -> tuple[str, ...]:
        return ("mineru:pipeline", f"device:{self._device}")

    def process(
        self,
        source: DocumentSource,
        *,
        source_path: Path,
        output_directory: Path,
    ) -> IdpResult:
        executable = shutil.which("mineru")
        if executable is None:
            raise RuntimeError("MinerU CLI is not installed")
        self._safety.preflight(source)
        detection = self._detector.detect(source)
        safety = self._safety.validate(source, detection)
        if detection.source_format not in {
            SourceFormat.IMAGE,
            SourceFormat.PDF_TEXT,
            SourceFormat.PDF_SCAN,
        }:
            raise ValueError("The 30-50 page MinerU benchmark accepts PDF/image sources only")
        completed = subprocess.run(
            [
                executable,
                "-p",
                str(source_path),
                "-o",
                str(output_directory),
                "-b",
                "pipeline",
                "-m",
                "auto",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"MinerU CLI failed with exit code {completed.returncode}")
        content_path = _find_content_list(output_directory)
        pages = _load_pages(content_path, source.source_reference)
        status = ParseStatus.SUCCESS if any(page.blocks for page in pages) else ParseStatus.PARTIAL
        warnings = (*detection.warnings, *safety.warnings)
        if status is ParseStatus.PARTIAL:
            warnings = (
                *warnings,
                ParseWarning(
                    code="MINERU_NO_TEXT",
                    message="MinerU completed but produced no readable text blocks",
                ),
            )
        descriptor = SourceDescriptor(
            document_id=source.document_id,
            filename=source.filename,
            media_type=detection.media_type,
            size_bytes=len(source.content),
            checksum_sha256=hashlib.sha256(source.content).hexdigest(),
            source_reference=source.source_reference,
        )
        canonical = CanonicalDocument(
            document_id=source.document_id,
            source=descriptor,
            source_format=detection.source_format,
            content=DocumentContent(pages=pages),
            parse_status=status,
            provenance=(
                ParserProvenance(
                    parser_name="mineru/cli-pipeline",
                    parser_version=self.version,
                    source_format=detection.source_format,
                    model_manifest=ModelManifest(
                        engine="mineru",
                        version=self.version,
                        model_identifiers=self.model_identifiers,
                        device=self._device,
                    ),
                ),
            ),
            warnings=warnings,
        )
        return self._understanding.execute(canonical)


def _find_content_list(output_directory: Path) -> Path:
    candidates = sorted(output_directory.rglob("*_content_list_v2.json"))
    if not candidates:
        candidates = sorted(output_directory.rglob("*_content_list.json"))
    if len(candidates) != 1:
        raise ValueError("MinerU must emit exactly one supported content-list JSON file")
    return candidates[0]


def _load_pages(
    content_path: Path,
    source_reference: str | None,
) -> tuple[Page, ...]:
    try:
        payload: object = json.loads(content_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("MinerU content-list JSON is invalid") from error
    grouped: dict[int, list[str]] = defaultdict(list)
    for page_index, element in _iter_page_elements(payload):
        grouped[page_index].extend(_element_texts(element))
    return tuple(
        Page(
            page_index=page_index,
            blocks=tuple(
                Paragraph(
                    block_id=f"page-{page_index}-mineru-{block_index}",
                    text=text,
                    source=SourceLocation(
                        source_reference=source_reference,
                        page_index=page_index,
                        block_index=block_index,
                    ),
                )
                for block_index, text in enumerate(texts)
                if text.strip()
            ),
        )
        for page_index, texts in sorted(grouped.items())
    )


def _iter_page_elements(payload: object) -> Iterable[tuple[int, object]]:
    if isinstance(payload, dict):
        pages = payload.get("pages")
        if isinstance(pages, list):
            yield from _iter_page_elements(pages)
            return
        page_index = _page_index(payload, 0)
        for key in ("page_elements", "blocks", "content_list", "elements"):
            elements = payload.get(key)
            if isinstance(elements, list):
                for element in elements:
                    yield page_index, element
                return
        yield page_index, payload
        return
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            if isinstance(item, dict):
                page_index = _page_index(item, index)
                nested = next(
                    (
                        item[key]
                        for key in ("page_elements", "blocks", "content_list", "elements")
                        if isinstance(item.get(key), list)
                    ),
                    None,
                )
                if isinstance(nested, list):
                    for element in nested:
                        yield page_index, element
                else:
                    yield page_index, item


def _page_index(payload: dict[str, Any], fallback: int) -> int:
    value = payload.get("page_idx", payload.get("page_index", fallback))
    return value if isinstance(value, int) and value >= 0 else fallback


def _element_texts(element: object) -> list[str]:
    if isinstance(element, str):
        return [element] if element.strip() else []
    if isinstance(element, list):
        return [text for item in element for text in _element_texts(item)]
    if not isinstance(element, dict):
        return []
    for key in (
        "text",
        "content",
        "paragraph_content",
        "title_content",
        "table_body",
        "markdown",
    ):
        if key in element:
            texts = _element_texts(element[key])
            if texts:
                return texts
    for key in ("list_items", "children", "items"):
        if key in element:
            texts = _element_texts(element[key])
            if texts:
                return texts
    return []
