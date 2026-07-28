#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the local EasyOCR Vietnamese challenger on one authorized session."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import easyocr
import cv2

from phase11_cccd import extract_cccd_fields


SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EasyOCR Vietnamese challenger")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def jsonable_box(box: Any) -> list[list[float]]:
    return [[round(float(point[0]), 3), round(float(point[1]), 3)] for point in box]


def main() -> int:
    args = parse_args()
    if not SESSION_ID_RE.fullmatch(args.session_id):
        raise SystemExit("Invalid session id")
    session_dir = args.data_root / "user_uploads" / "sessions" / args.session_id
    if not session_dir.is_dir():
        raise SystemExit("Session not found")
    page_paths = sorted((session_dir / "pages").glob("page_*.png"))
    if not page_paths:
        raise SystemExit("No rendered pages found")
    output_dir = session_dir / "phase10"
    output_path = output_dir / "easyocr.json"
    if output_path.exists() and not args.overwrite:
        raise SystemExit("EasyOCR result exists; pass --overwrite")

    model_root = args.data_root / "runtime" / "easyocr_models"
    started = time.perf_counter()
    native_result = json.loads(
        (session_dir / "result.json").read_text(encoding="utf-8")
    )
    use_routed_pages = (
        native_result.get("phase9", {}).get("selectedVariant")
        == "phase9_routed"
    )
    phase9_pages = native_result.get("phase9", {}).get("pages", [])
    phase11 = native_result.get("phase11", {})
    use_phase11_pages = phase11.get("status") in {"PASS", "NEEDS_REVIEW"}
    phase11_pages = phase11.get("pages", [])
    reader = easyocr.Reader(
        ["vi", "en"],
        gpu=False,
        model_storage_directory=str(model_root),
        download_enabled=True,
        verbose=False,
    )
    pages: list[dict[str, Any]] = []
    all_scores: list[float] = []
    for page_index, page_path in enumerate(page_paths):
        page_started = time.perf_counter()
        recognition_path = (
            session_dir / "phase11" / "pages" / page_path.name
            if use_phase11_pages
            and (session_dir / "phase11" / "pages" / page_path.name).is_file()
            else
            session_dir / "phase9" / "pages" / page_path.name
            if use_routed_pages
            and (session_dir / "phase9" / "pages" / page_path.name).is_file()
            else page_path
        )
        detection_lines = (
            phase11_pages[page_index].get("lines", [])
            if use_phase11_pages and page_index < len(phase11_pages)
            else
            phase9_pages[page_index].get("lines", [])
            if page_index < len(phase9_pages)
            else []
        )
        horizontal_list = []
        vertical_region_count = 0
        for line in detection_lines:
            box = line.get("box", [])
            if not box:
                continue
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            if max(ys) - min(ys) > (max(xs) - min(xs)) * 1.15:
                vertical_region_count += 1
            padding = 3
            horizontal_list.append(
                [
                    max(0, int(min(xs)) - padding),
                    int(max(xs)) + padding,
                    max(0, int(min(ys)) - padding),
                    int(max(ys)) + padding,
                ]
            )
        image = cv2.imread(str(recognition_path), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("Cannot read rendered page")
        if horizontal_list:
            predictions = reader.recognize(
                image,
                horizontal_list=horizontal_list,
                free_list=[],
                detail=1,
                paragraph=False,
                decoder="beamsearch",
                batch_size=1,
                workers=0,
                rotation_info=[90, 180, 270],
            )
            detection_source = (
                "paddle_phase11_boxes"
                if use_phase11_pages
                else "paddle_phase9_boxes"
            )
        else:
            predictions = reader.readtext(
                image,
                detail=1,
                paragraph=False,
                decoder="beamsearch",
                batch_size=1,
                workers=0,
                mag_ratio=1.5,
                rotation_info=[90, 180, 270],
            )
            detection_source = "easyocr"
        lines = [
            {
                "text": str(text),
                "confidence": round(float(score), 6),
                "box": jsonable_box(box),
            }
            for box, text, score in predictions
        ]
        all_scores.extend(line["confidence"] for line in lines)
        pages.append(
            {
                "pageIndex": page_index,
                "recognizedText": "\n".join(line["text"] for line in lines),
                "recognizedTextLineCount": len(lines),
                "avgConfidence": (
                    round(sum(line["confidence"] for line in lines) / len(lines), 6)
                    if lines
                    else None
                ),
                "durationMs": round((time.perf_counter() - page_started) * 1000),
                "detectionSource": detection_source,
                "verticalRegionCount": vertical_region_count,
                "rotationCandidatesDegrees": [0, 90, 180, 270],
                "lines": lines,
            }
        )
    identity_card = (
        extract_cccd_fields(pages, engine="EasyOCR/vi+en")
        if use_phase11_pages
        else None
    )
    result = {
        "schemaVersion": "1.1.0",
        "sessionId": args.session_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "containsRealPII": True,
        "status": "CHALLENGER_UNVERIFIED",
        "processing": {
            "engine": "EasyOCR",
            "version": easyocr.__version__,
            "languages": ["vi", "en"],
            "device": "cpu",
            "decoder": "beamsearch",
            "rotationInfoDegrees": [90, 180, 270],
            "durationMs": round((time.perf_counter() - started) * 1000),
        },
        "document": {
            "pageCount": len(pages),
            "recognizedTextLineCount": sum(
                page["recognizedTextLineCount"] for page in pages
            ),
            "avgConfidence": (
                round(sum(all_scores) / len(all_scores), 6) if all_scores else None
            ),
            "identityCard": identity_card,
            "pages": pages,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "pageCount": len(pages),
                "lineCount": result["document"]["recognizedTextLineCount"],
                "avgConfidence": result["document"]["avgConfidence"],
                "durationMs": result["processing"]["durationMs"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
