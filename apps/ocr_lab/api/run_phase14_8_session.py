#!/usr/bin/env python3
"""Run the locked Phase 14.8 recognizer policy for one local upload session."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = REPOSITORY_ROOT / "config" / "phase14_8_recognition_policy.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--policy-config", type=Path, default=POLICY_PATH)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_strict(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def safe_confidence(value: Any) -> float:
    try:
        if hasattr(value, "item"):
            value = value.item()
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def build_predictor(config_name: str, weight_path: Path) -> Any:
    from vietocr.tool.config import Cfg
    from vietocr.tool.predictor import Predictor

    config = Cfg.load_config_from_name(config_name)
    config["device"] = "cpu"
    config["cnn"]["pretrained"] = False
    config["weights"] = str(weight_path)
    config["predictor"]["beamsearch"] = False
    return Predictor(config)


def validate_policy(
    policy_path: Path,
    runtime_root: Path,
) -> tuple[dict[str, Any], dict[str, Path]]:
    config = load_json(policy_path)
    policy = config.get("policy", {})
    if (
        config.get("status") != "SHADOW_REVIEW_ONLY"
        or policy.get("primaryProfile") != "vietocr_vgg_seq2seq"
        or policy.get("verifierProfile") != "vietocr_vgg_transformer"
        or policy.get("detectorEvidenceProfile") != "paddle_detector_raw"
        or policy.get("autoReplaceSelectedText") is not False
    ):
        raise ValueError("Phase 14.8 policy config is not the locked verifier policy")
    locks = {model["profile"]: model for model in config["models"]}
    paths = {
        "vietocr_vgg_seq2seq": (
            runtime_root / "vietocr_models" / "vgg_seq2seq.pth"
        ),
        "vietocr_vgg_transformer": (
            runtime_root / "vietocr_models" / "vgg_transformer.pth"
        ),
    }
    for profile, path in paths.items():
        lock = locks[profile]
        if (
            not path.is_file()
            or path.stat().st_size != int(lock["bytes"])
            or sha256_file(path) != str(lock["sha256"])
        ):
            raise ValueError(f"Locked model mismatch: {profile}")
    return config, paths


def crop_line(
    image: Image.Image,
    box: list[list[float]],
) -> Image.Image:
    xs = [float(point[0]) for point in box]
    ys = [float(point[1]) for point in box]
    line_height = max(1.0, max(ys) - min(ys))
    pad_x = max(4, round(line_height * 0.18))
    pad_y = max(3, round(line_height * 0.12))
    left = max(0, int(min(xs)) - pad_x)
    right = min(image.width, int(max(xs)) + pad_x)
    top = max(0, int(min(ys)) - pad_y)
    bottom = min(image.height, int(max(ys)) + pad_y)
    if right <= left or bottom <= top:
        raise ValueError("Invalid Paddle detector box")
    crop = image.crop((left, top, right, bottom))
    if crop.height < 64:
        scale = min(5.0, 64 / max(1, crop.height))
        crop = crop.resize(
            (
                max(1, round(crop.width * scale)),
                max(1, round(crop.height * scale)),
            ),
            Image.Resampling.BICUBIC,
        )
    return crop


def line_decision(
    primary_text: str,
    primary_confidence: float,
    verifier_text: str,
) -> dict[str, Any]:
    exact_agreement = (
        bool(normalize_strict(primary_text))
        and normalize_strict(primary_text) == normalize_strict(verifier_text)
    )
    return {
        "status": "verified" if exact_agreement else "needs_review",
        "selectedText": primary_text,
        "selectedConfidence": primary_confidence,
        "exactAgreement": exact_agreement,
        "selectedProfile": "vietocr_vgg_seq2seq",
        "autoReplacementApplied": False,
        "rule": (
            "strict_primary_verifier_agreement"
            if exact_agreement
            else "preserve_primary_and_require_review"
        ),
    }


def process_session(args: argparse.Namespace) -> dict[str, Any]:
    if not SESSION_ID_RE.fullmatch(args.session_id):
        raise ValueError("Invalid session id")
    session_dir = (
        args.data_root / "user_uploads" / "sessions" / args.session_id
    )
    result_path = session_dir / "result.json"
    if not result_path.is_file():
        raise FileNotFoundError("Session result not found")
    output_dir = session_dir / "phase14_8"
    output_path = output_dir / "recognition.json"
    if output_path.exists() and not args.overwrite:
        return load_json(output_path)

    result = load_json(result_path)
    pages = list(result.get("document", {}).get("pages", []))
    if not pages:
        raise ValueError("Session has no Paddle detector pages")
    policy, model_paths = validate_policy(
        args.policy_config,
        args.data_root / "runtime",
    )
    predictors = {
        "vietocr_vgg_seq2seq": build_predictor(
            "vgg_seq2seq",
            model_paths["vietocr_vgg_seq2seq"],
        ),
        "vietocr_vgg_transformer": build_predictor(
            "vgg_transformer",
            model_paths["vietocr_vgg_transformer"],
        ),
    }
    output_pages = []
    verified_count = 0
    review_count = 0
    line_count = 0
    started = time.perf_counter()
    for page_index, page in enumerate(pages):
        page_path = session_dir / "pages" / f"page_{page_index:03d}.png"
        if not page_path.is_file():
            raise FileNotFoundError("Rendered session page is missing")
        with Image.open(page_path) as opened:
            image = opened.convert("RGB")
        texts = list(page.get("recognizedTexts") or [])
        scores = list(page.get("recognitionScores") or [])
        boxes = list(page.get("recognizedBoxes") or [])
        selected_texts = []
        selected_scores = []
        selected_boxes = []
        verification = []
        crop_dir = output_dir / "crops" / f"page_{page_index:03d}"
        crop_dir.mkdir(parents=True, exist_ok=True)
        for line_index, box in enumerate(boxes):
            normalized_box = [
                [round(float(point[0]), 3), round(float(point[1]), 3)]
                for point in box
            ]
            crop = crop_line(image, normalized_box)
            crop_path = crop_dir / f"line_{line_index:04d}.png"
            crop.save(crop_path, "PNG", optimize=True)
            predictions = {}
            for profile, predictor in predictors.items():
                line_started = time.perf_counter()
                text, probability = predictor.predict(
                    crop,
                    return_prob=True,
                )
                predictions[profile] = {
                    "text": str(text),
                    "confidence": safe_confidence(probability),
                    "durationMs": round(
                        (time.perf_counter() - line_started) * 1000,
                        3,
                    ),
                }
            primary = predictions["vietocr_vgg_seq2seq"]
            verifier = predictions["vietocr_vgg_transformer"]
            decision = line_decision(
                primary["text"],
                primary["confidence"],
                verifier["text"],
            )
            verified_count += int(decision["status"] == "verified")
            review_count += int(decision["status"] == "needs_review")
            line_count += 1
            selected_texts.append(decision["selectedText"])
            selected_scores.append(decision["selectedConfidence"])
            selected_boxes.append(normalized_box)
            verification.append(
                {
                    "lineIndex": line_index,
                    "box": normalized_box,
                    "primary": primary,
                    "verifier": verifier,
                    "detectorEvidence": {
                        "profile": "paddle_detector_raw",
                        "text": (
                            str(texts[line_index])
                            if line_index < len(texts)
                            else ""
                        ),
                        "confidence": (
                            safe_confidence(scores[line_index])
                            if line_index < len(scores)
                            else 0.0
                        ),
                        "selectionEligible": False,
                    },
                    "decision": decision,
                }
            )
        output_pages.append(
            {
                "pageIndex": page_index,
                "recognizedTexts": selected_texts,
                "recognitionScores": selected_scores,
                "recognizedBoxes": selected_boxes,
                "lineVerification": verification,
            }
        )
    payload = {
        "schemaVersion": "phase14.8-session-recognition/1.0.0",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sessionId": args.session_id,
        "containsRealPII": True,
        "status": (
            "SHADOW_NEEDS_REVIEW"
            if review_count
            else "SHADOW_ALL_LINES_VERIFIED"
        ),
        "policy": policy["policy"],
        "summary": {
            "pageCount": len(output_pages),
            "lineCount": line_count,
            "verifiedLineCount": verified_count,
            "needsReviewLineCount": review_count,
            "verifiedRate": round(
                verified_count / max(1, line_count),
                6,
            ),
        },
        "pages": output_pages,
        "durationMs": round((time.perf_counter() - started) * 1000, 3),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    args = parse_args()
    payload = process_session(args)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "pageCount": payload["summary"]["pageCount"],
                "lineCount": payload["summary"]["lineCount"],
                "verifiedLineCount": payload["summary"]["verifiedLineCount"],
                "needsReviewLineCount": payload["summary"][
                    "needsReviewLineCount"
                ],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
