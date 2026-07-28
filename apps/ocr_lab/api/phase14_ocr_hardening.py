#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 14 real-scan line recognition hardening.

Only page-reviewed sessions whose non-empty Ground Truth line count exactly
matches the Paddle crop count are eligible for automatic index alignment.
Detailed text stays in private-data and console output is aggregate-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import cv2
import easyocr
import numpy as np
from PIL import Image
from vietocr.tool.config import Cfg
from vietocr.tool.predictor import Predictor

from canonical_phase_metrics import aggregate_profile
from run_hybrid_phase13_3 import confidence, normalized, page_source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 14 OCR hardening")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def edit_distance(reference: Sequence[Any], hypothesis: Sequence[Any]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, ref_item in enumerate(reference, start=1):
        current = [row]
        for column, hyp_item in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (ref_item != hyp_item),
                )
            )
        previous = current
    return previous[-1]


def strip_diacritics(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value)
        if unicodedata.category(character) != "Mn"
    )


def aggregate(cases: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    return aggregate_profile(
        cases,
        profile,
        lambda case: str(case["groundTruth"]),
    )


def points(raw_box: Any) -> np.ndarray:
    array = np.asarray(raw_box, dtype=np.float32)
    if array.shape != (4, 2):
        raise ValueError("Expected a four-point detector box")
    sums = array.sum(axis=1)
    diffs = np.diff(array, axis=1).reshape(-1)
    return np.asarray(
        [
            array[np.argmin(sums)],
            array[np.argmin(diffs)],
            array[np.argmax(sums)],
            array[np.argmax(diffs)],
        ],
        dtype=np.float32,
    )


def resize_height(image: np.ndarray, target_height: int) -> np.ndarray:
    if image.shape[0] >= target_height:
        return image
    scale = min(5.0, target_height / max(1, image.shape[0]))
    return cv2.resize(
        image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
    )


def bbox_crop(
    image: np.ndarray,
    box: np.ndarray,
    *,
    pad_x_ratio: float,
    pad_y_ratio: float,
    target_height: int,
) -> np.ndarray:
    height, width = image.shape[:2]
    line_height = max(1.0, float(box[:, 1].max() - box[:, 1].min()))
    pad_x = max(2, round(line_height * pad_x_ratio))
    pad_y = max(2, round(line_height * pad_y_ratio))
    left = max(0, int(box[:, 0].min()) - pad_x)
    right = min(width, int(box[:, 0].max()) + pad_x)
    top = max(0, int(box[:, 1].min()) - pad_y)
    bottom = min(height, int(box[:, 1].max()) + pad_y)
    if right <= left or bottom <= top:
        raise ValueError("Invalid crop bounds")
    return resize_height(image[top:bottom, left:right], target_height)


def perspective_crop(
    image: np.ndarray, box: np.ndarray, *, target_height: int
) -> np.ndarray:
    ordered = points(box)
    top_left, top_right, bottom_right, bottom_left = ordered
    width = max(
        1,
        round(
            max(
                np.linalg.norm(top_right - top_left),
                np.linalg.norm(bottom_right - bottom_left),
            )
        ),
    )
    height = max(
        1,
        round(
            max(
                np.linalg.norm(bottom_left - top_left),
                np.linalg.norm(bottom_right - top_right),
            )
        ),
    )
    destination = np.asarray(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(ordered, destination)
    crop = cv2.warpPerspective(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    border = max(3, round(height * 0.12))
    crop = cv2.copyMakeBorder(
        crop,
        border,
        border,
        border,
        border,
        cv2.BORDER_CONSTANT,
        value=(255, 255, 255),
    )
    return resize_height(crop, target_height)


def easy_recognize(
    reader: Any, image: np.ndarray, *, decoder: str, clahe: bool
) -> tuple[str, float, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if clahe:
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    height, width = gray.shape[:2]
    started = time.perf_counter()
    result = reader.recognize(
        gray,
        horizontal_list=[[0, width, 0, height]],
        free_list=[],
        decoder=decoder,
        batch_size=1,
        detail=1,
        reformat=False,
        contrast_ths=0.05,
        adjust_contrast=0.7,
    )
    duration = (time.perf_counter() - started) * 1000
    if not result or len(result[0]) < 3:
        return "", 0.0, duration
    return str(result[0][1]), confidence(result[0][2]), duration


def eligible_sessions(data_root: Path) -> list[dict[str, Any]]:
    sessions_root = data_root / "user_uploads" / "sessions"
    output: list[dict[str, Any]] = []
    for session_dir in sessions_root.iterdir():
        gt_path = session_dir / "phase10" / "ground_truth.json"
        result_path = session_dir / "result.json"
        hybrid_path = session_dir / "phase13_3" / "hybrid_ocr.json"
        if not (gt_path.is_file() and result_path.is_file() and hybrid_path.is_file()):
            continue
        ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
        assertions = ground_truth.get("verificationAssertions", {})
        if not (
            assertions.get("comparedWithImage")
            and assertions.get("allTextChecked")
            and len(ground_truth.get("identityFields") or {}) == 8
        ):
            continue
        gt_lines = [
            line.strip()
            for page in ground_truth.get("pages", [])
            for line in str(page.get("text", "")).splitlines()
            if line.strip()
        ]
        hybrid = json.loads(hybrid_path.read_text(encoding="utf-8"))
        hybrid_lines = [
            line for page in hybrid.get("pages", []) for line in page.get("lines", [])
        ]
        if gt_lines and len(gt_lines) == len(hybrid_lines):
            output.append(
                {
                    "sessionDir": session_dir,
                    "result": json.loads(result_path.read_text(encoding="utf-8")),
                    "groundTruthLines": gt_lines,
                    "hybridLines": hybrid_lines,
                    "groundTruthSha256": hashlib.sha256(gt_path.read_bytes()).hexdigest(),
                }
            )
    output.sort(key=lambda item: item["sessionDir"].name)
    return output


def main() -> int:
    args = parse_args()
    output_root = args.data_root / "output" / "phase14"
    detailed_path = output_root / "line_benchmark_private.json"
    report_path = output_root / "PHASE14_OCR_RESULTS.md"
    if detailed_path.exists() and not args.overwrite:
        raise SystemExit("Phase 14 output exists; pass --overwrite")
    crop_root = output_root / "crops"
    crop_root.mkdir(parents=True, exist_ok=True)

    sessions = eligible_sessions(args.data_root)
    if not sessions:
        raise SystemExit("No safely index-aligned reviewed sessions found")
    reader = easyocr.Reader(
        ["vi"],
        gpu=False,
        model_storage_directory=str(args.data_root / "runtime" / "easyocr_models"),
        download_enabled=True,
        verbose=False,
    )
    crop_profiles = {
        "bbox_balanced_64": ("bbox", 0.18, 0.12, 64),
        "bbox_tight_96": ("bbox", 0.08, 0.06, 96),
        "bbox_generous_96": ("bbox", 0.30, 0.20, 96),
        "perspective_96": ("perspective", 0.0, 0.0, 96),
    }
    recognition_profiles = {
        "greedy": ("greedy", False),
        "beamsearch": ("beamsearch", False),
        "clahe_greedy": ("greedy", True),
    }
    cases: list[dict[str, Any]] = []
    for session in sessions:
        session_id = session["sessionDir"].name
        page_cache: dict[int, np.ndarray] = {}
        for line_offset, (ground_truth, hybrid_line) in enumerate(
            zip(
                session["groundTruthLines"],
                session["hybridLines"],
                strict=True,
            )
        ):
            page_index = 0
            for page in json.loads(
                (
                    session["sessionDir"] / "phase13_3" / "hybrid_ocr.json"
                ).read_text(encoding="utf-8")
            ).get("pages", []):
                page_lines = page.get("lines", [])
                if hybrid_line in page_lines:
                    page_index = int(page.get("pageIndex", 0))
                    break
            if page_index not in page_cache:
                path = page_source(
                    session["sessionDir"], session["result"], page_index
                )
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is None:
                    raise RuntimeError("Cannot read private source page")
                page_cache[page_index] = image
            image = page_cache[page_index]
            box = np.asarray(hybrid_line["box"], dtype=np.float32)
            case_id = hashlib.sha256(
                f"{session_id}:{line_offset}".encode("utf-8")
            ).hexdigest()[:20]
            case = {
                "caseId": case_id,
                "sessionId": session_id,
                "pageIndex": page_index,
                "lineIndex": int(hybrid_line.get("lineIndex", line_offset)),
                "alignment": "page_reviewed_equal_line_count_index",
                "groundTruth": ground_truth,
                "predictions": {
                    "paddle_detector_raw": {
                        "text": hybrid_line.get("detector", {}).get("rawText", ""),
                        "confidence": hybrid_line.get("detector", {}).get(
                            "confidence", 0.0
                        ),
                        "durationMs": 0.0,
                    }
                },
                "crops": {},
            }
            for crop_name, (kind, pad_x, pad_y, target_height) in crop_profiles.items():
                crop = (
                    perspective_crop(image, box, target_height=target_height)
                    if kind == "perspective"
                    else bbox_crop(
                        image,
                        box,
                        pad_x_ratio=pad_x,
                        pad_y_ratio=pad_y,
                        target_height=target_height,
                    )
                )
                crop_path = crop_root / f"{case_id}_{crop_name}.png"
                if not cv2.imwrite(str(crop_path), crop):
                    raise RuntimeError("Cannot write private Phase 14 crop")
                case["crops"][crop_name] = {
                    "path": str(crop_path.relative_to(output_root)),
                    "sha256": hashlib.sha256(crop_path.read_bytes()).hexdigest(),
                }
                for rec_name, (decoder, clahe) in recognition_profiles.items():
                    text, score, duration = easy_recognize(
                        reader, crop, decoder=decoder, clahe=clahe
                    )
                    case["predictions"][f"easy_{crop_name}_{rec_name}"] = {
                        "text": text,
                        "confidence": score,
                        "durationMs": round(duration, 3),
                    }
            cases.append(case)

    easy_profiles = [
        profile
        for profile in cases[0]["predictions"]
        if profile.startswith("easy_")
    ]
    aggregate_results = {
        "paddle_detector_raw": aggregate(cases, "paddle_detector_raw")
    }
    aggregate_results.update(
        {profile: aggregate(cases, profile) for profile in easy_profiles}
    )
    best_easy = sorted(
        easy_profiles,
        key=lambda profile: (
            -aggregate_results[profile]["exactMatchRate"],
            aggregate_results[profile]["diacriticErrorRate"],
            aggregate_results[profile]["cer"],
            aggregate_results[profile]["p95DurationMs"],
        ),
    )[0]
    best_crop = next(
        name for name in crop_profiles if f"easy_{name}_" in best_easy
    )

    viet_config = Cfg.load_config_from_name("vgg_seq2seq")
    viet_config["device"] = "cpu"
    viet_config["cnn"]["pretrained"] = False
    viet_predictor = Predictor(viet_config)
    for case in cases:
        crop_path = output_root / case["crops"][best_crop]["path"]
        with Image.open(crop_path) as image:
            started = time.perf_counter()
            text, score = viet_predictor.predict(
                image.convert("RGB"), return_prob=True
            )
            duration = (time.perf_counter() - started) * 1000
        case["predictions"]["vietocr_best_crop"] = {
            "text": str(text),
            "confidence": confidence(score),
            "durationMs": round(duration, 3),
        }
    aggregate_results["vietocr_best_crop"] = aggregate(
        cases, "vietocr_best_crop"
    )
    easy_viet_agreed = [
        case
        for case in cases
        if normalized(case["predictions"][best_easy]["text"])
        and normalized(case["predictions"][best_easy]["text"])
        == normalized(case["predictions"]["vietocr_best_crop"]["text"])
    ]
    easy_viet_exact = sum(
        normalized(case["predictions"][best_easy]["text"])
        == normalized(case["groundTruth"])
        for case in easy_viet_agreed
    )
    paddle_verified = [
        case
        for case in cases
        if normalized(case["predictions"]["paddle_detector_raw"]["text"])
        and (
            normalized(case["predictions"]["paddle_detector_raw"]["text"])
            == normalized(case["predictions"][best_easy]["text"])
            or normalized(case["predictions"]["paddle_detector_raw"]["text"])
            == normalized(case["predictions"]["vietocr_best_crop"]["text"])
        )
    ]
    paddle_verified_exact = sum(
        normalized(case["predictions"]["paddle_detector_raw"]["text"])
        == normalized(case["groundTruth"])
        for case in paddle_verified
    )
    manifest_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            [
                {
                    "caseId": case["caseId"],
                    "groundTruth": unicodedata.normalize(
                        "NFC", case["groundTruth"]
                    ),
                    "crops": case["crops"],
                }
                for case in cases
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    payload = {
        "schemaVersion": "14.0.0-private",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "containsRealPII": True,
        "alignmentStatus": "PROVISIONAL_LINE_ALIGNMENT",
        "alignmentRule": "page-reviewed GT and crop counts must match; map by index",
        "documentCount": len(sessions),
        "lineCount": len(cases),
        "datasetContentDigest": manifest_digest,
        "profiles": aggregate_results,
        "selection": {
            "bestEasyProfile": best_easy,
            "bestCropProfile": best_crop,
            "easyVietAgreementCount": len(easy_viet_agreed),
            "easyVietAgreementRate": round(len(easy_viet_agreed) / len(cases), 6),
            "agreementPrecision": round(
                easy_viet_exact / max(1, len(easy_viet_agreed)), 6
            ),
            "recommendedPrimary": "paddle_detector_raw",
            "paddleVerifiedCount": len(paddle_verified),
            "paddleVerifiedRate": round(len(paddle_verified) / len(cases), 6),
            "paddleVerifiedPrecision": round(
                paddle_verified_exact / max(1, len(paddle_verified)), 6
            ),
            "promotionDecision": "NOT_PROMOTED",
        },
        "cases": cases,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    detailed_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    best_metrics = aggregate_results[best_easy]
    report = f"""# Phase 14 — OCR hardening trên scan thật

- Trạng thái nhãn: `PROVISIONAL_LINE_ALIGNMENT`
- Tài liệu đủ điều kiện căn chỉnh theo chỉ số: {len(sessions)}
- Dòng crop có Ground Truth provisional: {len(cases)}
- Dataset digest: `{manifest_digest}`
- EasyOCR profile tốt nhất: `{best_easy}`
- Crop profile tốt nhất: `{best_crop}`

| Hệ thống | Exact Match | CER | WER | DER | p95 |
|---|---:|---:|---:|---:|---:|
| Paddle detector raw | {aggregate_results['paddle_detector_raw']['exactMatchRate']:.2%} | {aggregate_results['paddle_detector_raw']['cer']:.2%} | {aggregate_results['paddle_detector_raw']['wer']:.2%} | {aggregate_results['paddle_detector_raw']['diacriticErrorRate']:.2%} | n/a |
| EasyOCR best | {best_metrics['exactMatchRate']:.2%} | {best_metrics['cer']:.2%} | {best_metrics['wer']:.2%} | {best_metrics['diacriticErrorRate']:.2%} | {best_metrics['p95DurationMs']:.1f} ms |
| VietOCR best crop | {aggregate_results['vietocr_best_crop']['exactMatchRate']:.2%} | {aggregate_results['vietocr_best_crop']['cer']:.2%} | {aggregate_results['vietocr_best_crop']['wer']:.2%} | {aggregate_results['vietocr_best_crop']['diacriticErrorRate']:.2%} | {aggregate_results['vietocr_best_crop']['p95DurationMs']:.1f} ms |

EasyOCR/VietOCR đồng thuận {len(easy_viet_agreed)}/{len(cases)} dòng; precision
của nhóm đồng thuận là
{easy_viet_exact / max(1, len(easy_viet_agreed)):.2%}.

Paddle được ít nhất một verifier xác nhận trên {len(paddle_verified)}/{len(cases)}
dòng; precision provisional là
{paddle_verified_exact / max(1, len(paddle_verified)):.2%}. Phase 14 giữ Paddle
làm primary và chỉ dùng EasyOCR/VietOCR làm verifier.

## Quyết định

`NOT_PROMOTED`. Bốn tài liệu đã được review ở cấp trang nhưng ánh xạ crop vẫn là
provisional. Cần người dùng xác nhận Ground Truth trực tiếp trên từng crop trước
khi dùng metric này để thay recognizer production.
"""
    report_path.write_text(report, encoding="utf-8")
    print(
        json.dumps(
            {
                "documentCount": len(sessions),
                "lineCount": len(cases),
                "datasetContentDigest": manifest_digest,
                "bestEasyProfile": best_easy,
                "bestEasyMetrics": best_metrics,
                "vietocrMetrics": aggregate_results["vietocr_best_crop"],
                "agreementCount": len(easy_viet_agreed),
                "agreementPrecision": round(
                    easy_viet_exact / max(1, len(easy_viet_agreed)), 6
                ),
                "recommendedPrimary": "paddle_detector_raw",
                "paddleVerifiedCount": len(paddle_verified),
                "paddleVerifiedPrecision": round(
                    paddle_verified_exact / max(1, len(paddle_verified)), 6
                ),
                "promotionDecision": "NOT_PROMOTED",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
