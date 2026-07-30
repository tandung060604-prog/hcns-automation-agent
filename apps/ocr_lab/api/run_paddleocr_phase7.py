#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run improved PaddleOCR profiles without overwriting the Phase 5 baseline."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

if TYPE_CHECKING:
    from paddleocr import PaddleOCR

from run_paddleocr_baseline import (
    draw_ocr_boxes,
    jsonable,
    load_ground_truth_ids,
    source_document_id,
)


PROFILES = {
    "v4_enhanced": {
        "ocrVersion": "PP-OCRv4",
        "textDetection": "PP-OCRv4_mobile_det",
        "textRecognition": "latin_PP-OCRv3_mobile_rec",
    },
    "v5_enhanced": {
        "ocrVersion": "PP-OCRv5",
        "textDetection": "PP-OCRv5_mobile_det",
        "textRecognition": "latin_PP-OCRv5_mobile_rec",
    },
}


def prepare_image(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    image = Image.open(path).convert("RGB")
    original_width, original_height = image.size
    scale = 1
    if original_height < 96:
        scale = min(4, max(2, math.ceil(128 / original_height)))
        image = image.resize(
            (original_width * scale, original_height * scale),
            Image.Resampling.LANCZOS,
        )
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    image = image.filter(ImageFilter.UnsharpMask(radius=1.0, percent=120, threshold=3))
    rgb = np.asarray(image)
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    return bgr, {
        "adaptiveUpscale": scale,
        "originalSize": [original_width, original_height],
        "inferenceSize": [image.width, image.height],
        "autocontrastCutoff": 1,
        "contrastFactor": 1.08,
        "unsharpMask": {"radius": 1.0, "percent": 120, "threshold": 3},
    }


def load_selection(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {item["sampleId"] for item in payload.get("samples", [])}


def run_file(
    ocr: "PaddleOCR",
    image_path: Path,
    data_root: Path,
    profile: str,
    profile_config: dict[str, str],
    ground_truth_ids: list[str],
    overwrite: bool,
) -> tuple[str, int]:
    relative_path = image_path.relative_to(data_root / "input")
    profile_root = data_root / "output" / "phase7" / profile
    json_output = profile_root / "native_json" / relative_path.with_suffix(".json")
    vis_output = (
        profile_root
        / "visualization"
        / relative_path.with_name(f"{relative_path.stem}_vis.png")
    )
    if json_output.exists() and not overwrite:
        return "skipped", 0

    prepared, preprocessing = prepare_image(image_path)
    started = time.perf_counter()
    predictions = list(
        ocr.predict(
            prepared,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
            text_det_limit_side_len=1600,
            text_det_limit_type="max",
            text_det_box_thresh=0.45,
            text_rec_score_thresh=0.0,
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
    native = {
        "documentId": matched_document_id or sample_id,
        "sampleId": sample_id,
        "sourceDocumentId": matched_document_id,
        "sourceRelativePath": relative_path.as_posix(),
        "variant": suffix or "original",
        "inputType": image_path.suffix.lstrip(".").upper(),
        "pageCount": 1,
        "processing": {
            "engine": "PaddleOCR",
            "phase": 7,
            "profile": profile,
            "ocrVersion": profile_config["ocrVersion"],
            "language": "vi",
            "device": "cpu",
            "durationMs": duration_ms,
            "models": {
                "textDetection": profile_config["textDetection"],
                "textRecognition": profile_config["textRecognition"],
            },
            "parameters": {
                "textDetLimitSideLen": 1600,
                "textDetLimitType": "max",
                "textDetBoxThresh": 0.45,
                "textRecScoreThresh": 0.0,
                "enableMkldnn": False,
            },
            "preprocessing": preprocessing,
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
    json_output.write_text(json.dumps(native, ensure_ascii=False, indent=2), encoding="utf-8")
    if boxes:
        draw_ocr_boxes(image_path, boxes, vis_output)
    return "processed", duration_ms


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PaddleOCR Phase 7 profile")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    parser.add_argument("--selection-file", type=Path)
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--fail-fast", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    from paddleocr import PaddleOCR

    args = parse_args()
    profile_config = PROFILES[args.profile]
    selection = load_selection(args.selection_file)
    if args.sample_id:
        selection = set(args.sample_id)

    input_dir = args.data_root / "input"
    image_paths = sorted(input_dir.rglob("*.png"))
    if selection is not None:
        image_paths = [
            path
            for path in image_paths
            if path.relative_to(input_dir).with_suffix("").as_posix().replace("/", "__")
            in selection
        ]
    if args.limit > 0:
        image_paths = image_paths[: args.limit]
    if not image_paths:
        raise SystemExit("No matching PNG files")

    print(f"Initializing profile={args.profile} images={len(image_paths)}")
    ocr = PaddleOCR(
        text_detection_model_name=profile_config["textDetection"],
        text_recognition_model_name=profile_config["textRecognition"],
        device="cpu",
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
        text_det_limit_side_len=1600,
        text_det_limit_type="max",
        text_det_box_thresh=0.45,
        text_rec_score_thresh=0.0,
    )
    ground_truth_ids = load_ground_truth_ids(args.data_root)
    processed = 0
    skipped = 0
    failures: list[dict[str, str]] = []
    measured_ms = 0
    for index, image_path in enumerate(image_paths, start=1):
        try:
            status, duration_ms = run_file(
                ocr,
                image_path,
                args.data_root,
                args.profile,
                profile_config,
                ground_truth_ids,
                args.overwrite,
            )
            processed += status == "processed"
            skipped += status == "skipped"
            measured_ms += duration_ms
        except Exception as exc:
            if args.fail_fast:
                raise
            failures.append(
                {
                    "sourceRelativePath": image_path.relative_to(input_dir).as_posix(),
                    "errorType": type(exc).__name__,
                }
            )
            print(
                f"ERROR {image_path.relative_to(input_dir).as_posix()}: "
                f"{type(exc).__name__}"
            )
        if index % 10 == 0 or index == len(image_paths):
            print(f"Progress {index}/{len(image_paths)}")

    failure_path = (
        args.data_root / "output" / "phase7" / args.profile / "reports" / "failures.json"
    )
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(
        json.dumps({"failures": failures}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Complete: processed={processed}, skipped={skipped}, "
        f"failures={len(failures)}, measuredDurationMs={measured_ms}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
