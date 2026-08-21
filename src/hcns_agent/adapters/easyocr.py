"""EasyOCR adapter for the evidence-backed Vietnamese template route.

The dependency is intentionally lazy. The Template-first local route selects
this recognizer by default after UAT; PaddleOCR remains an explicit rollback
backend through ``HCNS_TEMPLATE_OCR_BACKEND=paddle``.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from importlib import import_module
from io import BytesIO
from pathlib import Path
from typing import Any

from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrLine, OcrPage, OcrResult

EASYOCR_CANVAS_SIZE = 1280
EASYOCR_MAG_RATIO = 1.3
EASYOCR_PREPROCESS_PROFILE = "none"
EASYOCR_DECODER = "greedy"
EASYOCR_LANGUAGE_PROFILE = "vi"
EASYOCR_TEXT_REPAIR_PROFILE = "contextual-business-token-v1"
EASYOCR_LAYOUT_RECOVERY_PROFILE = "label-crop-v1"
_SUPPORTED_PREPROCESS_PROFILES = frozenset(
    {"none", "content-roi-autocontrast-v1"}
)
_SUPPORTED_DECODERS = frozenset({"greedy", "beamsearch"})
_SUPPORTED_LANGUAGE_PROFILES = frozenset({"vi", "vi-en"})


@dataclass(frozen=True, slots=True)
class _ReadTextItem:
    box: tuple[tuple[float, float], ...]
    text: str
    confidence: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        xs = [point[0] for point in self.box]
        ys = [point[1] for point in self.box]
        return min(xs), min(ys), max(xs), max(ys)


class EasyOcrEngine:
    """Run EasyOCR Vietnamese recognition and preserve line geometry."""

    def __init__(
        self,
        reader: Any,
        *,
        device: str = "cpu",
        model_storage_directory: str | Path | None = None,
        canvas_size: int = EASYOCR_CANVAS_SIZE,
        mag_ratio: float = EASYOCR_MAG_RATIO,
        preprocess_profile: str = EASYOCR_PREPROCESS_PROFILE,
        decoder: str = EASYOCR_DECODER,
        language_profile: str = EASYOCR_LANGUAGE_PROFILE,
    ) -> None:
        if canvas_size <= 0 or mag_ratio <= 0:
            raise ValueError("EasyOCR canvas_size and mag_ratio must be positive")
        if preprocess_profile not in _SUPPORTED_PREPROCESS_PROFILES:
            raise ValueError(f"Unsupported EasyOCR preprocess profile: {preprocess_profile}")
        if decoder not in _SUPPORTED_DECODERS:
            raise ValueError(f"Unsupported EasyOCR decoder: {decoder}")
        if language_profile not in _SUPPORTED_LANGUAGE_PROFILES:
            raise ValueError(f"Unsupported EasyOCR language profile: {language_profile}")
        self._reader = reader
        self._device = device
        self._model_storage_directory = (
            str(model_storage_directory) if model_storage_directory is not None else None
        )
        self._canvas_size = canvas_size
        self._mag_ratio = mag_ratio
        self._preprocess_profile = preprocess_profile
        self._decoder = decoder
        self._language_profile = language_profile

    @property
    def name(self) -> str:
        return f"easyocr/{self._language_profile}-{self._decoder}"

    @classmethod
    def from_default(
        cls,
        *,
        device: str = "cpu",
        model_storage_directory: str | Path | None = None,
        canvas_size: int = EASYOCR_CANVAS_SIZE,
        mag_ratio: float = EASYOCR_MAG_RATIO,
        preprocess_profile: str = EASYOCR_PREPROCESS_PROFILE,
        decoder: str = EASYOCR_DECODER,
        language_profile: str = EASYOCR_LANGUAGE_PROFILE,
    ) -> EasyOcrEngine:
        try:
            easyocr = import_module("easyocr")
        except ImportError as error:
            raise RuntimeError(
                'EasyOCR is not installed. Run: python -m pip install -e ".[easyocr]"'
            ) from error
        storage_directory = model_storage_directory or os.getenv(
            "HCNS_EASYOCR_MODEL_DIR"
        )
        reader = easyocr.Reader(
            ["vi"] if language_profile == "vi" else ["vi", "en"],
            gpu=device.casefold() not in {"cpu", "mps"},
            model_storage_directory=(
                str(storage_directory) if storage_directory is not None else None
            ),
            download_enabled=True,
            verbose=False,
        )
        return cls(
            reader,
            device=device,
            model_storage_directory=storage_directory,
            canvas_size=canvas_size,
            mag_ratio=mag_ratio,
            preprocess_profile=preprocess_profile,
            decoder=decoder,
            language_profile=language_profile,
        )

    def recognize(self, source: DocumentSource) -> OcrResult:
        try:
            import numpy as np
            from PIL import Image
        except ImportError as error:
            raise RuntimeError("NumPy and Pillow are required for EasyOCR") from error

        started = time.perf_counter()
        with Image.open(BytesIO(source.content)) as image:
            image_array, roi_origin = _prepare_image(
                image, self._preprocess_profile, np
            )
        read_results = list(self._reader.readtext(
            image_array,
            detail=1,
            paragraph=False,
            rotation_info=None,
            canvas_size=self._canvas_size,
            mag_ratio=self._mag_ratio,
            decoder=self._decoder,
        ))
        recovery_results = _recover_label_crops(
            image_array,
            _read_text_items(read_results),
            reader=self._reader,
            canvas_size=self._canvas_size,
            mag_ratio=self._mag_ratio,
            decoder=self._decoder,
        )
        lines = _offset_lines(
            _group_readtext_results((*read_results, *recovery_results)),
            x_offset=roi_origin[0],
            y_offset=roi_origin[1],
        )
        return OcrResult(
            document_id=source.document_id,
            engine=self.name,
            pages=(OcrPage(page_index=0, lines=lines),),
            duration_ms=round((time.perf_counter() - started) * 1000),
            model_manifest={
                "backend": "easyocr",
                "recognitionModel": f"easyocr-{self._language_profile}-{self._decoder}",
                "device": self._device,
                "version": "1.7.2",
                "modelStorageDirectory": self._model_storage_directory or "default",
                "canvasSize": str(self._canvas_size),
                "magRatio": str(self._mag_ratio),
                "preprocessProfile": self._preprocess_profile,
                "decoder": self._decoder,
                "languageProfile": self._language_profile,
                "textRepairProfile": EASYOCR_TEXT_REPAIR_PROFILE,
                "layoutRecoveryProfile": EASYOCR_LAYOUT_RECOVERY_PROFILE,
            },
        )


def _prepare_image(image: Any, profile: str, numpy: Any) -> tuple[Any, tuple[int, int]]:
    if profile == "none":
        return numpy.asarray(image.convert("RGB")), (0, 0)

    from PIL import Image, ImageChops, ImageOps

    grayscale = ImageOps.autocontrast(image.convert("L"))
    background = Image.new("L", grayscale.size, 255)
    foreground = ImageChops.difference(grayscale, background).point(
        lambda value: 255 if value >= 20 else 0
    )
    bounds = foreground.getbbox()
    if bounds is None:
        return numpy.asarray(grayscale.convert("RGB")), (0, 0)

    left, top, right, bottom = bounds
    padding_x = max(8, int(grayscale.width * 0.01))
    padding_y = max(8, int(grayscale.height * 0.01))
    left = max(0, left - padding_x)
    top = max(0, top - padding_y)
    right = min(grayscale.width, right + padding_x)
    bottom = min(grayscale.height, bottom + padding_y)
    cropped = grayscale.crop((left, top, right, bottom)).convert("RGB")
    return numpy.asarray(cropped), (left, top)


def _recover_label_crops(
    image: Any,
    items: Sequence[_ReadTextItem],
    *,
    reader: Any,
    canvas_size: int,
    mag_ratio: float,
    decoder: str,
) -> list[tuple[Any, ...]]:
    """Re-read small layout regions when a label has no usable inline value."""

    height, width = int(image.shape[0]), int(image.shape[1])
    regions: list[tuple[int, int, int, int, float]] = []
    for item in items:
        key = _normalize_text(item.text)
        x0, y0, x1, y1 = item.bounds
        item_height = max(12, int(y1 - y0))
        if key == "test results":
            region = (
                max(0, int(x0 - 24)),
                max(0, int(y0 - item_height)),
                width,
                min(height, int(y1 + item_height * 9)),
                1.0,
            )
        elif key in {"family name", "first name"}:
            row_padding = max(8, int(item_height * 1.2))
            region = (
                max(0, int(x0 - item_height)),
                max(0, int(y0 - row_padding)),
                min(width, int(x1 + max(180, item_height * 10))),
                min(height, int(y1 + row_padding)),
                min(3.0, max(2.0, 32.0 / item_height)),
            )
        elif key == "overall band score" or key.startswith("overall "):
            region = (
                max(0, int(x0 - item_height * 2)),
                max(0, int(y0 - item_height * 2)),
                min(width, int(x1 + max(180, item_height * 10))),
                min(height, int(y1 + item_height * 3)),
                1.0,
            )
        else:
            continue
        if any(
            _intersection_over_union(region[:4], existing[:4]) >= 0.75
            for existing in regions
        ):
            continue
        regions.append(region)
        if len(regions) >= 3:
            break

    recovered: list[tuple[Any, ...]] = []
    for left, top, right, bottom, scale in regions:
        crop = image[top:bottom, left:right]
        if scale != 1.0:
            import numpy as np
            from PIL import Image

            crop = np.asarray(
                Image.fromarray(crop).resize(
                    (int(crop.shape[1] * scale), int(crop.shape[0] * scale)),
                    Image.Resampling.LANCZOS,
                )
            )
        results = reader.readtext(
            crop,
            detail=1,
            paragraph=False,
            rotation_info=None,
            canvas_size=canvas_size,
            mag_ratio=mag_ratio,
            decoder=decoder,
        )
        for result in results:
            if not isinstance(result, Sequence) or len(result) < 3:
                continue
            raw_box = result[0]
            try:
                offset_box = tuple(
                    (float(point[0]) / scale + left, float(point[1]) / scale + top)
                    for point in raw_box
                )
            except (TypeError, ValueError, IndexError):
                continue
            recovered.append((offset_box, result[1], result[2]))
    return recovered


def _offset_lines(
    lines: tuple[OcrLine, ...],
    *,
    x_offset: int,
    y_offset: int,
) -> tuple[OcrLine, ...]:
    if not x_offset and not y_offset:
        return lines
    return tuple(
        replace(
            line,
            box=tuple((x + x_offset, y + y_offset) for x, y in line.box),
        )
        for line in lines
    )


def _group_readtext_results(results: Iterable[Any]) -> tuple[OcrLine, ...]:
    """Deduplicate EasyOCR fragments and merge boxes that share a text row."""

    items = _deduplicate_items(_read_text_items(results))
    groups: list[list[_ReadTextItem]] = []
    for item in sorted(items, key=lambda value: (value.bounds[1], value.bounds[0])):
        matching = [
            group
            for group in groups
            if _vertical_overlap(item.bounds, _group_bounds(group)) >= 0.45
        ]
        if not matching:
            groups.append([item])
            continue
        target = min(
            matching,
            key=lambda group: abs(
                ((item.bounds[1] + item.bounds[3]) / 2)
                - ((_group_bounds(group)[1] + _group_bounds(group)[3]) / 2)
            ),
        )
        target.append(item)

    lines: list[OcrLine] = []
    for group in sorted(groups, key=lambda value: _group_bounds(value)[1]):
        ordered = sorted(group, key=lambda value: value.bounds[0])
        bounds = _group_bounds(ordered)
        text = " ".join(item.text for item in ordered if item.text)
        confidence = sum(item.confidence for item in ordered) / len(ordered)
        x0, y0, x1, y1 = bounds
        lines.append(
            OcrLine(
                text=text,
                confidence=round(confidence, 4),
                box=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
            )
        )
    return tuple(lines)


def _read_text_items(results: Iterable[Any]) -> list[_ReadTextItem]:
    items: list[_ReadTextItem] = []
    for result in results:
        if not isinstance(result, Sequence) or len(result) < 3:
            continue
        raw_box, raw_text, raw_confidence = result[0], result[1], result[2]
        text = _repair_ocr_text(str(raw_text).strip())
        if not text:
            continue
        try:
            box = tuple((float(point[0]), float(point[1])) for point in raw_box)
            confidence = float(raw_confidence)
        except (TypeError, ValueError, IndexError):
            continue
        if len(box) < 4:
            continue
        items.append(_ReadTextItem(box=box, text=text, confidence=confidence))
    return items


def _repair_ocr_text(text: str) -> str:
    """Repair one unambiguous OCR confusion in a labelled business token."""

    return re.sub(
        r"(?i)\b(Kinh\s+doanh\s+)BZB\b",
        r"\g<1>B2B",
        text,
    )


def _deduplicate_items(items: Iterable[_ReadTextItem]) -> list[_ReadTextItem]:
    kept: list[_ReadTextItem] = []
    for candidate in sorted(items, key=lambda value: _box_area(value.bounds), reverse=True):
        candidate_normalized = _normalize_text(candidate.text)
        duplicate = False
        for existing in kept:
            existing_normalized = _normalize_text(existing.text)
            overlap = _intersection_over_union(candidate.bounds, existing.bounds)
            contained = _containment(candidate.bounds, existing.bounds)
            same_text = candidate_normalized == existing_normalized
            fragment = (
                contained >= 0.75
                and len(candidate_normalized) <= max(4, len(existing_normalized) * 0.65)
            )
            if (overlap >= 0.5 and same_text) or fragment:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


def _group_bounds(items: Iterable[_ReadTextItem]) -> tuple[float, float, float, float]:
    values = [item.bounds for item in items]
    return (
        min(value[0] for value in values),
        min(value[1] for value in values),
        max(value[2] for value in values),
        max(value[3] for value in values),
    )


def _box_area(bounds: tuple[float, float, float, float]) -> float:
    return max(0.0, bounds[2] - bounds[0]) * max(0.0, bounds[3] - bounds[1])


def _vertical_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    overlap = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    return overlap / max(1.0, min(first[3] - first[1], second[3] - second[1]))


def _intersection_over_union(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = _box_area(first) + _box_area(second) - intersection
    return intersection / union if union else 0.0


def _containment(
    candidate: tuple[float, float, float, float],
    container: tuple[float, float, float, float],
) -> float:
    x0 = max(candidate[0], container[0])
    y0 = max(candidate[1], container[1])
    x1 = min(candidate[2], container[2])
    y1 = min(candidate[3], container[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    area = _box_area(candidate)
    return intersection / area if area else 0.0


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value).casefold()
    plain = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(plain.split())
