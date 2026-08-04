from dataclasses import replace
from unittest import TestCase

from synthetic_fixtures import (
    administrative_image_bytes,
    synthetic_contract_docx_bytes,
    synthetic_cv_pdf_bytes,
    synthetic_leave_request_docx_bytes,
    synthetic_xlsx_bytes,
)

from hcns_agent.adapters.classification import RuleBasedDocumentClassifier
from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.bootstrap import build_default_pipeline
from hcns_agent.domain.documents import DocumentType, SourceFormat
from hcns_agent.domain.models import FieldStatus
from hcns_agent.domain.understanding import QualityStatus
from hcns_agent.ports.document_parser import DocumentSource


class DocumentUnderstandingTests(TestCase):
    def parse(
        self,
        document_id: str,
        filename: str,
        content: bytes,
        *,
        ocr_text: str = "NOI DUNG OCR SYNTHETIC",
    ):
        pipeline = build_default_pipeline(DeterministicMockOcrEngine(text=ocr_text))
        return pipeline.execute(
            DocumentSource(
                document_id=document_id,
                filename=filename,
                content=content,
                source_reference=f"object://synthetic/{document_id}",
            )
        )

    def test_classifies_and_extracts_cv_with_page_provenance(self) -> None:
        result = self.parse("SYNTHETIC-CV-M2", "cv.pdf", synthetic_cv_pdf_bytes())

        self.assertIs(DocumentType.CV, result.classification.document_type)
        fields = {field.name: field for field in result.fields}
        self.assertEqual("NHAN_VIEN_SYNTHETIC_A", fields["full_name"].value)
        self.assertEqual("KIEM THU TAI LIEU", fields["skills"].value)
        self.assertEqual(0, fields["full_name"].evidence[0].source.page_index)
        self.assertIs(FieldStatus.NEEDS_REVIEW, fields["full_name"].status)
        self.assertIs(QualityStatus.REVIEW_REQUIRED, result.quality.status)

    def test_classifies_and_extracts_employment_contract(self) -> None:
        result = self.parse(
            "SYNTHETIC-CONTRACT-M2",
            "contract.docx",
            synthetic_contract_docx_bytes(),
        )

        self.assertIs(
            DocumentType.EMPLOYMENT_CONTRACT,
            result.classification.document_type,
        )
        fields = {field.name: field for field in result.fields}
        self.assertEqual("HD-SYNTHETIC-001", fields["contract_number"].value)
        self.assertEqual("2099-01-01", fields["start_date"].value)
        self.assertEqual("1000000", fields["salary"].value)
        self.assertIs(FieldStatus.NEEDS_REVIEW, fields["salary"].status)

    def test_classifies_and_extracts_leave_request(self) -> None:
        result = self.parse(
            "SYNTHETIC-LEAVE-M2",
            "leave-request.docx",
            synthetic_leave_request_docx_bytes(),
        )

        self.assertIs(
            DocumentType.LEAVE_REQUEST,
            result.classification.document_type,
        )
        fields = {field.name: field for field in result.fields}
        self.assertEqual("2099-02-01", fields["start_date"].value)
        self.assertEqual("2099-02-02", fields["end_date"].value)
        self.assertEqual(
            "KIEM THU QUY TRINH SYNTHETIC",
            fields["reason"].value,
        )

    def test_spreadsheet_without_approved_document_type_stays_reviewable(self) -> None:
        result = self.parse(
            "SYNTHETIC-SPREADSHEET-M2",
            "spreadsheet.xlsx",
            synthetic_xlsx_bytes(),
        )

        self.assertIs(DocumentType.UNKNOWN, result.classification.document_type)
        self.assertEqual((), result.fields)
        self.assertIs(QualityStatus.REVIEW_REQUIRED, result.quality.status)

    def test_supported_format_does_not_imply_supported_document_type(self) -> None:
        result = self.parse(
            "SYNTHETIC-UNKNOWN-M2",
            "form.png",
            administrative_image_bytes(),
            ocr_text="NOI DUNG KHONG XAC DINH",
        )

        self.assertIs(DocumentType.UNKNOWN, result.classification.document_type)
        self.assertEqual((), result.fields)
        self.assertIs(QualityStatus.REVIEW_REQUIRED, result.quality.status)
        self.assertIn(
            "UNKNOWN_DOCUMENT_TYPE",
            {issue.code for issue in result.quality.issues},
        )

    def test_classified_type_without_approved_extractor_requires_review(self) -> None:
        result = self.parse(
            "SYNTHETIC-ADMIN-M2",
            "form.png",
            administrative_image_bytes(),
            ocr_text="BIEU MAU HANH CHINH SYNTHETIC",
        )

        self.assertIs(
            DocumentType.ADMINISTRATIVE_FORM,
            result.classification.document_type,
        )
        self.assertIn(
            "NO_FIELD_EXTRACTOR",
            {issue.code for issue in result.quality.issues},
        )
        self.assertTrue(result.quality.review_required)

    def test_document_type_classification_is_independent_of_source_format(self) -> None:
        result = self.parse("SYNTHETIC-CV-FORMAT", "cv.pdf", synthetic_cv_pdf_bytes())
        same_content_other_format = replace(
            result.canonical_document,
            source_format=SourceFormat.IMAGE,
        )

        classification = RuleBasedDocumentClassifier().classify(same_content_other_format)

        self.assertIs(DocumentType.CV, classification.document_type)
