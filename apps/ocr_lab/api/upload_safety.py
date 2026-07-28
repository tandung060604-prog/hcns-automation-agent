"""Content-based safety preflight for OCR Lab uploads."""

from __future__ import annotations

from dataclasses import dataclass

from hcns_agent.adapters.image_inspection import PillowImageInspector
from hcns_agent.adapters.pdf import PyMuPdfInspector
from hcns_agent.application.format_detection import FormatDetector
from hcns_agent.application.safety import FileSafetyPolicy, FileSafetyValidator
from hcns_agent.ports.document_parser import DocumentSource

OCR_LAB_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
OCR_LAB_MAX_PDF_PAGES = 50


@dataclass(frozen=True, slots=True)
class SafeUpload:
    detected_format: str
    detected_media_type: str | None


def validate_local_upload(
    filename: str,
    content: bytes,
    *,
    declared_media_type: str | None = None,
) -> SafeUpload:
    """Reject mismatched, encrypted, corrupted, macro or explosive inputs."""

    source = DocumentSource(
        document_id="local-upload-preflight",
        filename=filename,
        content=content,
        declared_media_type=declared_media_type,
    )
    detector = FormatDetector(PyMuPdfInspector())
    detection = detector.detect(source)
    validator = FileSafetyValidator(
        PillowImageInspector(),
        FileSafetyPolicy(
            maximum_file_size=OCR_LAB_MAX_UPLOAD_BYTES,
            maximum_pdf_pages=OCR_LAB_MAX_PDF_PAGES,
            reject_format_mismatch=True,
        ),
    )
    validator.validate(source, detection)
    return SafeUpload(
        detected_format=detection.source_format.value,
        detected_media_type=detection.media_type,
    )
