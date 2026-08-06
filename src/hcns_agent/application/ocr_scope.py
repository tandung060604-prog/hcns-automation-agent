"""Current OCR allowlist for local document processing."""

from __future__ import annotations

from hcns_agent.domain.documents import DocumentType, SourceFormat

OCR_ALLOWED_DOCUMENT_TYPES = frozenset(
    {
        DocumentType.CV,
        DocumentType.IDENTITY_CARD,
        DocumentType.EMPLOYMENT_CONTRACT,
        DocumentType.CONTRACT_APPENDIX,
        DocumentType.HR_DECISION,
        DocumentType.CERTIFICATE,
    }
)
OCR_SCAN_FORMATS = frozenset({SourceFormat.IMAGE, SourceFormat.PDF_SCAN})

_ALIASES = {
    "CV": DocumentType.CV,
    "IDENTITY_DOCUMENT": DocumentType.IDENTITY_CARD,
    "IDENTITY_CARD": DocumentType.IDENTITY_CARD,
    "EMPLOYMENT_CONTRACT": DocumentType.EMPLOYMENT_CONTRACT,
    "CONTRACT": DocumentType.EMPLOYMENT_CONTRACT,
    "CONTRACT_DECISION": DocumentType.HR_DECISION,
    "HR_DECISION": DocumentType.HR_DECISION,
    "CERTIFICATE": DocumentType.CERTIFICATE,
}


def normalize_declared_document_type(value: str | DocumentType | None) -> DocumentType | None:
    if isinstance(value, DocumentType):
        return value
    normalized = str(value or "").strip().upper()
    return _ALIASES.get(normalized)


def ocr_allowed_for_document_type(value: str | DocumentType | None) -> bool:
    document_type = normalize_declared_document_type(value)
    return document_type in OCR_ALLOWED_DOCUMENT_TYPES


def ocr_scope_for(source_format: SourceFormat, value: str | DocumentType | None) -> str:
    if source_format not in OCR_SCAN_FORMATS:
        return "NATIVE_ONLY"
    return "OCR_ALLOWED" if ocr_allowed_for_document_type(value) else "UNSUPPORTED_NO_OCR"
