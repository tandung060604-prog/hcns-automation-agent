#!/usr/bin/env python3
"""Run EasyOCR and both locked VietOCR profiles for Phase 11.5 crops.

This worker runs in the private EasyOCR environment because PaddleOCR and the
secondary recognizers are intentionally installed in separate environments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import cv2
import easyocr
from PIL import Image
from vietocr.tool.config import Cfg
from vietocr.tool.predictor import Predictor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_confidence(value: Any) -> float:
    try:
        if hasattr(value, "item"):
            value = value.item()
        value = float(value)
        if not math.isfinite(value):
            return 0.0
        return round(max(0.0, min(1.0, value)), 6)
    except (TypeError, ValueError):
        return 0.0


def predictor(config_name: str, weight_path: Path) -> Predictor:
    config = Cfg.load_config_from_name(config_name)
    config["device"] = "cpu"
    config["cnn"]["pretrained"] = False
    config["weights"] = str(weight_path)
    config["predictor"]["beamsearch"] = False
    return Predictor(config)


def ordered_easy_lines(result: list[Any]) -> list[dict[str, Any]]:
    lines = []
    for box, text, score in result:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        lines.append(
            {
                "text": str(text),
                "confidence": safe_confidence(score),
                "box": [[round(float(point[0]), 3), round(float(point[1]), 3)] for point in box],
                "bounds": [min(xs), min(ys), max(xs), max(ys)],
            }
        )
    lines.sort(key=lambda line: (line["bounds"][1], line["bounds"][0]))
    return lines


def line_crops(image: Any, lines: list[dict[str, Any]]) -> list[Image.Image]:
    output: list[Image.Image] = []
    height, width = image.shape[:2]
    for line in lines:
        x0, y0, x1, y1 = line["bounds"]
        pad_x = max(5, int((x1 - x0) * 0.04))
        pad_y = max(4, int((y1 - y0) * 0.12))
        left = max(0, int(x0) - pad_x)
        top = max(0, int(y0) - pad_y)
        right = min(width, int(x1) + pad_x)
        bottom = min(height, int(y1) + pad_y)
        crop = image[top:bottom, left:right]
        if crop.size:
            output.append(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
    if not output:
        output.append(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)))
    return output


def main() -> int:
    args = parse_args()
    job = json.loads(args.job.read_text(encoding="utf-8"))
    job_digest = sha256(args.job)
    policy_digest = sha256(args.policy)
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    runtime_profile = policy.get("recognitionRuntime", {})
    locked = {
        model["profile"]: model["sha256"]
        for model in policy.get("modelLocks", policy.get("models", []))
        if model.get("sha256")
    }
    paths = {
        "vietocr_vgg_seq2seq": (args.runtime_root / "vietocr_models" / "vgg_seq2seq.pth"),
        "vietocr_vgg_transformer": (args.runtime_root / "vietocr_models" / "vgg_transformer.pth"),
    }
    for profile, path in paths.items():
        if not path.is_file() or sha256(path) != locked.get(profile):
            raise RuntimeError(f"Locked model mismatch: {profile}")
    easy_paths = {
        "easyocr_detector": (args.runtime_root / "easyocr_models" / "craft_mlt_25k.pth"),
        "easyocr_vi": args.runtime_root / "easyocr_models" / "latin_g2.pth",
    }
    for profile, path in easy_paths.items():
        if not path.is_file() or sha256(path) != locked.get(profile):
            raise RuntimeError(f"Locked model mismatch: {profile}")

    reader = easyocr.Reader(
        ["vi"],
        gpu=False,
        model_storage_directory=str(args.runtime_root / "easyocr_models"),
        download_enabled=False,
        verbose=False,
    )
    predictors = {
        "vietocr_vgg_seq2seq": predictor("vgg_seq2seq", paths["vietocr_vgg_seq2seq"]),
        "vietocr_vgg_transformer": predictor("vgg_transformer", paths["vietocr_vgg_transformer"]),
    }
    partial_path = args.output.with_suffix(".partial.json")
    results: dict[str, Any] = {}
    if partial_path.is_file():
        partial = json.loads(partial_path.read_text(encoding="utf-8"))
        if (
            partial.get("jobSha256") == job_digest
            and partial.get("policySha256") == policy_digest
        ):
            results = partial.get("results", {})
    for index, item in enumerate(job["items"], start=1):
        if str(item["caseId"]) in results:
            continue
        image = cv2.imread(str(item["cropPath"]), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Cannot read crop: {item['cropPath']}")
        started = time.perf_counter()
        easy_raw = reader.readtext(
            image,
            detail=1,
            paragraph=False,
            decoder=str(runtime_profile.get("easyocrDecoder", "beamsearch")),
            batch_size=int(runtime_profile.get("easyocrBatchSize", 1)),
            rotation_info=runtime_profile.get("easyocrRotationInfo"),
        )
        easy_duration = round((time.perf_counter() - started) * 1000, 3)
        easy_lines = ordered_easy_lines(easy_raw)
        predictions: dict[str, Any] = {
            "easyocr_vi": {
                "value": " ".join(line["text"] for line in easy_lines),
                "confidence": (
                    round(
                        sum(line["confidence"] for line in easy_lines) / len(easy_lines),
                        6,
                    )
                    if easy_lines
                    else 0.0
                ),
                "durationMs": easy_duration,
                "lines": [
                    {key: value for key, value in line.items() if key != "bounds"}
                    for line in easy_lines
                ],
            }
        }
        crops = line_crops(image, easy_lines)
        for profile, model in predictors.items():
            model_started = time.perf_counter()
            values: list[str] = []
            probabilities: list[float] = []
            for crop in crops:
                text, probability = model.predict(crop, return_prob=True)
                values.append(str(text))
                probabilities.append(safe_confidence(probability))
            predictions[profile] = {
                "value": " ".join(value for value in values if value),
                "confidence": (
                    round(sum(probabilities) / len(probabilities), 6) if probabilities else 0.0
                ),
                "durationMs": round(
                    (time.perf_counter() - model_started) * 1000,
                    3,
                ),
                "lineCount": len(crops),
            }
        results[str(item["caseId"])] = predictions
        print(
            json.dumps({"progress": index, "total": len(job["items"])}),
            flush=True,
        )
        if index % 8 == 0:
            partial_path.write_text(
                json.dumps(
                    {
                        "status": "RUNNING",
                        "jobSha256": job_digest,
                        "policySha256": policy_digest,
                        "results": results,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "schemaVersion": (
                    f"phase{str(policy.get('phaseVersion', '11.5.0')).removesuffix('.0')}"
                    "-secondary/1.0.0"
                ),
                "status": "COMPLETE",
                "jobSha256": job_digest,
                "policySha256": policy_digest,
                "containsRealPII": True,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if partial_path.is_file():
        partial_path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
