"""Domain models for HCNS document processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from hcns_agent.domain.documents import DocumentType as DocumentType


class FieldStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_FOUND = "NOT_FOUND"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class HrDocument:
    document_id: str
    filename: str
    document_type: DocumentType = DocumentType.UNKNOWN

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id must not be empty")
        if not self.filename.strip():
            raise ValueError("filename must not be empty")


@dataclass(frozen=True, slots=True)
class Provenance:
    engine: str
    page_index: int
    line_indexes: tuple[int, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtractedField:
    name: str
    value: str | None
    confidence: float
    status: FieldStatus
    provenance: Provenance

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ProcessingProposal:
    document_id: str
    document_type: DocumentType
    fields: tuple[ExtractedField, ...]
    requires_human_review: bool
    review_reasons: tuple[str, ...]
    engine: str
