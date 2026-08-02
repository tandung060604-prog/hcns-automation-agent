"""File safety validation performed before parser selection."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath, PureWindowsPath
from zipfile import BadZipFile, ZipFile

from hcns_agent.application.format_detection import DetectionResult
from hcns_agent.domain.canonical import ParseWarning
from hcns_agent.domain.documents import SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.inspection import ImageInspector


@dataclass(frozen=True, slots=True)
class FileSafetyPolicy:
    allowed_formats: frozenset[SourceFormat] = frozenset(
        {
            SourceFormat.IMAGE,
            SourceFormat.PDF_TEXT,
            SourceFormat.PDF_SCAN,
            SourceFormat.DOCX,
            SourceFormat.XLSX,
            SourceFormat.PPTX,
            SourceFormat.PLAIN_TEXT,
        }
    )
    maximum_file_size: int = 25 * 1024 * 1024
    maximum_pdf_pages: int = 200
    maximum_archive_entries: int = 2_000
    maximum_uncompressed_ooxml_size: int = 250 * 1024 * 1024
    maximum_compression_ratio: float = 100.0
    reject_macro_enabled: bool = True
    reject_format_mismatch: bool = False


@dataclass(frozen=True, slots=True)
class SafetyValidationResult:
    warnings: tuple[ParseWarning, ...] = ()


class FileSafetyValidator:
    def __init__(
        self,
        image_inspector: ImageInspector,
        policy: FileSafetyPolicy | None = None,
    ) -> None:
        self._image_inspector = image_inspector
        self._policy = policy or FileSafetyPolicy()

    def validate(
        self, source: DocumentSource, detection: DetectionResult
    ) -> SafetyValidationResult:
        self.preflight(source)
        source_format = detection.source_format
        extension = PureWindowsPath(source.filename).suffix.lower()
        if detection.media_type == "application/x-ole-storage" and extension in {
            ".docx",
            ".xlsx",
            ".pptx",
            ".docm",
            ".xlsm",
            ".pptm",
        }:
            raise DocumentIntakeError(
                IntakeErrorCode.ENCRYPTED_DOCUMENT,
                "Encrypted Office container is not accepted",
            )

        if source_format in {SourceFormat.LEGACY_DOC, SourceFormat.LEGACY_XLS}:
            raise DocumentIntakeError(
                IntakeErrorCode.CONVERSION_REQUIRED,
                "Legacy Office format requires an approved conversion path",
            )
        if (
            source_format is SourceFormat.UNKNOWN
            or source_format not in self._policy.allowed_formats
        ):
            raise DocumentIntakeError(
                IntakeErrorCode.UNSUPPORTED_FORMAT,
                "Detected document format is not supported by policy",
            )

        if (
            self._policy.reject_format_mismatch
            and detection.warnings
            and any(warning.code.endswith("_CONTENT_MISMATCH") for warning in detection.warnings)
        ):
            raise DocumentIntakeError(
                IntakeErrorCode.FORMAT_MISMATCH,
                "Declared filename or media type does not match content",
            )

        if source_format in {SourceFormat.PDF_TEXT, SourceFormat.PDF_SCAN}:
            inspection = detection.pdf_inspection
            if inspection is None or inspection.corrupted:
                raise DocumentIntakeError(
                    IntakeErrorCode.CORRUPTED_FILE, "PDF could not be inspected safely"
                )
            if inspection.encrypted:
                raise DocumentIntakeError(
                    IntakeErrorCode.ENCRYPTED_DOCUMENT,
                    "Password-protected PDF is not accepted",
                )
            if inspection.page_count > self._policy.maximum_pdf_pages:
                raise DocumentIntakeError(
                    IntakeErrorCode.PDF_PAGE_LIMIT_EXCEEDED,
                    "PDF page count exceeds the configured safety limit",
                )

        if source_format is SourceFormat.IMAGE:
            image_inspection = self._image_inspector.inspect(source)
            if image_inspection.corrupted:
                raise DocumentIntakeError(
                    IntakeErrorCode.CORRUPTED_FILE, "Image could not be verified"
                )

        if source_format in {SourceFormat.DOCX, SourceFormat.XLSX, SourceFormat.PPTX}:
            self._validate_ooxml(source)

        return SafetyValidationResult()

    def preflight(self, source: DocumentSource) -> None:
        """Reject unsafe names and oversized bytes before any container parser runs."""
        self._validate_source_name(source.filename)
        if len(source.content) > self._policy.maximum_file_size:
            raise DocumentIntakeError(
                IntakeErrorCode.FILE_TOO_LARGE,
                "Document exceeds the configured maximum file size",
            )

    @staticmethod
    def _validate_source_name(filename: str) -> None:
        normalized = filename.replace("\\", "/")
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(filename)
        if (
            posix_path.is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or ".." in posix_path.parts
        ):
            raise DocumentIntakeError(
                IntakeErrorCode.INVALID_SOURCE,
                "Source filename contains an unsafe path",
            )

    def _validate_ooxml(self, source: DocumentSource) -> None:
        extension = PureWindowsPath(source.filename).suffix.lower()
        if extension in {".docm", ".xlsm", ".pptm"} and self._policy.reject_macro_enabled:
            raise DocumentIntakeError(
                IntakeErrorCode.MACRO_ENABLED_DOCUMENT,
                "Macro-enabled Office document extension is rejected",
            )
        try:
            with ZipFile(BytesIO(source.content)) as archive:
                entries = archive.infolist()
                if len(entries) > self._policy.maximum_archive_entries:
                    self._archive_limit_error("OOXML archive has too many entries")

                total_compressed = 0
                total_uncompressed = 0
                for entry in entries:
                    self._validate_archive_entry_name(entry.filename)
                    total_compressed += max(entry.compress_size, 1)
                    total_uncompressed += entry.file_size
                    if entry.file_size > 0 and entry.file_size / max(entry.compress_size, 1) > (
                        self._policy.maximum_compression_ratio
                    ):
                        self._archive_limit_error(
                            "OOXML archive entry exceeds compression ratio limit"
                        )
                    if entry.flag_bits & 0x1:
                        raise DocumentIntakeError(
                            IntakeErrorCode.ENCRYPTED_DOCUMENT,
                            "Encrypted OOXML archive entries are not accepted",
                        )
                    if (
                        entry.filename.replace("\\", "/").lower().endswith("vbaproject.bin")
                        and self._policy.reject_macro_enabled
                    ):
                        raise DocumentIntakeError(
                            IntakeErrorCode.MACRO_ENABLED_DOCUMENT,
                            "Macro-enabled Office documents are rejected",
                        )

                if total_uncompressed > self._policy.maximum_uncompressed_ooxml_size:
                    self._archive_limit_error("OOXML uncompressed size exceeds safety limit")
                if (
                    total_uncompressed > 0
                    and total_uncompressed / max(total_compressed, 1)
                    > self._policy.maximum_compression_ratio
                ):
                    self._archive_limit_error("OOXML archive expansion exceeds safety limit")
                corrupt_entry = archive.testzip()
                if corrupt_entry is not None:
                    raise DocumentIntakeError(
                        IntakeErrorCode.CORRUPTED_FILE,
                        "OOXML archive contains an entry with an invalid checksum",
                    )
        except BadZipFile as error:
            raise DocumentIntakeError(
                IntakeErrorCode.CORRUPTED_FILE, "OOXML archive is corrupted"
            ) from error

    @staticmethod
    def _validate_archive_entry_name(name: str) -> None:
        normalized = name.replace("\\", "/")
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(name)
        if (
            posix_path.is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or ".." in posix_path.parts
        ):
            raise DocumentIntakeError(
                IntakeErrorCode.DANGEROUS_ARCHIVE_PATH,
                "OOXML archive contains an unsafe path",
            )

    @staticmethod
    def _archive_limit_error(message: str) -> None:
        raise DocumentIntakeError(IntakeErrorCode.ARCHIVE_LIMIT_EXCEEDED, message)
