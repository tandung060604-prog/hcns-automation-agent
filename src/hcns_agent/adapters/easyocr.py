"""EasyOCR adapter for the evidence-backed Vietnamese template route.

The dependency is intentionally lazy. The Template-first local route selects
this recognizer by default after UAT; PaddleOCR remains an explicit rollback
backend through ``HCNS_TEMPLATE_OCR_BACKEND=paddle``.
"""

from __future__ import annotations

import os
import time
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib import import_module
from io import BytesIO
from pathlib import Path
from typing import Any

from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrLine, OcrPage, OcrResult

EASYOCR_CANVAS_SIZE = 1280
EASYOCR_MAG_RATIO = 1.3


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
    ) -> None:
        self._reader = reader
        self._device = device
        self._model_storage_directory = (
            str(model_storage_directory) if model_storage_directory is not None else None
        )

    @property
    def name(self) -> str:
        return "easyocr/vi-greedy"

    @classmethod
    def from_default(
        cls,
        *,
        device: str = "cpu",
        model_storage_directory: str | Path | None = None,
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
            ["vi"],
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
        )

    def recognize(self, source: DocumentSource) -> OcrResult:
        try:
            import numpy as np
            from PIL import Image
        except ImportError as error:
            raise RuntimeError("NumPy and Pillow are required for EasyOCR") from error

        started = time.perf_counter()
        with Image.open(BytesIO(source.content)) as image:
            image_array = np.asarray(image.convert("RGB"))
        read_results = self._reader.readtext(
            image_array,
            detail=1,
            paragraph=False,
            rotation_info=None,
            canvas_size=EASYOCR_CANVAS_SIZE,
            mag_ratio=EASYOCR_MAG_RATIO,
        )
        lines = _group_readtext_results(read_results)
        return OcrResult(
            document_id=source.document_id,
            engine=self.name,
            pages=(OcrPage(page_index=0, lines=lines),),
            duration_ms=round((time.perf_counter() - started) * 1000),
            model_manifest={
                "backend": "easyocr",
                "recognitionModel": "easyocr-vi-greedy",
                "device": self._device,
                "version": "1.7.2",
                "modelStorageDirectory": self._model_storage_directory or "default",
            },
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
        text = str(raw_text).strip()
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
