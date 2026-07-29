#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the Phase 14.2 controlled OCR pilot on private local sessions.

PaddleOCR supplies detector boxes and a secondary recognition candidate.
VietOCR recognizes a fixed high-resolution crop as the primary candidate.
Only exact normalized agreement is auto-accepted. Raw text is written only
inside the private session output and is never printed to the console.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
from vietocr.tool.config import Cfg
from vietocr.tool.predictor import Predictor

from phase14_ocr_hardening import bbox_crop
from run_hybrid_phase13_3 import (
    SESSION_ID_RE,
    confidence,
    detection_pages,
    line_box,
    normalized,
    page_source,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Phase 14.2 controlled OCR pilot"
    )
    parser.add_argument("--data-root", type=Path, required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--session-id")
    target.add_argument("--all", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(ratio * len(ordered)) - 1))
    return round(ordered[index], 3)


def candidate_is_valid(value: str) -> bool:
    compact = normalized(value)
    return bool(compact and any(character.isalnum() for character in compact))


def line_decision(primary_text: str, verifier_text: str) -> dict[str, Any]:
    primary_valid = candidate_is_valid(primary_text)
    verifier_valid = candidate_is_valid(verifier_text)
    exact_agreement = (
        primary_valid
        and verifier_valid
        and normalized(primary_text) == normalized(verifier_text)
    )
    return {
        "status": "accepted" if exact_agreement else "needs_review",
        "selectedText": primary_text,
        "primaryValid": primary_valid,
        "verifierValid": verifier_valid,
        "exactAgreement": exact_agreement,
        "rule": (
            "vietocr_primary_exactly_confirmed_by_paddle"
            if exact_agreement
            else "vietocr_primary_preserved_pending_human_review"
        ),
    }


def session_candidates(data_root: Path, session_id: str | None) -> list[Path]:
    sessions_root = data_root / "user_uploads" / "sessions"
    if session_id:
        if not SESSION_ID_RE.fullmatch(session_id):
            raise ValueError("Invalid session id")
        candidate = sessions_root / session_id
        if not (candidate / "result.json").is_file():
            raise FileNotFoundError("Session result not found")
        return [candidate]
    if not sessions_root.is_dir():
        return []
    return sorted(
        directory
        for directory in sessions_root.iterdir()
        if directory.is_dir() and (directory / "result.json").is_file()
    )


def build_predictor() -> Predictor:
    config = Cfg.load_config_from_name("vgg_seq2seq")
    config["device"] = "cpu"
    config["cnn"]["pretrained"] = False
    return Predictor(config)


