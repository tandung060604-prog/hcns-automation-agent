"""Composition root for the default local Universal Document Intake."""

from __future__ import annotations

from hcns_agent.adapters.classification import RuleBasedDocumentClassifier
from hcns_agent.adapters.docx import DocxDocumentParser
from hcns_agent.adapters.extractors import (
    CertificateFieldExtractor,
    CvFieldExtractor,
    EmploymentContractFieldExtractor,
    LeaveRequestFieldExtractor,
    TimesheetFieldExtractor,
)
from hcns_agent.adapters.image_inspection import PillowImageInspector
from hcns_agent.adapters.image_parser import ImageDocumentParser
from hcns_agent.adapters.pdf import (
    NativePdfDocumentParser,
    PyMuPdfInspector,
    PyMuPdfRasterizer,
    ScannedPdfDocumentParser,
)
from hcns_agent.adapters.plain_text import PlainTextDocumentParser
from hcns_agent.adapters.pptx import PptxDocumentParser
from hcns_agent.adapters.xlsx import XlsxDocumentParser
from hcns_agent.application.extractor_registry import FieldExtractorRegistry
from hcns_agent.application.format_detection import FormatDetector
from hcns_agent.application.intake import UniversalDocumentIntake
from hcns_agent.application.parser_registry import DocumentParserRegistry
from hcns_agent.application.quality_gate import ValidationQualityGate
from hcns_agent.application.safety import FileSafetyPolicy, FileSafetyValidator
from hcns_agent.application.understand_document import (
    DocumentUnderstandingService,
    IdpPipeline,
)
from hcns_agent.ports.ocr import OcrEngine


def build_default_intake(
    ocr_engine: OcrEngine,
    *,
    safety_policy: FileSafetyPolicy | None = None,
) -> UniversalDocumentIntake:
    pdf_inspector = PyMuPdfInspector()
    registry = DocumentParserRegistry()
    registry.register(ImageDocumentParser(ocr_engine))
    registry.register(NativePdfDocumentParser())
    registry.register(ScannedPdfDocumentParser(PyMuPdfRasterizer(), ocr_engine))
    registry.register(DocxDocumentParser())
    registry.register(XlsxDocumentParser())
    registry.register(PptxDocumentParser())
    registry.register(PlainTextDocumentParser())
    return UniversalDocumentIntake(
        detector=FormatDetector(pdf_inspector),
        safety_validator=FileSafetyValidator(
            PillowImageInspector(),
            policy=safety_policy,
        ),
        registry=registry,
    )


def build_default_understanding() -> DocumentUnderstandingService:
    extractors = FieldExtractorRegistry()
    extractors.register(CvFieldExtractor())
    extractors.register(EmploymentContractFieldExtractor())
    extractors.register(CertificateFieldExtractor())
    extractors.register(LeaveRequestFieldExtractor())
    extractors.register(TimesheetFieldExtractor())
    return DocumentUnderstandingService(
        classifier=RuleBasedDocumentClassifier(),
        extractors=extractors,
        quality_gate=ValidationQualityGate(),
    )


def build_default_pipeline(
    ocr_engine: OcrEngine,
    *,
    safety_policy: FileSafetyPolicy | None = None,
) -> IdpPipeline:
    return IdpPipeline(
        intake=build_default_intake(
            ocr_engine,
            safety_policy=safety_policy,
        ),
        understanding=build_default_understanding(),
    )
