from dataclasses import fields, is_dataclass
from unittest import TestCase

from synthetic_fixtures import (
    administrative_image_bytes,
    scanned_pdf_bytes,
    synthetic_contract_docx_bytes,
    synthetic_cv_pdf_bytes,
    synthetic_pptx_bytes,
    synthetic_xlsx_bytes,
)

from hcns_agent.adapters.docx import DocxDocumentParser
from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.adapters.pdf import NativePdfDocumentParser
from hcns_agent.adapters.xlsx import XlsxDocumentParser
from hcns_agent.application.parser_registry import DocumentParserRegistry
from hcns_agent.bootstrap import build_default_intake
from hcns_agent.domain.canonical import (
    Heading,
    ListBlock,
    Paragraph,
    Table,
)
from hcns_agent.domain.documents import ParseStatus, SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError, IntakeErrorCode
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrResult


class _SpyOcrEngine:
    def __init__(self) -> None:
        self._delegate = DeterministicMockOcrEngine(
            text="NOI DUNG OCR SYNTHETIC",
            confidence=0.93,
        )
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._delegate.name

    def recognize(self, source: DocumentSource) -> OcrResult:
        self.calls.append(source.filename)
        return self._delegate.recognize(source)


class DocumentParserContractTests(TestCase):
    def setUp(self) -> None:
        self.ocr = _SpyOcrEngine()
        self.intake = build_default_intake(self.ocr)

    def parse(self, document_id: str, filename: str, content: bytes):
        return self.intake.execute(
            DocumentSource(
                document_id=document_id,
                filename=filename,
                content=content,
                source_reference=f"object://synthetic/{document_id}",
            )
        )

    def test_image_routes_to_ocr_and_preserves_text_confidence_and_box(self) -> None:
        document = self.parse(
            "SYNTHETIC-IMAGE",
            "form.png",
            administrative_image_bytes(),
        )

        block = document.content.pages[0].blocks[0]
        self.assertIs(SourceFormat.IMAGE, document.source_format)
        self.assertEqual("NOI DUNG OCR SYNTHETIC", block.text)
        self.assertEqual(0.93, block.confidence)
        self.assertIsNotNone(block.source.bounding_box)
        self.assertEqual(1, len(self.ocr.calls))
        self.assertEqual("mock/deterministic-v1", document.provenance[0].model_manifest.engine)

    def test_text_pdf_uses_native_parser_and_preserves_page_index(self) -> None:
        document = self.parse(
            "SYNTHETIC-CV",
            "cv.pdf",
            synthetic_cv_pdf_bytes(),
        )

        self.assertIs(SourceFormat.PDF_TEXT, document.source_format)
        self.assertEqual(0, document.content.pages[0].page_index)
        self.assertEqual(0, document.content.pages[0].blocks[0].source.page_index)
        self.assertIn("CV SYNTHETIC", document.content.pages[0].blocks[0].text)
        self.assertEqual([], self.ocr.calls)

    def test_scanned_pdf_routes_each_page_to_ocr(self) -> None:
        document = self.parse(
            "SYNTHETIC-SCAN",
            "scan.pdf",
            scanned_pdf_bytes(),
        )

        self.assertIs(SourceFormat.PDF_SCAN, document.source_format)
        self.assertEqual(0, document.content.pages[0].page_index)
        self.assertEqual("NOI DUNG OCR SYNTHETIC", document.content.pages[0].blocks[0].text)
        self.assertEqual(1, len(self.ocr.calls))

    def test_docx_preserves_heading_paragraph_list_and_table(self) -> None:
        document = self.parse(
            "SYNTHETIC-CONTRACT",
            "contract.docx",
            synthetic_contract_docx_bytes(),
        )

        blocks = document.content.blocks
        self.assertTrue(any(isinstance(block, Heading) for block in blocks))
        self.assertTrue(any(isinstance(block, Paragraph) for block in blocks))
        self.assertTrue(any(isinstance(block, ListBlock) for block in blocks))
        table = next(block for block in blocks if isinstance(block, Table))
        self.assertEqual("Gia tri", table.rows[0].cells[1].text)
        self.assertEqual([], self.ocr.calls)

    def test_plain_text_uses_native_parser_without_ocr(self) -> None:
        document = self.parse(
            "SYNTHETIC-TEXT",
            "cv.txt",
            "CV\nK\u1ef9 n\u00eang: Python\n".encode(),
        )

        self.assertIs(SourceFormat.PLAIN_TEXT, document.source_format)
        self.assertEqual(ParseStatus.SUCCESS, document.parse_status)
        self.assertEqual("CV", document.content.pages[0].blocks[0].text)
        self.assertEqual([], self.ocr.calls)

    def test_xlsx_preserves_sheet_cell_formula_and_merged_range(self) -> None:
        document = self.parse(
            "SYNTHETIC-SPREADSHEET",
            "spreadsheet.xlsx",
            synthetic_xlsx_bytes(),
        )

        workbook = document.content.workbook
        self.assertIsNotNone(workbook)
        sheet = workbook.sheets[0]
        cells = {cell.coordinate: cell for row in sheet.rows for cell in row.cells}
        self.assertEqual("SyntheticSheet", sheet.name)
        self.assertEqual("=SUM(B2:C2)", cells["D2"].formula)
        self.assertIn("A4:D4", sheet.merged_ranges)
        self.assertEqual([], self.ocr.calls)

    def test_pptx_uses_same_extension_contract_without_router_branch(self) -> None:
        document = self.parse(
            "SYNTHETIC-PRESENTATION",
            "notice.pptx",
            synthetic_pptx_bytes(),
        )

        self.assertIs(SourceFormat.PPTX, document.source_format)
        self.assertIs(ParseStatus.PARTIAL, document.parse_status)
        self.assertEqual("THONG BAO SYNTHETIC", document.content.pages[0].blocks[0].text)
        self.assertIn("PPTX_LIMITED_SUPPORT", {warning.code for warning in document.warnings})

    def test_format_warnings_are_preserved_in_canonical_output(self) -> None:
        document = self.parse(
            "SYNTHETIC-WARNING",
            "wrong.docx",
            administrative_image_bytes(),
        )
        self.assertIn(
            "EXTENSION_CONTENT_MISMATCH",
            {warning.code for warning in document.warnings},
        )

    def test_canonical_output_contains_no_vendor_objects(self) -> None:
        document = self.parse(
            "SYNTHETIC-VENDOR-BOUNDARY",
            "spreadsheet.xlsx",
            synthetic_xlsx_bytes(),
        )
        _assert_no_vendor_objects(self, document)


