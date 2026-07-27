"""Deterministic OCR adapter for tests and local demos."""

from __future__ import annotations

from dataclasses import dataclass

from hcns_agent.domain.models import HrDocument
from hcns_agent.ports.ocr import OcrLine, OcrPage, OcrResult


@dataclass(slots=True)
class DeterministicMockOcrEngine:
    text: str = "HỒ SƠ NHÂN SỰ SYNTHETIC"
    confidence: float = 0.95

    @property
    def name(self) -> str:
        return "mock/deterministic-v1"

    def recognize(self, document: HrDocument) -> OcrResult:
        return OcrResult(
            document_id=document.document_id,
            engine=self.name,
            pages=(
                OcrPage(
                    page_index=0,
                    lines=(OcrLine(text=self.text, confidence=self.confidence),),
                ),
            ),
            duration_ms=1,
            model_manifest={"backend": "mock", "version": "1"},
        )

