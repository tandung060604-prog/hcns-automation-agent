"""Evidence-preserving hybrid OCR orchestration.

The detector owns geometry. The primary recognizer proposes text and the
verifier may only confirm it; disagreement is never silently corrected.
"""

from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrEngine, OcrLine, OcrPage, OcrResult


@dataclass(frozen=True, slots=True)
class LineRecognition:
    text: str
    confidence: float
    model: str


class DetectedLineRecognizer(Protocol):
    @property
    def name(self) -> str: ...

    def recognize_line(
        self,
        source: DocumentSource,
        *,
        page_index: int,
        line_index: int,
        box: tuple[tuple[float, float], ...],
    ) -> LineRecognition: ...


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


@dataclass(slots=True)
class HybridVietnameseOcrEngine:
    detector: OcrEngine
    primary: DetectedLineRecognizer
    verifier: DetectedLineRecognizer

    @property
    def name(self) -> str:
        return "hybrid/paddle-easyocr-vietocr-pilot"

    def recognize(self, source: DocumentSource) -> OcrResult:
        started = time.perf_counter()
        detected = self.detector.recognize(source)
        pages: list[OcrPage] = []
        for page in detected.pages:
            lines: list[OcrLine] = []
            decisions: list[dict[str, object]] = []
            for line_index, detected_line in enumerate(page.lines):
                primary = self.primary.recognize_line(
                    source,
                    page_index=page.page_index,
                    line_index=line_index,
                    box=detected_line.box,
                )
                verifier = self.verifier.recognize_line(
                    source,
                    page_index=page.page_index,
                    line_index=line_index,
                    box=detected_line.box,
                )
                agreed = bool(_normalized(primary.text)) and _normalized(
                    primary.text
                ) == _normalized(verifier.text)
                status = "accepted" if agreed else "needs_review"
                lines.append(
                    OcrLine(
                        text=primary.text,
                        confidence=primary.confidence,
                        box=detected_line.box,
                    )
                )
                decisions.append(
                    {
                        "lineIndex": line_index,
                        "status": status,
                        "detectorText": detected_line.text,
                        "primaryText": primary.text,
                        "primaryConfidence": primary.confidence,
                        "primaryModel": primary.model,
                        "verifierText": verifier.text,
                        "verifierConfidence": verifier.confidence,
                        "verifierModel": verifier.model,
                        "rule": (
                            "nfc_casefold_exact_agreement"
                            if agreed
                            else "primary_preserved_pending_human_review"
                        ),
                    }
                )
            metadata = dict(page.metadata)
            metadata["lineVerification"] = decisions
            metadata["acceptedLineCount"] = sum(
                decision["status"] == "accepted" for decision in decisions
            )
            metadata["needsReviewLineCount"] = sum(
                decision["status"] == "needs_review" for decision in decisions
            )
            pages.append(
                OcrPage(
                    page_index=page.page_index,
                    lines=tuple(lines),
                    metadata=metadata,
                )
            )
        return OcrResult(
            document_id=source.document_id,
            engine=self.name,
            pages=tuple(pages),
            duration_ms=round((time.perf_counter() - started) * 1000),
            model_manifest={
                "detector": detected.engine,
                "primary": self.primary.name,
                "verifier": self.verifier.name,
                "autoAcceptRule": "nfc_casefold_exact_agreement",
                "promotion": "pilot_only",
            },
        )
