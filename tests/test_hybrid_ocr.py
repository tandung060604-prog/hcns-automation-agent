from __future__ import annotations

import unittest
from dataclasses import dataclass

from hcns_agent.adapters.hybrid_ocr import (
    HybridVietnameseOcrEngine,
    LineRecognition,
)
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrLine, OcrPage, OcrResult


class FakeDetector:
    name = "paddle-detector"

    def recognize(self, source: DocumentSource) -> OcrResult:
        del source
        return OcrResult(
            document_id="doc-1",
            engine=self.name,
            pages=(
                OcrPage(
                    page_index=0,
                    lines=(
                        OcrLine(
                            text="NGUYN THI MAI",
                            confidence=0.92,
                            box=((1.0, 2.0), (20.0, 2.0), (20.0, 8.0), (1.0, 8.0)),
                        ),
                        OcrLine(
                            text="Qun 1",
                            confidence=0.88,
                            box=((1.0, 10.0), (20.0, 10.0), (20.0, 16.0), (1.0, 16.0)),
                        ),
                    ),
                ),
            ),
            duration_ms=5,
        )


@dataclass
class FakeRecognizer:
    name: str
    values: tuple[LineRecognition, ...]

    def recognize_line(self, source, *, page_index, line_index, box):
        del source, page_index, box
        return self.values[line_index]


class HybridOcrTests(unittest.TestCase):
    def test_accepts_only_agreement_and_preserves_detector_geometry(self) -> None:
        source = DocumentSource(
            document_id="doc-1",
            filename="scan.png",
            content=b"private image bytes",
            declared_media_type="image/png",
        )
        primary = FakeRecognizer(
            "easyocr/vi",
            (
                LineRecognition("NGUYN THI MAI", 0.96, "easyocr-vi"),
                LineRecognition("Quận 1", 0.89, "easyocr-vi"),
            ),
        )
        verifier = FakeRecognizer(
            "vietocr/vgg_seq2seq",
            (
                LineRecognition("Nguyễn Thị Mai", 0.95, "vgg_seq2seq"),
                LineRecognition("Quận I", 0.80, "vgg_seq2seq"),
            ),
        )

        result = HybridVietnameseOcrEngine(
            FakeDetector(), primary, verifier
        ).recognize(source)

        page = result.pages[0]
        self.assertEqual(
            [line.text for line in page.lines], ["NGUYN THI MAI", "Qun 1"]
        )
        self.assertEqual(
            page.lines[0].box,
            ((1.0, 2.0), (20.0, 2.0), (20.0, 8.0), (1.0, 8.0)),
        )
        self.assertEqual(page.metadata["acceptedLineCount"], 1)
        self.assertEqual(page.metadata["needsReviewLineCount"], 1)
        self.assertEqual(
            page.metadata["lineVerification"][0]["status"], "accepted"
        )
        self.assertEqual(
            page.metadata["lineVerification"][1]["status"], "needs_review"
        )
        self.assertEqual(
            page.metadata["lineVerification"][1]["rule"],
            "paddle_preserved_pending_human_review",
        )
        self.assertEqual(result.model_manifest["promotion"], "pilot_only")
