#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the local PaddleOCR baseline for every PNG under ``input``."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from paddleocr import PaddleOCR


def jsonable(value: Any) -> Any:
    """Convert Paddle/numpy result values into JSON-compatible Python values."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def load_ground_truth_ids(data_root: Path) -> list[str]:
    ids: list[str] = []
    for path in sorted((data_root / "ground_truth").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            document_id = payload.get("documentId")
            if isinstance(document_id, str) and document_id:
                ids.append(document_id)
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(set(ids), key=len, reverse=True)


def source_document_id(stem: str, ground_truth_ids: list[str]) -> str | None:
    for document_id in ground_truth_ids:
        if stem == document_id or stem.startswith(f"{document_id}_"):
            return document_id
    return None


def draw_ocr_boxes(image_path: Path, boxes: list[Any], output_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    for box in boxes:
        points = [(float(point[0]), float(point[1])) for point in box]
        if len(points) >= 3:
            draw.polygon(points, outline="red", width=2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def run_ocr_file(
    ocr: "PaddleOCR",
    image_path: Path,
    data_root: Path,
    ground_truth_ids: list[str],
    lang: str,
    device: str,
    ocr_version: str,
    model_configuration: dict[str, str],
    overwrite: bool,
) -> tuple[str, int]:
    input_dir = data_root / "input"
    relative_path = image_path.relative_to(input_dir)
    json_output = data_root / "output" / "native_json" / relative_path.with_suffix(".json")
    visualization_output = (
        data_root
        / "output"
        / "visualization"
        / relative_path.with_name(f"{relative_path.stem}_vis.png")
    )

    if json_output.exists() and not overwrite:
        return "skipped", 0

    started = time.perf_counter()
    predictions = list(
        ocr.predict(
            str(image_path),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
        )
    )
    duration_ms = round((time.perf_counter() - started) * 1000)

    texts: list[str] = []
    scores: list[float] = []
    boxes: list[Any] = []
    for prediction in predictions:
        texts.extend(str(value) for value in prediction.get("rec_texts", []))
        scores.extend(float(value) for value in prediction.get("rec_scores", []))
        boxes.extend(jsonable(prediction.get("rec_polys", [])))

    matched_document_id = source_document_id(image_path.stem, ground_truth_ids)
    sample_id = relative_path.with_suffix("").as_posix().replace("/", "__")
    suffix = image_path.stem[len(matched_document_id) :].lstrip("_") if matched_document_id else ""
    native_json = {
        "documentId": matched_document_id or sample_id,
        "sampleId": sample_id,
        "sourceDocumentId": matched_document_id,
        "sourceRelativePath": relative_path.as_posix(),
        "variant": suffix or "original",
        "inputType": image_path.suffix.lstrip(".").upper(),
        "pageCount": 1,
        "processing": {
            "engine": "PaddleOCR",
            "ocrVersion": ocr_version,
            "language": lang,
            "device": device,
            "durationMs": duration_ms,
            "models": model_configuration,
        },
        "pages": [
            {
                "pageIndex": 0,
                "recognizedTexts": texts,
                "recognitionScores": scores,
                "recognizedBoxes": boxes,
            }
        ],
    }

    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(native_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if boxes:
        draw_ocr_boxes(image_path, boxes, visualization_output)
    return "processed", duration_ms


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PaddleOCR local baseline inference.")
    parser.add_argument("--data-root", type=Path, required=True, help="Private baseline data root")
    parser.add_argument("--lang", default="vi")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--ocr-version", default="PP-OCRv4")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N images; 0 means all")
    parser.add_argument("--fail-fast", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    from paddleocr import PaddleOCR

    args = parse_args()
    input_dir = args.data_root / "input"
    if not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    png_files = sorted(input_dir.rglob("*.png"))
    if args.limit > 0:
        png_files = png_files[: args.limit]
    if not png_files:
        raise SystemExit(f"No PNG files found below: {input_dir}")

    print(
        f"Initializing PaddleOCR (lang={args.lang!r}, device={args.device!r}, "
        f"ocr_version={args.ocr_version!r})"
    )
    model_configuration: dict[str, str]
    if args.lang == "vi" and args.ocr_version == "PP-OCRv4":
        # PaddleOCR 3.x has no monolithic vi/v4 registry entry. Match the
        # historical multilingual setup: v4 detector + Vietnamese-capable
        # Latin v3 recognizer, and record both concrete models in every result.
        model_configuration = {
            "textDetection": "PP-OCRv4_mobile_det",
            "textRecognition": "latin_PP-OCRv3_mobile_rec",
        }
        ocr = PaddleOCR(
            text_detection_model_name=model_configuration["textDetection"],
            text_recognition_model_name=model_configuration["textRecognition"],
            device=args.device,
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
        )
    else:
        model_configuration = {"preset": args.ocr_version}
        ocr = PaddleOCR(
            lang=args.lang,
            device=args.device,
            ocr_version=args.ocr_version,
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
        )
    ground_truth_ids = load_ground_truth_ids(args.data_root)

    processed = 0
    skipped = 0
    failures: list[dict[str, str]] = []
    measured_duration_ms = 0
    for index, image_path in enumerate(png_files, start=1):
        try:
            status, duration_ms = run_ocr_file(
                ocr,
                image_path,
                args.data_root,
                ground_truth_ids,
                args.lang,
                args.device,
                args.ocr_version,
                model_configuration,
                args.overwrite,
            )
            processed += status == "processed"
            skipped += status == "skipped"
            measured_duration_ms += duration_ms
        except Exception as exc:  # Continue batch, but fail the command at the end.
            if args.fail_fast:
                raise
            relative = image_path.relative_to(input_dir).as_posix()
            failures.append({"sourceRelativePath": relative, "errorType": type(exc).__name__})
            print(f"ERROR {relative}: {type(exc).__name__}")
        if index % 20 == 0 or index == len(png_files):
            print(f"Progress {index}/{len(png_files)}")

    print(
        f"Complete: processed={processed}, skipped={skipped}, failures={len(failures)}, "
        f"measuredDurationMs={measured_duration_ms}"
    )
    failure_path = args.data_root / "output" / "reports" / "ocr_failures.json"
    if failures:
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(
            json.dumps({"failures": failures}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 1
    if failure_path.exists():
        failure_path.write_text(
            json.dumps({"failures": []}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
