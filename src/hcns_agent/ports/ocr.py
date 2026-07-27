"""Vendor-neutral OCR contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from hcns_agent.ports.document_parser import DocumentSource


@dataclass(frozen=True, slots=True)
class OcrLine:
    text: str
    confidence: float
    box: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class OcrPage:
    page_index: int
    lines: tuple[OcrLine, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OcrResult:
    document_id: str
    engine: str
    pages: tuple[OcrPage, ...]
    duration_ms: int
    model_manifest: dict[str, str] = field(default_factory=dict)


class OcrEngine(Protocol):
    @property
    def name(self) -> str:
        """Stable engine identifier."""

    def recognize(self, source: DocumentSource) -> OcrResult:
        """Recognize a document without performing business side effects."""
