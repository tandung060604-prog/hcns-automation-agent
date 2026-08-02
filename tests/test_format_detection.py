from unittest import TestCase

from synthetic_fixtures import (
    administrative_image_bytes,
    make_ooxml_zip,
    scanned_pdf_bytes,
    synthetic_contract_docx_bytes,
    synthetic_cv_pdf_bytes,
    synthetic_pptx_bytes,
    synthetic_timesheet_xlsx_bytes,
)

from hcns_agent.adapters.pdf import PyMuPdfInspector
from hcns_agent.application.format_detection import FormatDetector
from hcns_agent.domain.documents import SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import DocumentSource


class FormatDetectorTests(TestCase):
    def setUp(self) -> None:
        self.detector = FormatDetector(PyMuPdfInspector())

    def detect(self, filename: str, content: bytes, media_type: str | None = None) -> SourceFormat:
        result = self.detector.detect(
            DocumentSource(
                document_id="SYNTHETIC-DETECT",
                filename=filename,
                content=content,
                declared_media_type=media_type,
            )
        )
        return result.source_format

    def test_detects_image_signature(self) -> None:
        self.assertIs(
            SourceFormat.IMAGE,
            self.detect("upload.bin", administrative_image_bytes()),
        )

    def test_distinguishes_text_and_scanned_pdf(self) -> None:
        self.assertIs(
            SourceFormat.PDF_TEXT,
            self.detect("cv.bin", synthetic_cv_pdf_bytes()),
        )
        self.assertIs(
            SourceFormat.PDF_SCAN,
            self.detect("scan.bin", scanned_pdf_bytes()),
        )

    def test_detects_ooxml_by_container_content(self) -> None:
        self.assertIs(
            SourceFormat.DOCX,
            self.detect("upload.bin", synthetic_contract_docx_bytes()),
        )
        self.assertIs(
            SourceFormat.XLSX,
            self.detect("upload.bin", synthetic_timesheet_xlsx_bytes()),
        )
        self.assertIs(
            SourceFormat.PPTX,
            self.detect("upload.bin", synthetic_pptx_bytes()),
        )

    def test_extension_and_mime_mismatch_create_warnings(self) -> None:
        result = self.detector.detect(
            DocumentSource(
                document_id="SYNTHETIC-MISMATCH",
                filename="not-a-document.docx",
                content=administrative_image_bytes(),
                declared_media_type="application/pdf",
            )
        )

        self.assertEqual(
            {"EXTENSION_CONTENT_MISMATCH", "MIME_CONTENT_MISMATCH"},
            {warning.code for warning in result.warnings},
        )

    def test_unknown_format_is_explicit(self) -> None:
        self.assertIs(SourceFormat.UNKNOWN, self.detect("unknown.bin", b"synthetic"))

    def test_detects_utf8_plain_text_only_when_extension_is_txt(self) -> None:
        self.assertIs(SourceFormat.PLAIN_TEXT, self.detect("source.txt", "CV\nKỹ năng".encode()))
        self.assertIs(SourceFormat.UNKNOWN, self.detect("source.bin", "CV\nKỹ năng".encode()))

    def test_corrupted_zip_is_rejected(self) -> None:
        with self.assertRaises(DocumentIntakeError) as raised:
            self.detect("corrupt.docx", b"PK\x03\x04synthetic-corruption")

        self.assertIs(IntakeErrorCode.CORRUPTED_FILE, raised.exception.code)

    def test_zip_without_ooxml_structure_is_unknown(self) -> None:
        self.assertIs(
            SourceFormat.UNKNOWN,
            self.detect("archive.zip", make_ooxml_zip({"plain.txt": "synthetic"})),
        )
