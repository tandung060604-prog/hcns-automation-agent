#!/usr/bin/env python3
"""Run the local EasyOCR vi+en worker for private scan pages."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path


def _bounds(box: object) -> tuple[float, float, float, float]:
    points = _box(box)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _box(value: object) -> list[list[float]]:
    return [
        [float(point[0]), float(point[1])]
        for point in value  # type: ignore[union-attr]
    ]


def _same_line(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> bool:
    first_height = first[3] - first[1]
    second_height = second[3] - second[1]
    first_center = (first[1] + first[3]) / 2
    second_center = (second[1] + second[3]) / 2
    return abs(first_center - second_center) <= max(18.0, min(first_height, second_height) * 0.75)


def _line_groups(results: list[object]) -> list[list[object]]:
    positioned = sorted(
        results,
        key=lambda item: (
            (_bounds(item[0])[1] + _bounds(item[0])[3]) / 2,
            _bounds(item[0])[0],
        ),
    )
    groups: list[list[object]] = []
    for item in positioned:
        box = _bounds(item[0])
        if groups and _same_line(box, _bounds(groups[-1][-1][0])):
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def _candidate_allowed(candidate: str, original: str) -> bool:
    candidate = " ".join(candidate.split())
    original = " ".join(original.split())
    if len(candidate.split()) < 2 or "@" in candidate or "github" in candidate.casefold():
        return False
    if original and original[0].islower() and candidate[0].isdigit():
        return False
    return len(candidate) <= max(80, len(original) * 2.5)


_SECTION_HEADINGS = frozenset(
    {
        "muc tieu nghe nghiep",
        "hoc van",
        "kinh nghiem",
        "kinh nghiem lam viec",
        "ky nang",
        "chung chi",
        "du an",
        "so thich",
        "nguoi tham chieu",
    }
)


def _fold_text(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).casefold()
    decomposed = unicodedata.normalize("NFD", text)
    plain = "".join(
        "d" if character == "đ" else character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def _section_heading(text: object) -> str | None:
    key = _fold_text(text)
    return next(
        (
            heading
            for heading in sorted(_SECTION_HEADINGS, key=len, reverse=True)
            if key == heading or key.startswith(f"{heading} ")
        ),
        None,
    )


def _load_vietocr_config(config_root: Path) -> object:
    from vietocr.tool.config import Cfg

    base_path = config_root / "base.yml"
    model_path = config_root / "vgg-seq2seq.yml"
    missing = [str(path) for path in (base_path, model_path) if not path.is_file()]
    if missing:
        raise SystemExit(
            "Offline VietOCR config is incomplete; missing: " + ", ".join(missing)
        )
    base = Cfg.load_config_from_file(str(base_path))
    model = Cfg.load_config_from_file(str(model_path))
    base.update(model)
    return Cfg(base)


def _refine_lines(path: Path, results: list[object], predictor: object) -> list[dict[str, object]]:
    from PIL import Image

    with Image.open(path).convert("RGB") as image:
        groups = _line_groups(results)
        active_sections: list[str | None] = []
        current_section: str | None = None
        for group in groups:
            original = " ".join(
                str(item[1]).strip()
                for item in sorted(group, key=lambda item: _bounds(item[0])[0])
                if str(item[1]).strip()
            )
            heading = _section_heading(original)
            if heading is not None:
                current_section = heading
            active_sections.append(current_section)
        crops: list[object] = []
        crop_groups: list[list[object]] = []
        for index, group in enumerate(groups):
            # VietOCR line refinement is useful for narrative OCR, but on CV
            # skill lists it can replace a good EasyOCR token with a noisy one.
            # Keep the promoted EasyOCR output for this section and avoid the
            # extra crop/model work as a small memory guard.
            if active_sections[index] == "ky nang":
                continue
            bounds = [_bounds(item[0]) for item in group]
            y0 = max(0, int(min(item[1] for item in bounds)) - 8)
            y1 = min(image.height, int(max(item[3] for item in bounds)) + 8)
            x0 = max(0, int(min(item[0] for item in bounds)) - 80)
            x1 = min(image.width, int(max(item[2] for item in bounds)) + 160)
            if x1 - x0 > image.width * 0.75 or y0 > image.height * 0.8:
                continue
            crop = image.crop((x0, y0, x1, y1))
            crops.append(
                crop.resize(
                    (max(32, crop.width * 2), max(32, crop.height * 2)),
                    Image.Resampling.LANCZOS,
                )
            )
            crop_groups.append(group)
        candidates = predictor.predict_batch(crops) if crops else []
        refined: list[dict[str, object]] = []
        candidate_by_group = {
            id(group): str(candidate)
            for group, candidate in zip(crop_groups, candidates, strict=True)
        }
        for index, group in enumerate(groups):
            original_group = group
            group = sorted(original_group, key=lambda item: _bounds(item[0])[0])
            text = " ".join(str(item[1]).strip() for item in group if str(item[1]).strip())
            candidate = (
                None
                if active_sections[index] == "ky nang"
                else candidate_by_group.get(id(original_group))
            )
            if candidate and _candidate_allowed(candidate, text):
                text = " ".join(candidate.split())
            bounds = [_bounds(item[0]) for item in group]
            x0 = min(item[0] for item in bounds)
            y0 = min(item[1] for item in bounds)
            x1 = max(item[2] for item in bounds)
            y1 = max(item[3] for item in bounds)
            refined.append(
                {
                    "text": text,
                    "score": max(float(item[2]) for item in group),
                    "box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                }
            )
        return refined


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--vietocr-model-root", type=Path)
    parser.add_argument("--vietocr-config-root", type=Path)
    parser.add_argument("--vietocr-line-refine", action="store_true")
    parser.add_argument("--canvas-size", type=int, default=1280)
    parser.add_argument("--mag-ratio", type=float, default=1.3)
    options = parser.parse_args()

    import easyocr

    paths = json.loads(options.input.read_text(encoding="utf-8"))
    if not isinstance(paths, list):
        raise SystemExit("EasyOCR input must be a JSON array")
    reader = easyocr.Reader(
        ["vi", "en"],
        gpu=False,
        model_storage_directory=str(options.model_root),
        download_enabled=False,
        verbose=False,
    )
    predictor = None
    if options.vietocr_line_refine and options.vietocr_model_root:
        weight = options.vietocr_model_root / "vgg_seq2seq.pth"
        if weight.is_file():
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor

            config = (
                _load_vietocr_config(options.vietocr_config_root)
                if options.vietocr_config_root
                else Cfg.load_config_from_name("vgg_seq2seq")
            )
            config["device"] = "cpu"
            config["weights"] = str(weight)
            config["predictor"]["beamsearch"] = False
            predictor = Predictor(config)
    pages: dict[str, dict[str, object]] = {}
    for raw_path in paths:
        path = Path(str(raw_path)).expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"EasyOCR page is unavailable: {path}")
        results = reader.readtext(
            str(path),
            detail=1,
            paragraph=False,
            decoder="beamsearch",
            batch_size=1,
            canvas_size=options.canvas_size,
            mag_ratio=options.mag_ratio,
        )
        refined = _refine_lines(path, results, predictor) if predictor else None
        if refined is not None:
            pages[str(path)] = {
                "recognizedTexts": [item["text"] for item in refined],
                "recognitionScores": [item["score"] for item in refined],
                "recognizedBoxes": [item["box"] for item in refined],
            }
            continue
        pages[str(path)] = {
            "recognizedTexts": [str(item[1]) for item in results],
            "recognitionScores": [float(item[2]) for item in results],
            "recognizedBoxes": [_box(item[0]) for item in results],
        }
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(
        json.dumps(
            {
                "schemaVersion": "external-dataset-easyocr-pages/1.0.0",
                "engine": "easyocr/vi+en",
                "pages": pages,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"EasyOCR pages ready: {len(pages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
