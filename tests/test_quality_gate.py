from unittest import TestCase

from hcns_agent.application.quality_gate import ValidationQualityGate
from hcns_agent.domain.canonical import (
    CanonicalDocument,
    DocumentContent,
    Page,
    Paragraph,
    ParserProvenance,
    SourceDescriptor,
    SourceLocation,
)
from hcns_agent.domain.documents import DocumentType, ParseStatus, SourceFormat
from hcns_agent.domain.models import FieldStatus
from hcns_agent.domain.understanding import (
    BusinessField,
    ClassificationCandidate,
    DocumentClassification,
    FieldEvidence,
    QualityStatus,
)


class ValidationQualityGateTests(TestCase):
    def setUp(self) -> None:
        self.document = _canonical_document()
        self.classification = DocumentClassification(
            document_type=DocumentType.CV,
            confidence=0.90,
            candidates=(
                ClassificationCandidate(
                    document_type=DocumentType.CV,
                    confidence=0.90,
                    matched_markers=("cv",),
                ),
            ),
            evidence=(SourceLocation(page_index=0, block_index=0),),
            classifier_name="synthetic/classifier",
            classifier_version="1.0.0",
        )

    def test_low_confidence_and_sensitive_fields_require_review(self) -> None:
        fields = (
            _field("full_name", "NHAN_VIEN_SYNTHETIC_C", 0.96, sensitive=True),
            _field("skills", "KIEM THU", 0.50),
        )

        validated, report = ValidationQualityGate().evaluate(
            self.document,
            self.classification,
            fields,
            extractor_available=True,
        )

        statuses = {field.name: field.status for field in validated}
        self.assertIs(FieldStatus.NEEDS_REVIEW, statuses["full_name"])
        self.assertIs(FieldStatus.NEEDS_REVIEW, statuses["skills"])
        self.assertIs(QualityStatus.REVIEW_REQUIRED, report.status)
        self.assertIn("LOW_FIELD_CONFIDENCE", {issue.code for issue in report.issues})

    def test_missing_required_field_is_reported(self) -> None:
        _, report = ValidationQualityGate().evaluate(
            self.document,
            self.classification,
            (_field("full_name", "NHAN_VIEN_SYNTHETIC_C", 0.96),),
            extractor_available=True,
        )

        missing = [
            issue.field_name for issue in report.issues if issue.code == "REQUIRED_FIELD_MISSING"
        ]
        self.assertEqual(["skills"], missing)
        self.assertTrue(report.review_required)

    def test_conflicting_values_are_invalid(self) -> None:
        fields = (
            _field("full_name", "NHAN_VIEN_SYNTHETIC_C", 0.96),
            _field("full_name", "NHAN_VIEN_SYNTHETIC_D", 0.96),
            _field("skills", "KIEM THU", 0.96),
        )

        validated, report = ValidationQualityGate().evaluate(
            self.document,
            self.classification,
            fields,
            extractor_available=True,
        )

        self.assertTrue(
            all(
                field.status is FieldStatus.INVALID
                for field in validated
                if field.name == "full_name"
            )
        )
        self.assertIn("FIELD_CONFLICT", {issue.code for issue in report.issues})

    def test_invalid_date_range_is_detected(self) -> None:
        classification = DocumentClassification(
            document_type=DocumentType.LEAVE_REQUEST,
            confidence=0.90,
            candidates=(
                ClassificationCandidate(
                    document_type=DocumentType.LEAVE_REQUEST,
                    confidence=0.90,
                    matched_markers=("don nghi phep",),
                ),
            ),
            evidence=(SourceLocation(page_index=0, block_index=0),),
            classifier_name="synthetic/classifier",
            classifier_version="1.0.0",
        )
        fields = (
            _field("employee_name", "NHAN_VIEN_SYNTHETIC_C", 0.96),
            _field("start_date", "2099-03-05", 0.96),
            _field("end_date", "2099-03-01", 0.96),
            _field("reason", "KIEM THU SYNTHETIC", 0.96),
        )

        validated, report = ValidationQualityGate().evaluate(
            self.document,
            classification,
            fields,
            extractor_available=True,
        )

        self.assertIn("DATE_RANGE_CONFLICT", {issue.code for issue in report.issues})
        date_statuses = {
            field.status for field in validated if field.name in {"start_date", "end_date"}
        }
        self.assertEqual({FieldStatus.INVALID}, date_statuses)


def _canonical_document() -> CanonicalDocument:
    source = SourceDescriptor(
        document_id="SYNTHETIC-QUALITY",
        filename="quality.pdf",
        media_type="application/pdf",
        size_bytes=1,
        checksum_sha256="0" * 64,
    )
    return CanonicalDocument(
        document_id=source.document_id,
        source=source,
        source_format=SourceFormat.PDF_TEXT,
        content=DocumentContent(
            pages=(
                Page(
                    page_index=0,
                    blocks=(
                        Paragraph(
                            block_id="block-0",
                            text="CV SYNTHETIC",
                            source=SourceLocation(page_index=0, block_index=0),
                        ),
                    ),
                ),
            )
        ),
        parse_status=ParseStatus.SUCCESS,
        provenance=(
            ParserProvenance(
                parser_name="synthetic/parser",
                parser_version="1.0.0",
                source_format=SourceFormat.PDF_TEXT,
            ),
        ),
    )


def _field(
    name: str,
    value: str,
    confidence: float,
    *,
    sensitive: bool = False,
) -> BusinessField:
    return BusinessField(
        name=name,
        value=value,
        confidence=confidence,
        status=FieldStatus.ACCEPTED,
        sensitive=sensitive,
        evidence=(
            FieldEvidence(
                source=SourceLocation(page_index=0, block_index=0),
                method="synthetic-test",
            ),
        ),
        extractor_name="synthetic/extractor",
        extractor_version="1.0.0",
    )
