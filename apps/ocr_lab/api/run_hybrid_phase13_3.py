#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recognize Paddle-detected lines with EasyOCR and verify with VietOCR.

All artifacts produced by this pilot remain inside the private session directory.
The worker never prints recognized text because sessions may contain real PII.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import easyocr
from PIL import Image
from vietocr.tool.config import Cfg
from vietocr.tool.predictor import Predictor


SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 13.3 hybrid OCR pilot")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def confidence(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 6)
    except (TypeError, ValueError):
        return 0.0


def easy_value(results: Any) -> tuple[str, float]:
    if not results or len(results[0]) < 3:
        return "", 0.0
    return str(results[0][1]), confidence(results[0][2])


def page_source(session_dir: Path, result: dict[str, Any], page_index: int) -> Path:
    page_name = f"page_{page_index:03d}.png"
    candidates = [
        session_dir / "phase11" / "pages" / page_name,
        session_dir / "phase9" / "pages" / page_name,
        session_dir / "pages" / page_name,
    ]
    phase11_ready = result.get("phase11", {}).get("status") in {
        "PASS",
        "NEEDS_REVIEW",
    }
    phase9_routed = result.get("phase9", {}).get("selectedVariant") == "phase9_routed"
    if not phase11_ready:
        candidates.pop(0)
    if not phase9_routed:
        candidates = [path for path in candidates if "phase9" not in path.parts]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No page image for page {page_index}")


