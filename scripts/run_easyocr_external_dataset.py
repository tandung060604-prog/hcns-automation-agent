#!/usr/bin/env python3
"""Run the local EasyOCR vi+en worker for private scan pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _box(value: object) -> list[list[float]]:
    return [
        [float(point[0]), float(point[1])]
        for point in value  # type: ignore[union-attr]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
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
            mag_ratio=1.3,
        )
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
