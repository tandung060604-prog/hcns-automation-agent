"""PaddleOCR adapter with lazy dependency loading.

The adapter accepts an injected predictor so contract tests never download
models. Use ``from_default`` only inside a trusted local runtime.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import import_module
from io import BytesIO
from typing import Any

from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrLine, OcrPage, OcrResult


@dataclass(slots=True)
class PaddleOcrEngine:
    predictor: Any
    detection_model: str = "PP-OCRv5_mobile_det"
    recognition_model: str = "latin_PP-OCRv5_mobile_rec"
    device: str = "cpu"
    predict_options: dict[str, Any] = field(
        default_factory=lambda: {
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": True,
            "text_det_limit_side_len": 1600,
            "text_det_limit_type": "max",
            "text_det_box_thresh": 0.45,
            "text_rec_score_thresh": 0.0,
        }
    )

    @property
    def name(self) -> str:
        return "paddleocr/pp-ocrv5-vi"

    @classmethod
    def from_default(cls, *, device: str = "cpu") -> PaddleOcrEngine:
        try:
            PaddleOCR = import_module("paddleocr").PaddleOCR
        except ImportError as error:
            raise RuntimeError(
                'PaddleOCR is not installed. Run: python -m pip install -e ".[paddle]"'
            ) from error

        predictor = PaddleOCR(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
            device=device,
            enable_mkldnn=False,
        )
        return cls(predictor=predictor, device=device)

    def recognize(self, source: DocumentSource) -> OcrResult:
        try:
            import numpy as np
            from PIL import Image
        except ImportError as error:
            raise RuntimeError(
                "PaddleOCR image dependencies are missing; install the paddle extra"
            ) from error

        started = time.perf_counter()
        with Image.open(BytesIO(source.content)) as image:
            rgb_image = np.asarray(image.convert("RGB"))
        predictions = self.predictor.predict(rgb_image, **self.predict_options)
        pages = tuple(self._to_pages(predictions))
        duration_ms = round((time.perf_counter() - started) * 1000)
        return OcrResult(
            document_id=source.document_id,
            engine=self.name,
            pages=pages,
            duration_ms=duration_ms,
            model_manifest={
                "backend": "paddleocr",
                "detectionModel": self.detection_model,
                "recognitionModel": self.recognition_model,
                "device": self.device,
                "version": "3",
            },
        )

    @staticmethod
    def _to_pages(predictions: Iterable[Any]) -> Iterable[OcrPage]:
        for page_index, prediction in enumerate(predictions):
            texts = list(prediction.get("rec_texts", []))
            scores = list(prediction.get("rec_scores", []))
            polygons = list(prediction.get("rec_polys", []))
            lines: list[OcrLine] = []
            for line_index, text in enumerate(texts):
                confidence = float(scores[line_index]) if line_index < len(scores) else 0.0
                polygon = polygons[line_index] if line_index < len(polygons) else ()
                box = tuple((float(point[0]), float(point[1])) for point in _as_list(polygon))
                lines.append(OcrLine(text=str(text), confidence=confidence, box=box))
            yield OcrPage(page_index=page_index, lines=tuple(lines))


def _as_list(value: Any) -> list[Any]:
    if hasattr(value, "tolist"):
        converted = value.tolist()
        return list(converted)
    return list(value)
