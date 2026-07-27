from dataclasses import replace
from unittest import TestCase

from synthetic_fixtures import (
    administrative_image_bytes,
    encrypted_pdf_bytes,
    make_ooxml_zip,
    synthetic_contract_docx_bytes,
    synthetic_cv_pdf_bytes,
)

from hcns_agent.adapters.image_inspection import PillowImageInspector
from hcns_agent.adapters.pdf import PyMuPdfInspector
from hcns_agent.application.format_detection import FormatDetector
from hcns_agent.application.safety import FileSafetyPolicy, FileSafetyValidator
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import DocumentSource


class FileSafetyValidatorTests(TestCase):
    def setUp(self) -> None:
        self.detector = FormatDetector(PyMuPdfInspector())

    def validate(
        self,
        source: DocumentSource,
        policy: FileSafetyPolicy | None = None,
    ) -> None:
        detection = self.detector.detect(source)
        FileSafetyValidator(PillowImageInspector(), policy).validate(source, detection)

    def assert_rejected(
        self,
        code: IntakeErrorCode,
        source: DocumentSource,
        policy: FileSafetyPolicy | None = None,
    ) -> None:
        with self.assertRaises(DocumentIntakeError) as raised:
            self.validate(source, policy)
        self.assertIs(code, raised.exception.code)

    def test_rejects_oversized_file(self) -> None:
        source = DocumentSource(
            "SYNTHETIC-SIZE",
            "form.png",
            administrative_image_bytes(),
        )
        self.assert_rejected(
            IntakeErrorCode.FILE_TOO_LARGE,
            source,
            replace(FileSafetyPolicy(), maximum_file_size=8),
        )

    def test_rejects_source_path_traversal(self) -> None:
        source = DocumentSource(
            "SYNTHETIC-PATH",
            "../form.png",
            administrative_image_bytes(),
        )
        self.assert_rejected(IntakeErrorCode.INVALID_SOURCE, source)

    def test_rejects_dangerous_zip_entry(self) -> None:
        content = make_ooxml_zip(
            {
                "word/document.xml": "<w:document/>",
                "../synthetic-payload.bin": b"not executable",
            }
        )
        source = DocumentSource("SYNTHETIC-ZIP-PATH", "contract.docx", content)
        self.assert_rejected(IntakeErrorCode.DANGEROUS_ARCHIVE_PATH, source)

    def test_rejects_excessive_archive_expansion(self) -> None:
        content = make_ooxml_zip({"word/document.xml": "A" * 200_000})
        source = DocumentSource("SYNTHETIC-ZIP-BOMB", "contract.docx", content)
        policy = replace(FileSafetyPolicy(), maximum_compression_ratio=10.0)
        self.assert_rejected(IntakeErrorCode.ARCHIVE_LIMIT_EXCEEDED, source, policy)

    def test_rejects_macro_enabled_ooxml(self) -> None:
        content = make_ooxml_zip(
            {
                "word/document.xml": "<w:document/>",
                "word/vbaProject.bin": b"synthetic macro marker",
            }
        )
        source = DocumentSource("SYNTHETIC-MACRO", "contract.docm", content)
        self.assert_rejected(IntakeErrorCode.MACRO_ENABLED_DOCUMENT, source)

    def test_rejects_macro_enabled_extension_without_macro_payload(self) -> None:
        source = DocumentSource(
            "SYNTHETIC-MACRO-EXTENSION",
            "contract.docm",
            synthetic_contract_docx_bytes(),
        )
        self.assert_rejected(IntakeErrorCode.MACRO_ENABLED_DOCUMENT, source)

    def test_rejects_encrypted_office_container(self) -> None:
        content = bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 64
        source = DocumentSource("SYNTHETIC-OFFICE-ENCRYPTED", "contract.docx", content)
        self.assert_rejected(IntakeErrorCode.ENCRYPTED_DOCUMENT, source)

    def test_rejects_excessive_archive_entry_count(self) -> None:
        content = make_ooxml_zip(
            {
                "word/document.xml": "<w:document/>",
                "word/extra.xml": "<synthetic/>",
            }
        )
        source = DocumentSource("SYNTHETIC-ZIP-COUNT", "contract.docx", content)
        policy = replace(FileSafetyPolicy(), maximum_archive_entries=1)
        self.assert_rejected(IntakeErrorCode.ARCHIVE_LIMIT_EXCEEDED, source, policy)

    def test_rejects_unsupported_legacy_format(self) -> None:
        content = bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 64
        source = DocumentSource("SYNTHETIC-LEGACY", "contract.doc", content)
        self.assert_rejected(IntakeErrorCode.CONVERSION_REQUIRED, source)

    def test_rejects_password_protected_pdf(self) -> None:
        source = DocumentSource(
            "SYNTHETIC-ENCRYPTED",
            "encrypted.pdf",
            encrypted_pdf_bytes(),
        )
        self.assert_rejected(IntakeErrorCode.ENCRYPTED_DOCUMENT, source)

    def test_rejects_pdf_page_limit(self) -> None:
        source = DocumentSource(
            "SYNTHETIC-PAGES",
            "cv.pdf",
            synthetic_cv_pdf_bytes(),
        )
        policy = replace(FileSafetyPolicy(), maximum_pdf_pages=0)
        self.assert_rejected(IntakeErrorCode.PDF_PAGE_LIMIT_EXCEEDED, source, policy)

    def test_policy_can_reject_extension_mismatch(self) -> None:
        source = DocumentSource(
            "SYNTHETIC-MISMATCH",
            "form.docx",
            administrative_image_bytes(),
        )
        policy = replace(FileSafetyPolicy(), reject_format_mismatch=True)
        self.assert_rejected(IntakeErrorCode.FORMAT_MISMATCH, source, policy)

    def test_valid_synthetic_docx_passes(self) -> None:
        self.validate(
            DocumentSource(
                "SYNTHETIC-DOCX",
                "contract.docx",
                synthetic_contract_docx_bytes(),
            )
        )
