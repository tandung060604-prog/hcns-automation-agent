"""Evidence-preserving hybrid OCR orchestration for Phase 14.8.

Paddle owns geometry only. VietOCR Seq2Seq owns the selected text and the
Transformer independently verifies it. No Paddle recognition text participates
in fallback selection.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from hcns_agent.application.recognition_policy import (
    PHASE14_8_TRANSFORMER_VERIFIER_POLICY,
    VerifierRecognitionPolicy,
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


@dataclass(slots=True)
class HybridVietnameseOcrEngine:
    detector: OcrEngine
    # Paddle supplies geometry. Primary and verifier recognize the same crop.
    primary: DetectedLineRecognizer
    verifier: DetectedLineRecognizer
    policy: VerifierRecognitionPolicy = PHASE14_8_TRANSFORMER_VERIFIER_POLICY

    @property
    def name(self) -> str:
        return "hybrid/paddle-detector-vietocr-seq2seq-transformer"

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
                decision = self.policy.decide(
                    primary_text=primary.text,
                    primary_confidence=primary.confidence,
                    verifier_text=verifier.text,
                )
                lines.append(
                    OcrLine(
                        text=decision.selected_text,
                        confidence=decision.selected_confidence,
                        box=detected_line.box,
                    )
                )
                decisions.append(
                    {
                        "lineIndex": line_index,
                        "status": decision.status,
                        "selectedText": decision.selected_text,
                        "selectedConfidence": decision.selected_confidence,
                        "primaryText": primary.text,
                        "primaryConfidence": primary.confidence,
                        "primaryModel": primary.model,
                        "verifierText": verifier.text,
                        "verifierConfidence": verifier.confidence,
                        "verifierModel": verifier.model,
                        "detectorRawText": detector_text,
                        "detectorConfidence": detected_line.confidence,
                        "primaryVerifierExactAgreement": (
                            decision.exact_agreement
                        ),
                        "paddleEligibleForSelection": False,
                        "rule": decision.rule,
                    }
                )
            metadata = dict(page.metadata)
            metadata["lineVerification"] = decisions
            metadata["verifiedLineCount"] = sum(
                decision["status"] == "verified" for decision in decisions
            )
            metadata["acceptedLineCount"] = 0
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
                "primary": self.primary.name,
                "verifier": self.verifier.name,
                "paddleSelectionEligible": "false",
                "verificationRule": "seq2seq_exactly_matches_transformer",
                "promotion": "shadow_review_only",
                "recognitionPolicyId": str(policy_manifest["policyId"]),
                "recognitionPolicyVersion": str(policy_manifest["version"]),
                "recognitionPolicyDigest": str(policy_manifest["policyDigest"]),
            },
        )
