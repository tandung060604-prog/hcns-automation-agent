"""Local-only benchmark backend adapters and physical page counting."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from pathlib import Path

from hcns_agent.application.understand_document import IdpPipeline
from hcns_agent.domain.understanding import IdpResult
from hcns_agent.ports.document_parser import DocumentSource


class PaddleBenchmarkBackend:
    """Execute the normal intake and M2 understanding pipeline with PaddleOCR."""

    def __init__(self, pipeline: IdpPipeline, *, device: str = "cpu") -> None:
        self._pipeline = pipeline
        self._device = device

    @property
    def name(self) -> str:
        return "paddleocr-baseline"

    @property
    def version(self) -> str:
        return _package_version("paddleocr")

    @property
    def model_identifiers(self) -> tuple[str, ...]:
        return (
            "PP-OCRv5_mobile_det",
            "latin_PP-OCRv5_mobile_rec",
            f"device:{self._device}",
        )

    def process(
        self,
        source: DocumentSource,
        *,
        source_path: Path,
        output_directory: Path,
    ) -> IdpResult:
        del source_path, output_directory
        return self._pipeline.execute(source)


class LocalSourcePageCounter:
    """Count PDF pages or image frames using already-required local libraries."""

    def count_pages(self, source: DocumentSource) -> int:
        if source.content.startswith(b"%PDF-"):
            return self._pdf_pages(source.content)
        return self._image_pages(source.content)

    @staticmethod
    def _pdf_pages(content: bytes) -> int:
        try:
            import fitz  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError("PyMuPDF is required for benchmark page counting") from error
        try:
            with fitz.open(stream=content, filetype="pdf") as document:
                if document.needs_pass:
                    raise ValueError("Encrypted PDFs cannot be benchmarked")
                return int(document.page_count)
        except ValueError:
            raise
        except Exception as error:
            raise ValueError("Benchmark source is not a valid PDF") from error

    @staticmethod
    def _image_pages(content: bytes) -> int:
        try:
            from PIL import Image
        except ImportError as error:
            raise RuntimeError("Pillow is required for benchmark page counting") from error
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
            with Image.open(BytesIO(content)) as image:
                return int(getattr(image, "n_frames", 1))
        except Exception as error:
            raise ValueError("Benchmark sources must be valid PDF or image files") from error


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not-installed"
