"""Process a document and create a review-aware proposal."""

from __future__ import annotations

from dataclasses import dataclass

from hcns_agent.domain.models import (
    DocumentType,
    ExtractedField,
    FieldStatus,
    HrDocument,
    ProcessingProposal,
    Provenance,
)
from hcns_agent.ports.ocr import OcrEngine, OcrResult


@dataclass(frozen=True, slots=True)
class ProcessingPolicy:
    minimum_confidence: float = 0.85
    sensitive_fields: frozenset[str] = frozenset(
        {"identity_number", "full_name", "date_of_birth", "salary", "bank_account"}
    )
    always_review_types: frozenset[DocumentType] = frozenset(
        {
            DocumentType.IDENTITY_CARD,
            DocumentType.PASSPORT,
            DocumentType.EMPLOYMENT_CONTRACT,
            DocumentType.TIMESHEET,
        }
    )


class ProcessDocument:
    def __init__(self, ocr_engine: OcrEngine, policy: ProcessingPolicy | None = None) -> None:
        self._ocr_engine = ocr_engine
        self._policy = policy or ProcessingPolicy()

    def execute(self, document: HrDocument) -> ProcessingProposal:
        result = self._ocr_engine.recognize(document)
        fields = self._extract_demonstration_fields(document, result)
        reasons: list[str] = []

        if document.document_type in self._policy.always_review_types:
            reasons.append(f"{document.document_type} requires review by policy")
        if any(field.status is FieldStatus.NEEDS_REVIEW for field in fields):
            reasons.append("One or more fields are below the confidence threshold")
        if any(field.name in self._policy.sensitive_fields for field in fields):
            reasons.append("Sensitive fields require human confirmation")

        return ProcessingProposal(
            document_id=document.document_id,
            document_type=document.document_type,
            fields=tuple(fields),
            requires_human_review=bool(reasons),
            review_reasons=tuple(dict.fromkeys(reasons)),
            engine=result.engine,
        )

    def _extract_demonstration_fields(
        self, document: HrDocument, result: OcrResult
    ) -> list[ExtractedField]:
        # This deliberately small extractor demonstrates boundaries. Production
        # extractors belong to document-type-specific modules and contract tests.
        lines = [line for page in result.pages for line in page.lines if line.text.strip()]
        if not lines:
            return [
                ExtractedField(
                    name="document_text",
                    value=None,
                    confidence=0.0,
                    status=FieldStatus.NOT_FOUND,
                    provenance=Provenance(engine=result.engine, page_index=0),
                )
            ]

        confidence = min(line.confidence for line in lines)
        status = (
            FieldStatus.ACCEPTED
            if confidence >= self._policy.minimum_confidence
            else FieldStatus.NEEDS_REVIEW
        )
        return [
            ExtractedField(
                name="document_text",
                value="\n".join(line.text for line in lines),
                confidence=confidence,
                status=status,
                provenance=Provenance(
                    engine=result.engine,
                    page_index=0,
                    line_indexes=tuple(range(len(lines))),
                    metadata={"document_type": document.document_type},
                ),
            )
        ]
