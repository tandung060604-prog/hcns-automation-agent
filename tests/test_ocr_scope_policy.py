from hcns_agent.application.ocr_scope import ocr_allowed_for_document_type, ocr_scope_for
from hcns_agent.domain.documents import DocumentType, SourceFormat


def test_scope_allows_local_ocr_for_visual_hr_families() -> None:
    assert ocr_allowed_for_document_type(DocumentType.IDENTITY_CARD)
    assert ocr_allowed_for_document_type("IDENTITY_DOCUMENT")
    assert ocr_allowed_for_document_type(DocumentType.CV)
    assert ocr_allowed_for_document_type(DocumentType.EMPLOYMENT_CONTRACT)
    assert ocr_allowed_for_document_type("CONTRACT")
    assert ocr_allowed_for_document_type(DocumentType.CERTIFICATE)
    assert ocr_scope_for(SourceFormat.IMAGE, "CERTIFICATE") == "OCR_ALLOWED"
    assert ocr_scope_for(SourceFormat.PDF_SCAN, "CV") == "OCR_ALLOWED"
    assert ocr_scope_for(SourceFormat.IMAGE, "CONTRACT") == "OCR_ALLOWED"
    assert ocr_scope_for(SourceFormat.PDF_TEXT, "CV") == "NATIVE_ONLY"
