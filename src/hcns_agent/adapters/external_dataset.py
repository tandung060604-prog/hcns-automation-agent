"""Vendor-backed page counting for external dataset inventory."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from hcns_agent.application.external_dataset import ExternalDatasetError
from hcns_agent.domain.documents import SourceFormat


def count_source_format_and_pages(path: Path, content: bytes) -> tuple[SourceFormat, int]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz  # type: ignore[import-untyped]

            with fitz.open(stream=content, filetype="pdf") as document:
                if document.needs_pass:
                    raise ExternalDatasetError(f"Encrypted PDF is not accepted: {path.name}")
                page_count = int(document.page_count)
                page_has_text = [
                    sum(1 for character in page.get_text("text") if not character.isspace()) >= 8
                    for page in document
                ]
        except ExternalDatasetError:
            raise
        except Exception as error:
            raise ExternalDatasetError(f"Invalid PDF source: {path.name}") from error
        is_native = bool(page_has_text) and all(page_has_text)
        return (SourceFormat.PDF_TEXT if is_native else SourceFormat.PDF_SCAN), page_count
    if suffix in {".png", ".jpg", ".jpeg"}:
        try:
            from PIL import Image

            with Image.open(BytesIO(content)) as image:
                image.verify()
        except Exception as error:
            raise ExternalDatasetError(f"Invalid image source: {path.name}") from error
        return SourceFormat.IMAGE, 1
    if suffix == ".txt":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ExternalDatasetError(f"TXT source is not UTF-8: {path.name}") from error
        return SourceFormat.PLAIN_TEXT, 1
    if suffix == ".pptx":
        return SourceFormat.PPTX, _count_zip_parts(path, content, "ppt/slides/slide", ".xml")
    if suffix == ".docx":
        try:
            with ZipFile(BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ExternalDatasetError(f"Invalid DOCX source: {path.name}")
        except (BadZipFile, OSError) as error:
            raise ExternalDatasetError(f"Invalid DOCX source: {path.name}") from error
        return SourceFormat.DOCX, 1
    raise ExternalDatasetError(f"Unsupported dataset suffix: {suffix}")


def _count_zip_parts(path: Path, content: bytes, prefix: str, suffix: str) -> int:
    try:
        with ZipFile(BytesIO(content)) as archive:
            count = sum(
                1
                for name in archive.namelist()
                if name.startswith(prefix) and name.endswith(suffix)
            )
    except (BadZipFile, OSError) as error:
        raise ExternalDatasetError(f"Invalid OOXML source: {path.name}") from error
    return max(1, count)
