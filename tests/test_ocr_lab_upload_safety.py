from __future__ import annotations

import unittest

from synthetic_fixtures import (
    administrative_image_bytes,
    encrypted_pdf_bytes,
    make_ooxml_zip,
)

from apps.ocr_lab.api.upload_safety import validate_local_upload
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode


class OcrLabUploadSafetyTests(unittest.TestCase):
    def test_accepts_a_valid_image_by_content(self) -> None:
        result = validate_local_upload(
            "synthetic.png",
            administrative_image_bytes(),
            declared_media_type="image/png",
        )

        self.assertEqual("IMAGE", result.detected_format)
        self.assertEqual("image/png", result.detected_media_type)

    def test_rejects_extension_content_mismatch(self) -> None:
        self.assert_rejected(
            IntakeErrorCode.FORMAT_MISMATCH,
            "synthetic.pdf",
            administrative_image_bytes(),
            "application/pdf",
        )

    def test_rejects_encrypted_pdf(self) -> None:
        self.assert_rejected(
            IntakeErrorCode.ENCRYPTED_DOCUMENT,
            "synthetic.pdf",
            encrypted_pdf_bytes(),
            "application/pdf",
        )

    def test_rejects_ooxml_macro_payload(self) -> None:
        content = make_ooxml_zip(
            {
                "word/document.xml": "<w:document/>",
                "word/vbaProject.bin": b"synthetic macro marker",
            }
        )
        self.assert_rejected(
            IntakeErrorCode.MACRO_ENABLED_DOCUMENT,
            "synthetic.docx",
            content,
            (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        )

    def test_rejects_submitted_path_traversal(self) -> None:
        self.assert_rejected(
            IntakeErrorCode.INVALID_SOURCE,
            "../synthetic.png",
            administrative_image_bytes(),
            "image/png",
        )

    def assert_rejected(
        self,
        expected_code: IntakeErrorCode,
        filename: str,
        content: bytes,
        media_type: str,
    ) -> None:
        with self.assertRaises(DocumentIntakeError) as raised:
            validate_local_upload(
                filename,
                content,
                declared_media_type=media_type,
            )
        self.assertIs(expected_code, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
