"""PaddleOCR adapter with lazy dependency loading.

The adapter accepts an injected predictor so contract tests never download
models. Use ``from_default`` only inside a trusted local runtime.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from importlib import import_module
from io import BytesIO
from typing import Any

from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrLine, OcrPage, OcrResult


@dataclass(slots=True)
class PaddleOcrEngine:
    predictor: Any
    image_converter: Callable[[Any], Any] | None = None
    detection_model: str = "PP-OCRv5_mobile_det"
    recognition_model: str = "latin_PP-OCRv5_mobile_rec"
    device: str = "cpu"
    predict_options: dict[str, Any] = field(
        default_factory=lambda: {
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
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
    def from_default(
        cls,
        *,
        device: str = "cpu",
        recognition_model: str = "latin_PP-OCRv5_mobile_rec",
    ) -> PaddleOcrEngine:
        try:
            PaddleOCR = import_module("paddleocr").PaddleOCR
        except ImportError as error:
            raise RuntimeError(
                'PaddleOCR is not installed. Run: python -m pip install -e ".[paddle]"'
            ) from error

        predictor = PaddleOCR(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name=recognition_model,
            device=device,
            enable_mkldnn=False,
            cpu_threads=4,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        return cls(
            predictor=predictor,
            image_converter=_prepare_for_paddle,
            recognition_model=recognition_model,
            device=device,
        )

    def recognize(self, source: DocumentSource) -> OcrResult:
        try:
            from PIL import Image
        except ImportError as error:
            raise RuntimeError(
                "Pillow is required to decode OCR images"
            ) from error

        started = time.perf_counter()
        with Image.open(BytesIO(source.content)) as image:
            rgb_image = image.convert("RGB")
            predictor_input = (
                self.image_converter(rgb_image)
                if self.image_converter is not None
                else _to_numpy(rgb_image)
            )
        predictions = self.predictor.predict(
            predictor_input, **self.predict_options
        )
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


def _to_numpy(image: Any) -> Any:
    try:
        import numpy as np  # type: ignore[import-not-found,unused-ignore]
    except ImportError as error:
        raise RuntimeError(
            "NumPy is required by PaddleOCR; install the paddle extra"
        ) from error
    return np.asarray(image)


def _prepare_for_paddle(image: Any) -> Any:
    try:
        import cv2  # type: ignore[import-not-found,unused-ignore]
        import numpy as np  # type: ignore[import-not-found,unused-ignore]
        from PIL import ImageEnhance, ImageFilter, ImageOps
    except ImportError as error:
        raise RuntimeError(
            "NumPy, OpenCV, and Pillow are required for OCR preprocessing"
        ) from error
    enhanced = ImageOps.autocontrast(image, cutoff=1)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.08)
    enhanced = enhanced.filter(
        ImageFilter.UnsharpMask(radius=1.0, percent=120, threshold=3)
    )
    rgb = np.asarray(enhanced)
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    rectified = _rectify_document(bgr, cv2=cv2, np=np)
    luminance = cv2.cvtColor(rectified, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(luminance)
    lightness = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(lightness)
    return cv2.cvtColor(
        cv2.merge((lightness, channel_a, channel_b)),
        cv2.COLOR_LAB2BGR,
    )


def _rectify_document(image: Any, *, cv2: Any, np: Any) -> Any:
    """Flatten a photographed page when a reliable four-corner contour exists."""

    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    page_mask = np.where(
        (hsv[:, :, 1] < 80) & (hsv[:, :, 2] > 70),
        255,
        0,
    ).astype("uint8")
    page_mask = cv2.morphologyEx(
        page_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21)),
    )
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
    )
    contours = [
        *cv2.findContours(
            page_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )[0],
        *cv2.findContours(
            edges,
            cv2.RETR_LIST,
            cv2.CHAIN_APPROX_SIMPLE,
        )[0],
    ]
    minimum_page_area = height * width * 0.35
    corners = None
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        if cv2.contourArea(contour) < minimum_page_area:
            break
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) == 4 and cv2.isContourConvex(polygon):
            corners = polygon.reshape(4, 2).astype("float32")
            break
    if corners is None:
        return image

    point_sum = corners.sum(axis=1)
    point_delta = np.diff(corners, axis=1).reshape(-1)
    ordered = np.asarray(
        [
            corners[np.argmin(point_sum)],
            corners[np.argmin(point_delta)],
            corners[np.argmax(point_sum)],
            corners[np.argmax(point_delta)],
        ],
        dtype="float32",
    )
    top_left, top_right, bottom_right, bottom_left = ordered
    output_width = int(
        max(
            np.linalg.norm(bottom_right - bottom_left),
            np.linalg.norm(top_right - top_left),
        )
    )
    output_height = int(
        max(
            np.linalg.norm(top_right - bottom_right),
            np.linalg.norm(top_left - bottom_left),
        )
    )
    if output_width < 600 or output_height < 600:
        return image
    scale = min(1.5, 1800 / max(output_width, output_height))
    output_width = int(output_width * scale)
    output_height = int(output_height * scale)
    destination = np.asarray(
        [
            [0, 0],
            [output_width - 1, 0],
            [output_width - 1, output_height - 1],
            [0, output_height - 1],
        ],
        dtype="float32",
    )
    transform = cv2.getPerspectiveTransform(ordered, destination)
    return cv2.warpPerspective(
        image,
        transform,
        (output_width, output_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