def process_session(
    session_dir: Path,
    predictor: Predictor,
    *,
    overwrite: bool,
) -> dict[str, Any]:
    result_path = session_dir / "result.json"
    output_dir = session_dir / "phase14_2"
    output_path = output_dir / "controlled_pilot.json"
    if output_path.exists() and not overwrite:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        return {
            "outcome": "reused",
            "summary": payload.get("summary", {}),
            "runtime": payload.get("runtime", {}),
        }

    result = json.loads(result_path.read_text(encoding="utf-8"))
    source_name, pages = detection_pages(result)
    started = time.perf_counter()
    durations: list[float] = []
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
            crop = bbox_crop(
                image,
                np.asarray(box, dtype=np.float32),
                pad_x_ratio=0.18,
                pad_y_ratio=0.12,
                target_height=64,
            )
            crop_path = page_crop_dir / f"line_{line_index:04d}.png"
            if not cv2.imwrite(str(crop_path), crop):
                raise RuntimeError("Cannot write private line crop")
            crop_count += 1

            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            recognize_started = time.perf_counter()
            primary_text, primary_probability = predictor.predict(
                Image.fromarray(rgb), return_prob=True
            )
            duration_ms = (time.perf_counter() - recognize_started) * 1000
            durations.append(duration_ms)
            primary_text = str(primary_text)
            verifier_text = str(line.get("rawText") or line.get("text") or "")
            decision = line_decision(primary_text, verifier_text)
            if decision["status"] == "accepted":
                accepted_count += 1
            else:
                review_count += 1
            output_lines.append(
                {
                    "lineIndex": line_index,
                    "box": box,
                    "cropProfile": "bbox_balanced_64",
                    "primary": {
                        "engine": "VietOCR",
                        "model": "vgg_seq2seq",
                        "text": primary_text,
                        "confidence": confidence(primary_probability),
                        "durationMs": round(duration_ms, 3),
                    },
                    "verifier": {
                        "engine": "PaddleOCR",
                        "source": source_name,
                        "text": verifier_text,
                        "confidence": confidence(line.get("confidence")),
                    },
                    "decision": decision,
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
                    line["decision"]["status"] == "accepted"
                    for line in output_lines
                ),
                "needsReviewLineCount": sum(
                    line["decision"]["status"] == "needs_review"
                    for line in output_lines
                ),
                "lines": output_lines,
            }
        )

    payload = {
        "schemaVersion": "14.2.0-controlled-pilot",
        "sessionId": session_dir.name,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "containsRealPII": True,
        "status": (
            "CONTROLLED_PILOT_NEEDS_REVIEW"
            if review_count
            else "CONTROLLED_PILOT_ALL_LINES_AGREED"
        ),
        "policy": {
            "detector": "PaddleOCR PP-OCRv5 detector boxes",
            "cropProfile": "bbox_balanced_64",
            "primaryRecognizer": "VietOCR/vgg_seq2seq",
            "verifier": "PaddleOCR PP-OCRv5 Vietnamese recognizer",
            "autoAcceptRule": (
                "Primary and verifier must be non-empty and exactly agree after "
                "NFC + casefold + whitespace normalization"
            ),
            "disagreementRule": "Keep VietOCR candidate and require human review",
            "confidenceAloneCanAutoAccept": False,
            "productionPromotionAllowed": False,
            "policyEvidence": (
                "Phase 14.1 user-reviewed 77-line crop benchmark"
            ),
        },
        "runtime": {
            "vietocrVersion": importlib.metadata.version("vietocr"),
            "device": "cpu",
            "durationMs": round((time.perf_counter() - started) * 1000),
            "meanRecognitionDurationMs": round(
                sum(durations) / max(1, len(durations)), 3
            ),
            "p95RecognitionDurationMs": percentile(durations, 0.95),
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
    return {
        "outcome": "processed",
        "summary": payload["summary"],
        "runtime": payload["runtime"],
    }


def write_batch_report(
    data_root: Path,
    *,
    results: list[dict[str, Any]],
    failures: list[str],
) -> dict[str, Any]:
    output_root = data_root / "output" / "phase14_2"
    output_root.mkdir(parents=True, exist_ok=True)
    summaries = [item["summary"] for item in results]
    runtimes = [item["runtime"] for item in results]
    crop_count = sum(int(item.get("cropCount", 0)) for item in summaries)
    accepted_count = sum(
        int(item.get("acceptedLineCount", 0)) for item in summaries
    )
    review_count = sum(
        int(item.get("needsReviewLineCount", 0)) for item in summaries
    )
    evaluation_path = (
        data_root
        / "output"
        / "phase14"
        / "PHASE14_REVIEWED_EVALUATION.json"
    )
    reviewed_evaluation: dict[str, Any] = {}
    if evaluation_path.is_file():
        source = json.loads(evaluation_path.read_text(encoding="utf-8"))
        reviewed_evaluation = {
            "groundTruthStatus": source.get("groundTruthStatus"),
            "lineCount": source.get("lineCount"),
            "reviewedLineCount": source.get("reviewedLineCount"),
            "profiles": source.get("profiles", {}),
            "selection": {
                key: source.get("selection", {}).get(key)
                for key in (
                    "recommendedPrimary",
                    "promotionDecision",
                    "productionDecision",
                    "verifierPolicy",
                )
            },
        }
    payload = {
        "schemaVersion": "14.2.0-private-aggregate",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "containsRealPII": False,
        "sourceCorpus": "authorized_local_user_sessions",
        "sessionCount": len(results),
        "failedSessionCount": len(failures),
        "failureTypes": sorted(failures),
        "summary": {
            "cropCount": crop_count,
            "acceptedLineCount": accepted_count,
            "needsReviewLineCount": review_count,
            "acceptanceRate": round(accepted_count / max(1, crop_count), 6),
            "totalDurationMs": round(
                sum(float(item.get("durationMs", 0)) for item in runtimes), 3
            ),
        },
        "reviewedAccuracyReference": reviewed_evaluation,
        "decision": {
            "pilotStatus": "CONTROLLED_PILOT_COMPLETE",
            "productionStatus": "NOT_PRODUCTION_READY",
            "reason": (
                "Operational coverage is measured on all eligible sessions; "
                "accuracy remains limited to user-reviewed crop Ground Truth"
            ),
        },
    }
    json_path = output_root / "CONTROLLED_PILOT_SUMMARY.json"
    report_path = output_root / "PHASE14_2_RESULTS.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = f"""# Phase 14.2 — Controlled OCR pilot

- Session xử lý được: {len(results)}
- Session bỏ qua do lỗi kỹ thuật/không có trang OCR: {len(failures)}
- Dòng crop: {crop_count}
- Tự động chấp nhận bằng exact agreement: {accepted_count} ({payload['summary']['acceptanceRate']:.2%})
- Cần review: {review_count}
- Production: `NOT_PRODUCTION_READY`

Accuracy chỉ lấy từ 77 dòng Ground Truth cấp crop đã được người dùng xác nhận.
Các session còn lại chỉ được dùng để đo coverage và tỷ lệ chuyển `needs_review`.
Không có trường nào được auto-accept chỉ dựa trên confidence.
"""
    report_path.write_text(report, encoding="utf-8")
    return payload


def main() -> int:
    args = parse_args()
    try:
        sessions = session_candidates(args.data_root, args.session_id)
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
    if not sessions:
        raise SystemExit("No eligible local session found")

    predictor = build_predictor()
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for session_dir in sessions:
        try:
            results.append(
                process_session(
                    session_dir,
                    predictor,
                    overwrite=args.overwrite,
                )
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            failures.append(type(exc).__name__)
            if args.session_id:
                raise SystemExit(f"Controlled pilot failed: {type(exc).__name__}") from exc

    aggregate = write_batch_report(
        args.data_root,
        results=results,
        failures=failures,
    )
    print(
        json.dumps(
            {
                "sessionCount": aggregate["sessionCount"],
                "failedSessionCount": aggregate["failedSessionCount"],
                **aggregate["summary"],
                "productionStatus": aggregate["decision"]["productionStatus"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
