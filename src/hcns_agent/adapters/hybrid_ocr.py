"""Evidence-preserving hybrid OCR orchestration.

Paddle owns geometry and the selected text. Independent recognizers may only
confirm that text; disagreement is never allowed to replace it silently.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from hcns_agent.application.ocr_metrics import normalize_for_agreement
from hcns_agent.application.recognition_policy import (
    PADDLE_VERIFICATION_POLICY_V1,
    RecognitionPolicy,
)
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
    return normalize_for_agreement(value)


@dataclass(slots=True)
class HybridVietnameseOcrEngine:
    detector: OcrEngine
    # Phase 14 keeps these names for API compatibility. Both are independent
    # verifiers of the detector's Paddle recognition candidate.
    primary: DetectedLineRecognizer
    verifier: DetectedLineRecognizer
    policy: RecognitionPolicy = PADDLE_VERIFICATION_POLICY_V1

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
                detector_text = detected_line.text
                selected_text = self.policy.selected_text(detector_text)
                confirmed_by_primary = bool(_normalized(detector_text)) and _normalized(
                    detector_text
                ) == _normalized(primary.text)
                confirmed_by_verifier = bool(_normalized(detector_text)) and _normalized(
                    detector_text
                ) == _normalized(verifier.text)
                confirmed = confirmed_by_primary or confirmed_by_verifier
                status = "accepted" if confirmed else "needs_review"
                lines.append(
                    OcrLine(
                        text=selected_text,
                        confidence=detected_line.confidence,
                        box=detected_line.box,
                    )
                )
                decisions.append(
                    {
                        "lineIndex": line_index,
                        "status": status,
                        "selectedText": selected_text,
                        "selectedConfidence": detected_line.confidence,
                        "easyOcrText": primary.text,
                        "easyOcrConfidence": primary.confidence,
                        "easyOcrModel": primary.model,
                        "vietOcrText": verifier.text,
                        "vietOcrConfidence": verifier.confidence,
                        "vietOcrModel": verifier.model,
                        "paddleEasyAgreed": confirmed_by_primary,
                        "paddleVietAgreed": confirmed_by_verifier,
                        "rule": (
                            "paddle_confirmed_by_at_least_one_independent_recognizer"
                            if confirmed
                            else "paddle_preserved_pending_human_review"
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
        policy_manifest = self.policy.manifest()
        return OcrResult(
            document_id=source.document_id,
            engine=self.name,
            pages=tuple(pages),
            duration_ms=round((time.perf_counter() - started) * 1000),
            model_manifest={
                "detector": detected.engine,
                "primary": detected.engine,
                "verifiers": f"{self.primary.name},{self.verifier.name}",
                "autoAcceptRule": "paddle_matches_at_least_one_verifier",
                "promotion": "pilot_only",
                "recognitionPolicyId": str(policy_manifest["policyId"]),
                "recognitionPolicyVersion": str(policy_manifest["version"]),
                "recognitionPolicyDigest": str(policy_manifest["policyDigest"]),
            },
        )