def detection_pages(result: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    phase11 = result.get("phase11", {})
    if phase11.get("status") in {"PASS", "NEEDS_REVIEW"} and phase11.get("pages"):
        return "paddle_phase11_boxes", list(phase11["pages"])
    phase9 = result.get("phase9", {})
    if phase9.get("pages"):
        return "paddle_phase9_boxes", list(phase9["pages"])
    return "paddle_native_boxes", list(result.get("document", {}).get("pages", []))


def line_box(line: dict[str, Any]) -> list[list[float]]:
    raw_box = line.get("box") or []
    if len(raw_box) != 4:
        return []
    try:
        return [[round(float(point[0]), 3), round(float(point[1]), 3)] for point in raw_box]
    except (TypeError, ValueError, IndexError):
        return []


def crop_line(image: Any, box: list[list[float]]) -> Any:
    height, width = image.shape[:2]
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    line_height = max(1.0, max(ys) - min(ys))
    pad_x = max(4, round(line_height * 0.18))
    pad_y = max(3, round(line_height * 0.12))
    left = max(0, int(min(xs)) - pad_x)
    right = min(width, int(max(xs)) + pad_x)
    top = max(0, int(min(ys)) - pad_y)
    bottom = min(height, int(max(ys)) + pad_y)
    if right <= left or bottom <= top:
        raise ValueError("Invalid detector box")
    crop = image[top:bottom, left:right]
    target_height = max(64, crop.shape[0])
    scale = min(4.0, target_height / max(1, crop.shape[0]))
    if scale > 1.0:
        crop = cv2.resize(
            crop,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
    return crop


def main() -> int:
    args = parse_args()
    if not SESSION_ID_RE.fullmatch(args.session_id):
        raise SystemExit("Invalid session id")
    session_dir = args.data_root / "user_uploads" / "sessions" / args.session_id
    result_path = session_dir / "result.json"
    if not result_path.is_file():
        raise SystemExit("Session result not found")
    output_dir = session_dir / "phase13_3"
    output_path = output_dir / "hybrid_ocr.json"
    if output_path.exists() and not args.overwrite:
        raise SystemExit("Hybrid result exists; pass --overwrite")

    result = json.loads(result_path.read_text(encoding="utf-8"))
    source_name, pages = detection_pages(result)
    model_root = args.data_root / "runtime" / "easyocr_models"
    started = time.perf_counter()
    easy_reader = easyocr.Reader(
        ["vi"],
        gpu=False,
        model_storage_directory=str(model_root),
        download_enabled=True,
        verbose=False,
    )
    viet_config = Cfg.load_config_from_name("vgg_seq2seq")
    viet_config["device"] = "cpu"
    viet_config["cnn"]["pretrained"] = False
    viet_predictor = Predictor(viet_config)

    output_pages: list[dict[str, Any]] = []
    accepted_count = 0
    review_count = 0
    crop_count = 0
    for page_index, page in enumerate(pages):
        image_path = page_source(session_dir, result, page_index)
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Cannot read page {page_index}")
        page_crop_dir = output_dir / "crops" / f"page_{page_index:03d}"
        page_crop_dir.mkdir(parents=True, exist_ok=True)
        output_lines: list[dict[str, Any]] = []
        for line_index, line in enumerate(page.get("lines", [])):
            box = line_box(line)
            if not box:
                continue
            try:
                crop = crop_line(image, box)
            except ValueError:
                continue
            crop_path = page_crop_dir / f"line_{line_index:04d}.png"
            if not cv2.imwrite(str(crop_path), crop):
                raise RuntimeError("Cannot write private line crop")
            crop_count += 1

            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            crop_height, crop_width = gray.shape[:2]
            easy_started = time.perf_counter()
            easy_results = easy_reader.recognize(
                gray,
                horizontal_list=[[0, crop_width, 0, crop_height]],
                free_list=[],
                decoder="greedy",
                batch_size=1,
                detail=1,
                reformat=False,
                contrast_ths=0.05,
                adjust_contrast=0.7,
            )
            easy_duration = (time.perf_counter() - easy_started) * 1000
            easy_text, easy_confidence = easy_value(easy_results)

            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            viet_started = time.perf_counter()
            viet_text, viet_probability = viet_predictor.predict(
                Image.fromarray(rgb), return_prob=True
            )
            viet_duration = (time.perf_counter() - viet_started) * 1000
            viet_text = str(viet_text)
            paddle_text = str(line.get("rawText") or line.get("text") or "")
            paddle_easy_agreed = bool(normalized(paddle_text)) and normalized(
                paddle_text
            ) == normalized(easy_text)
            paddle_viet_agreed = bool(normalized(paddle_text)) and normalized(
                paddle_text
            ) == normalized(viet_text)
            verified = paddle_easy_agreed or paddle_viet_agreed
            status = "accepted" if verified else "needs_review"
            if verified:
                accepted_count += 1
            else:
                review_count += 1
            output_lines.append(
                {
                    "lineIndex": line_index,
                    "box": box,
                    "detector": {
                        "engine": "PaddleOCR",
                        "source": source_name,
                        "rawText": paddle_text,
                        "confidence": confidence(line.get("confidence")),
                    },
                    "primary": {
                        "engine": "EasyOCR",
                        "model": "vi",
                        "text": easy_text,
                        "confidence": easy_confidence,
                        "durationMs": round(easy_duration, 3),
                    },
                    "verifier": {
                        "engine": "VietOCR",
                        "model": "vgg_seq2seq",
                        "text": viet_text,
                        "confidence": confidence(viet_probability),
                        "durationMs": round(viet_duration, 3),
                    },
                    "decision": {
                        "status": status,
                        "selectedText": paddle_text,
                        "paddleEasyAgreed": paddle_easy_agreed,
                        "paddleVietAgreed": paddle_viet_agreed,
                        "rule": (
                            "paddle_confirmed_by_at_least_one_independent_recognizer"
                            if verified
                            else "paddle_preserved_pending_human_review"
                        ),
                    },
                }
            )
        output_pages.append(
            {
                "pageIndex": page_index,
                "recognizedText": "\n".join(
                    line["decision"]["selectedText"] for line in output_lines
                ),
                "lineCount": len(output_lines),
                "acceptedLineCount": sum(
                    line["decision"]["status"] == "accepted" for line in output_lines
                ),
                "needsReviewLineCount": sum(
                    line["decision"]["status"] == "needs_review"
                    for line in output_lines
                ),
                "lines": output_lines,
            }
        )

    payload = {
        "schemaVersion": "13.3.0-pilot",
        "sessionId": args.session_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "containsRealPII": True,
        "status": "PILOT_NEEDS_REVIEW" if review_count else "PILOT_ALL_LINES_AGREED",
        "policy": {
            "detector": "PaddleOCR",
            "primaryRecognizer": "PaddleOCR raw recognition",
            "verifiers": ["EasyOCR/vi", "VietOCR/vgg_seq2seq"],
            "autoAcceptRule": (
                "Paddle candidate must match EasyOCR or VietOCR after "
                "NFC + casefold + whitespace normalization"
            ),
            "disagreementRule": "Keep Paddle candidate and require human review",
            "policyEvidence": (
                "Phase 14 provisional real-scan benchmark: Paddle raw "
                "outperformed both crop recognizers"
            ),
            "productionPromotionAllowed": False,
        },
        "runtime": {
            "easyocrVersion": importlib.metadata.version("easyocr"),
            "vietocrVersion": importlib.metadata.version("vietocr"),
            "device": "cpu",
            "durationMs": round((time.perf_counter() - started) * 1000),
        },
        "summary": {
            "pageCount": len(output_pages),
            "cropCount": crop_count,
            "acceptedLineCount": accepted_count,
            "needsReviewLineCount": review_count,
            "acceptanceRate": round(accepted_count / max(1, crop_count), 6),
        },
        "pages": output_pages,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "pageCount": len(output_pages),
                "cropCount": crop_count,
                "acceptedLineCount": accepted_count,
                "needsReviewLineCount": review_count,
                "durationMs": payload["runtime"]["durationMs"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
