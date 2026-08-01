"""PaddleOCR adapter with lazy dependency loading.

The adapter accepts an injected predictor so contract tests never download
models. Use ``from_default`` only inside a trusted local runtime.
"""

from __future__ import annotations

import json
import time
import unicodedata
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
    enable_roi_recovery: bool = False

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
            enable_roi_recovery=True,
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
        roi_evidence: list[dict[str, object]] = []
        if self.enable_roi_recovery:
            roi_evidence = self._recover_roi_fields(predictor_input, pages)
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
                "roiRecovery": json.dumps(roi_evidence, ensure_ascii=False),
            },
        )

    def _recover_roi_fields(
        self,
        predictor_input: Any,
        pages: tuple[OcrPage, ...],
    ) -> list[dict[str, object]]:
        """Run a bounded second pass over fixed-template value regions.

        The first pass remains the source of truth for layout and classification.
        These small regions only provide candidates for fields commonly lost by
        Vietnamese OCR; parsers decide whether a candidate is safe to apply.
        The configuration is deliberately layout-relative so scan-PDF raster sizes
        and camera captures use the same coordinates.
        """
        shape: Any = getattr(predictor_input, "shape", ())
        if len(shape) < 2 or not pages:
            return []
        height, width = int(shape[0]), int(shape[1])
        layout = _roi_layout(pages)
        if layout is None:
            return []
        evidence: list[dict[str, object]] = []
        for field_name, (x0, y0, x1, y1) in layout:
            crop_box = (
                max(0, int(width * x0)),
                max(0, int(height * y0)),
                min(width, int(width * x1)),
                min(height, int(height * y1)),
            )
            if crop_box[2] - crop_box[0] < 80 or crop_box[3] - crop_box[1] < 24:
                continue
            try:
                import numpy as np  # type: ignore[import-not-found,unused-ignore]

                crop = np.ascontiguousarray(
                    predictor_input[
                        crop_box[1] : crop_box[3], crop_box[0] : crop_box[2]
                    ]
                )
                predictions = self.predictor.predict(
                    crop, **self.predict_options
                )
            except Exception:
                # ROI is an enhancement. A failed crop must never fail the full
                # document or change the mandatory manual-review route.
                continue
            texts: list[str] = []
            scores: list[float] = []
            for prediction in predictions:
                texts.extend(
                    str(value).strip()
                    for value in prediction.get("rec_texts", [])
                    if str(value).strip()
                )
                scores.extend(float(value) for value in prediction.get("rec_scores", []))
            if field_name == "employeeName":
                texts = [
                    value.split(":", 1)[1].split("-", 1)[0].strip()
                    if ":" in value
                    else value.split("-", 1)[0].strip()
                    for value in texts
                ]
            if not texts:
                continue
            evidence.append(
                {
                    "field": field_name,
                    "text": " ".join(texts),
                    "confidence": round(sum(scores) / len(scores), 4) if scores else 0.0,
                    "box": list(crop_box),
                    "recognizer": self.name,
                    "reason": "fixed_template_value_roi",
                }
            )
        return evidence

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


def _roi_layout(
    pages: tuple[OcrPage, ...],
) -> tuple[tuple[str, tuple[float, float, float, float]], ...] | None:
    """Choose one of the two approved HR layouts from OCR title anchors."""
    text = " ".join(line.text for page in pages for line in page.lines)
    normalized = _normalize_label(text)
    folded = text.casefold()
    top_lines = [
        line
        for page in pages
        for line in page.lines
        if line.box and min(point[1] for point in line.box) < 320
    ]
    leave_title = any("ngh" in line.text.casefold() for line in top_lines[:3])
    overtime_title = any(
        "ca" in line.text.casefold()
        and "ng" in line.text.casefold()
        and "t" in line.text.casefold()
        for line in top_lines
    )
    # PP-OCRv5 latin may preserve ``ngh``/``t...ng ca`` while dropping the
    # remaining Vietnamese marks. These title-local combinations are mutually
    # exclusive for the two closed-set layouts.
    if overtime_title:
        return (
            ("employeeName", (0.18, 0.23, 0.48, 0.25)),
            ("jobTitle", (0.39, 0.23, 0.90, 0.25)),
            ("reason", (0.08, 0.26, 0.97, 0.38)),
            ("workContent", (0.18, 0.41, 0.97, 0.48)),
        )
    if leave_title or "ngh" in folded or "don xin nghi phep" in normalized:
        return (
            ("employeeName", (0.18, 0.175, 0.86, 0.20)),
            ("jobTitle", (0.18, 0.20, 0.86, 0.225)),
            ("department", (0.18, 0.22, 0.90, 0.25)),
            ("reason", (0.18, 0.31, 0.97, 0.40)),
            ("handoverTasks", (0.18, 0.40, 0.97, 0.48)),
        )
    return None


def _normalize_label(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value).casefold()
    plain = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(
        "".join(character if character.isalnum() else " " for character in plain).split()
    )


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