class ParserRegistryTests(TestCase):
    def test_registration_is_deterministic_and_rejects_duplicates(self) -> None:
        first = DocumentParserRegistry()
        first.register(DocxDocumentParser())
        first.register(NativePdfDocumentParser())
        first.register(XlsxDocumentParser())

        second = DocumentParserRegistry()
        second.register(XlsxDocumentParser())
        second.register(NativePdfDocumentParser())
        second.register(DocxDocumentParser())

        self.assertEqual(first.registered_formats, second.registered_formats)
        with self.assertRaisesRegex(ValueError, "already registered"):
            first.register(DocxDocumentParser())

    def test_unsupported_format_fails_with_stable_error(self) -> None:
        with self.assertRaises(DocumentIntakeError) as raised:
            DocumentParserRegistry().resolve(SourceFormat.PPTX)

        self.assertIs(IntakeErrorCode.NO_PARSER, raised.exception.code)

    def test_parser_capabilities_agree_with_supports(self) -> None:
        parsers = (
            DocxDocumentParser(),
            NativePdfDocumentParser(),
            XlsxDocumentParser(),
        )
        for parser in parsers:
            for source_format in SourceFormat:
                self.assertEqual(
                    source_format in parser.capabilities.source_formats,
                    parser.supports(source_format),
                )


def _assert_no_vendor_objects(test: TestCase, value: object) -> None:
    module = type(value).__module__
    test.assertFalse(
        module.startswith(("openpyxl", "fitz", "pymupdf", "PIL", "paddleocr")),
        f"Vendor object leaked into canonical output: {module}.{type(value).__name__}",
    )
    if is_dataclass(value):
        for item in fields(value):
            _assert_no_vendor_objects(test, getattr(value, item.name))
    elif isinstance(value, dict):
        for key, item in value.items():
            _assert_no_vendor_objects(test, key)
            _assert_no_vendor_objects(test, item)
    elif isinstance(value, (tuple, list, set, frozenset)):
        for item in value:
            _assert_no_vendor_objects(test, item)
