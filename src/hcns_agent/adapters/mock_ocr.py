"""Deterministic OCR adapter for tests and local demos."""

from __future__ import annotations

from dataclasses import dataclass

from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrLine, OcrPage, OcrResult


@dataclass(slots=True)
class DeterministicMockOcrEngine:
    text: str = "HỒ SƠ NHÂN SỰ SYNTHETIC"
    confidence: float = 0.95
    box: tuple[tuple[float, float], ...] = (
        (0.0, 0.0),
        (100.0, 0.0),
        (100.0, 20.0),
        (0.0, 20.0),
    )

    @property
    def name(self) -> str:
        return "mock/deterministic-v1"

    def recognize(self, source: DocumentSource) -> OcrResult:
        return OcrResult(
            document_id=source.document_id,
            engine=self.name,
            pages=(
                OcrPage(
                    page_index=0,
                    lines=(
                        OcrLine(
                            text=self.text,
                            confidence=self.confidence,
                            box=self.box,
                        ),
                    ),
                ),
            ),
            duration_ms=1,
            model_manifest={"backend": "mock", "version": "1"},
        )
