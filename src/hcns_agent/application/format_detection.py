"""Content-based source format detection."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

from hcns_agent.domain.canonical import ParseWarning
from hcns_agent.domain.documents import SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.inspection import PdfInspection, PdfInspector

_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)

_EXTENSION_FORMATS = {
    ".txt": {SourceFormat.PLAIN_TEXT},
    ".pdf": {SourceFormat.PDF_TEXT, SourceFormat.PDF_SCAN},
    ".docx": {SourceFormat.DOCX},
    ".xlsx": {SourceFormat.XLSX},
    ".pptx": {SourceFormat.PPTX},
    ".doc": {SourceFormat.LEGACY_DOC},
    ".xls": {SourceFormat.LEGACY_XLS},
    ".jpg": {SourceFormat.IMAGE},
    ".jpeg": {SourceFormat.IMAGE},
    ".png": {SourceFormat.IMAGE},
    ".tif": {SourceFormat.IMAGE},
    ".tiff": {SourceFormat.IMAGE},
    ".webp": {SourceFormat.IMAGE},
}

_MIME_FORMATS = {
    "application/pdf": {SourceFormat.PDF_TEXT, SourceFormat.PDF_SCAN},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {SourceFormat.DOCX},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {SourceFormat.XLSX},
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": {
        SourceFormat.PPTX
    },
}


@dataclass(frozen=True, slots=True)
class DetectionResult:
    source_format: SourceFormat
    media_type: str | None
    warnings: tuple[ParseWarning, ...] = ()
    pdf_inspection: PdfInspection | None = None


class FormatDetector:
    def __init__(self, pdf_inspector: PdfInspector) -> None:
        self._pdf_inspector = pdf_inspector

    def detect(self, source: DocumentSource) -> DetectionResult:
        header = source.content[:16]
        pdf_inspection: PdfInspection | None = None
        media_type: str | None

        if header.startswith(b"%PDF-"):
            pdf_inspection = self._pdf_inspector.inspect(source)
            if pdf_inspection.corrupted:
                raise DocumentIntakeError(
                    IntakeErrorCode.CORRUPTED_FILE, "PDF structure is corrupted"
                )
            detected = (
                SourceFormat.PDF_TEXT if pdf_inspection.has_usable_text else SourceFormat.PDF_SCAN
            )
            media_type = "application/pdf"
        elif image_media_type := _detect_image_media_type(source.content):
            detected = SourceFormat.IMAGE
            media_type = image_media_type
        elif header.startswith(b"PK"):
            detected, media_type = self._detect_ooxml(source)
        elif header.startswith(_OLE_SIGNATURE):
            extension = PurePath(source.filename).suffix.lower()
            detected = (
                SourceFormat.LEGACY_XLS
                if extension == ".xls"
                else SourceFormat.LEGACY_DOC
                if extension == ".doc"
                else SourceFormat.UNKNOWN
            )
            media_type = "application/x-ole-storage"
        elif (
            _looks_like_utf8_text(source.content)
            and PurePath(source.filename).suffix.lower() == ".txt"
        ):
            detected = SourceFormat.PLAIN_TEXT
            media_type = "text/plain"
        else:
            detected = SourceFormat.UNKNOWN
            media_type = None

        warnings = self._mismatch_warnings(source, detected)
        return DetectionResult(
            source_format=detected,
            media_type=media_type,
            warnings=warnings,
            pdf_inspection=pdf_inspection,
        )

    @staticmethod
    def _detect_ooxml(source: DocumentSource) -> tuple[SourceFormat, str | None]:
        try:
            with ZipFile(BytesIO(source.content)) as archive:
                names = tuple(name.replace("\\", "/").lower() for name in archive.namelist())
        except BadZipFile as error:
            raise DocumentIntakeError(
                IntakeErrorCode.CORRUPTED_FILE, "ZIP/OOXML structure is corrupted"
            ) from error

        if any(name.startswith("word/") for name in names):
            return (
                SourceFormat.DOCX,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        if any(name.startswith("xl/") for name in names):
            return (
                SourceFormat.XLSX,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        if any(name.startswith("ppt/") for name in names):
            return (
                SourceFormat.PPTX,
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        return SourceFormat.UNKNOWN, "application/zip"

    @staticmethod
    def _mismatch_warnings(
        source: DocumentSource, detected: SourceFormat
    ) -> tuple[ParseWarning, ...]:
        warnings: list[ParseWarning] = []
        extension = PurePath(source.filename).suffix.lower()
        expected_by_extension = _EXTENSION_FORMATS.get(extension)
        if expected_by_extension is not None and detected not in expected_by_extension:
            warnings.append(
                ParseWarning(
                    code="EXTENSION_CONTENT_MISMATCH",
                    message="Filename extension does not match detected content",
                )
            )

        if source.declared_media_type:
            normalized_mime = source.declared_media_type.split(";", maxsplit=1)[0].strip().lower()
            expected_by_mime = _formats_for_mime(normalized_mime)
            if expected_by_mime is not None and detected not in expected_by_mime:
                warnings.append(
                    ParseWarning(
                        code="MIME_CONTENT_MISMATCH",
                        message="Declared media type does not match detected content",
                    )
                )
        return tuple(warnings)


def _detect_image_media_type(content: bytes) -> str | None:
    for signature, media_type in _IMAGE_SIGNATURES:
        if content.startswith(signature):
            return media_type
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _looks_like_utf8_text(content: bytes) -> bool:
    if not content or b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _formats_for_mime(media_type: str) -> set[SourceFormat] | None:
    if media_type.startswith("image/"):
        return {SourceFormat.IMAGE}
    return _MIME_FORMATS.get(media_type)
