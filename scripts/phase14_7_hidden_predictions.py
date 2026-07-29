#!/usr/bin/env python3
"""Build and seal Phase 14.7 hidden predictions without exposing OCR text.

Run the ``paddle`` subcommand with the PaddleOCR environment, then run
``vietocr`` with the local VietOCR environment.  Ground Truth review remains
locked until the second subcommand creates and hashes the private snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hcns_agent.application.phase14_7_protocol import (
    CROP_PROFILE,
    PENDING,
    PREDICTION_PROFILES,
    atomic_write_json,
    bbox_balanced_bounds,
    compute_queue_digest,
    sha256_file,
)

REAL_CORPUS = "REAL_CCCD_HELDOUT"
PADDLE_PROFILE = "paddle_detector_raw"
SEQ2SEQ_PROFILE = "vietocr_vgg_seq2seq"
TRANSFORMER_PROFILE = "vietocr_vgg_transformer"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument(
        "--benchmark-lock",
        type=Path,
        default=Path("config/phase14_6_benchmark_lock.json"),
    )
    parser.add_argument(
        "--private-runtime",
        type=Path,
        default=Path(
            r"C:\Camunda\private-data\paddleocr-hr-baseline\runtime"
        ),
    )
    parser.add_argument(
        "--paddle-model-root",
        type=Path,
        default=Path(r"C:\Users\HP\.paddlex\official_models"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("paddle")
    subparsers.add_parser("vietocr")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_model(
    *,
    profile: str,
    path: Path,
    expected: dict[str, Any],
) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Locked model is missing for {profile}")
    size = path.stat().st_size
    digest = sha256_file(path)
    if size != int(expected["bytes"]) or digest != str(expected["sha256"]):
        raise ValueError(f"Locked model digest mismatch for {profile}")
    return {
        "profile": profile,
        "file": path.name,
        "bytes": size,
        "sha256": digest,
    }


def locked_models(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    lock = load_json(args.benchmark_lock)
    if lock["policy"]["cropProfile"] != CROP_PROFILE:
        raise ValueError("Benchmark lock uses a different crop profile")
    configured = {item["profile"]: item for item in lock["models"]}
    if set(PREDICTION_PROFILES) - set(configured):
        raise ValueError("Benchmark lock is missing a prediction profile")

    paths = {
        PADDLE_PROFILE: (
            args.paddle_model_root
            / "PP-OCRv4_mobile_det"
            / configured[PADDLE_PROFILE]["relativePath"]
        ),
        SEQ2SEQ_PROFILE: (
            args.private_runtime / configured[SEQ2SEQ_PROFILE]["relativePath"]
        ),
        TRANSFORMER_PROFILE: (
            args.private_runtime / configured[TRANSFORMER_PROFILE]["relativePath"]
        ),
    }
    metadata = {
        profile: validate_model(
            profile=profile,
            path=paths[profile],
            expected=configured[profile],
        )
        for profile in PREDICTION_PROFILES
    }
    return lock, {"paths": paths, "metadata": metadata}


def validate_dataset(dataset_root: Path) -> tuple[list[dict[str, Any]], str]:
    complete_lock = dataset_root / "locks" / "benchmark_lock.complete.json"
    manifest_path = dataset_root / "manifest.json"
    if not complete_lock.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Complete benchmark lock or manifest is missing")
    complete = load_json(complete_lock)
    manifest = load_json(manifest_path)
    if not isinstance(manifest, list) or len(manifest) != 33:
        raise ValueError("Expected the complete 33-document manifest")
    if int(complete.get("document_count", complete.get("documentCount", 0))) not in {
        0,
        33,
    }:
        raise ValueError("Complete benchmark lock document count mismatch")

    rows = [row for row in manifest if row.get("corpus") == REAL_CORPUS]
    if len(rows) != 8:
        raise ValueError("Expected exactly 8 private held-out CCCD documents")
    source_ids = {str(row.get("source_document_id", "")) for row in rows}
    source_hashes = {str(row.get("sha256", "")) for row in rows}
    if len(source_ids) != 8 or "" in source_ids:
        raise ValueError("Private CCCD source_document_id values are not independent")
    if len(source_hashes) != 8 or "" in source_hashes:
        raise ValueError("Private CCCD file hashes are not unique")
    for row in rows:
        if row.get("variant_id") != "ORIGINAL":
            raise ValueError("Private CCCD must be an ORIGINAL document")
        path = dataset_root / str(row["file"])
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            raise ValueError("A private CCCD no longer matches the complete lock")
    return sorted(rows, key=lambda row: str(row["id"])), sha256_file(complete_lock)


def result_payload(item: Any) -> dict[str, Any]:
    value = item.json if hasattr(item, "json") else item
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TypeError("Unexpected PaddleOCR result")
    payload = value.get("res", value)
    if not isinstance(payload, dict):
        raise TypeError("Unexpected PaddleOCR result payload")
    return payload


def case_id(document_id: str, line_index: int, box: list[list[float]]) -> str:
    source = json.dumps(
        [document_id, 0, line_index, box],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(source).hexdigest()[:24]


def run_paddle(args: argparse.Namespace) -> int:
    from paddleocr import PaddleOCR
    from PIL import Image, ImageOps

    dataset_root = args.dataset_root.resolve()
    rows, dataset_lock_digest = validate_dataset(dataset_root)
    benchmark_lock, models = locked_models(args)
    phase_root = dataset_root / "ground_truth" / "private_phase14_7"
    paddle_path = (
        dataset_root / "predictions" / "phase14_7_paddle_private.json"
    )
    queue_path = phase_root / "review_queue_private.json"
    if paddle_path.exists() or queue_path.exists():
        raise FileExistsError(
            "Phase 14.7 Paddle/queue artifacts already exist; refusing overwrite"
        )

    detector_dir = args.paddle_model_root / "PP-OCRv4_mobile_det"
    recognizer_dir = args.paddle_model_root / "latin_PP-OCRv3_mobile_rec"
    recognizer_weights = recognizer_dir / "inference.pdiparams"
    if not recognizer_weights.is_file():
        raise FileNotFoundError("Local Paddle Latin recognizer is missing")
    recognizer_metadata = {
        "model": "latin_PP-OCRv3_mobile_rec",
        "file": recognizer_weights.name,
        "bytes": recognizer_weights.stat().st_size,
        "sha256": sha256_file(recognizer_weights),
    }

    ocr = PaddleOCR(
        text_detection_model_name="PP-OCRv4_mobile_det",
        text_detection_model_dir=str(detector_dir),
        text_recognition_model_name="latin_PP-OCRv3_mobile_rec",
        text_recognition_model_dir=str(recognizer_dir),
        device="cpu",
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    output_cases: list[dict[str, Any]] = []
    queue_cases: list[dict[str, Any]] = []
    total_started = time.perf_counter()
    for document_offset, row in enumerate(rows, start=1):
        document_id = str(row["id"])
        source_path = dataset_root / str(row["file"])
        with Image.open(source_path) as opened:
            page = ImageOps.exif_transpose(opened).convert("RGB")
        page_dir = phase_root / "pages" / document_id
        page_dir.mkdir(parents=True, exist_ok=True)
        page_path = page_dir / "page_001.jpg"
        page.save(page_path, "JPEG", quality=95, subsampling=0)

        started = time.perf_counter()
        results = list(
            ocr.predict(
                str(page_path),
                text_det_limit_side_len=1600,
                text_det_limit_type="max",
                text_det_thresh=0.25,
                text_det_box_thresh=0.45,
                text_det_unclip_ratio=1.6,
                text_rec_score_thresh=0.0,
            )
        )
        document_duration_ms = (time.perf_counter() - started) * 1000
        if len(results) != 1:
            raise ValueError("A single-image CCCD must produce one OCR page")
        payload = result_payload(results[0])
        texts = list(payload.get("rec_texts") or [])
        scores = list(payload.get("rec_scores") or [])
        polygons = list(payload.get("rec_polys") or [])
        if not polygons or len(polygons) != len(texts):
            raise ValueError("Paddle detector returned incomplete line geometry")

        crop_dir = phase_root / "crops" / document_id / "page_001"
        crop_dir.mkdir(parents=True, exist_ok=True)
        per_line_duration = document_duration_ms / max(1, len(polygons))
        for line_index, raw_polygon in enumerate(polygons, start=1):
            box = [[float(point[0]), float(point[1])] for point in raw_polygon]
            identifier = case_id(document_id, line_index, box)
            left, top, right, bottom = bbox_balanced_bounds(
                box,
                image_width=page.width,
                image_height=page.height,
            )
            crop = page.crop((left, top, right, bottom))
            if crop.height < 64:
                scale = min(5.0, 64 / max(1, crop.height))
                crop = crop.resize(
                    (
                        max(1, round(crop.width * scale)),
                        max(1, round(crop.height * scale)),
                    ),
                    Image.Resampling.BICUBIC,
                )
            crop_path = crop_dir / f"{identifier}.png"
            crop.save(crop_path, "PNG", optimize=True)
            crop_relative = crop_path.relative_to(dataset_root).as_posix()
            page_relative = page_path.relative_to(dataset_root).as_posix()
            crop_digest = sha256_file(crop_path)
            score = float(scores[line_index - 1]) if line_index <= len(scores) else 0.0
            paddle_case = {
                "caseId": identifier,
                "documentId": document_id,
                "sourceDocumentId": row["source_document_id"],
                "pageIndex": 0,
                "lineIndex": line_index - 1,
                "box": box,
                "cropBounds": [left, top, right, bottom],
                "cropPath": crop_relative,
                "pageRenderPath": page_relative,
                "cropSha256": crop_digest,
                "predictions": {
                    PADDLE_PROFILE: {
                        "text": str(texts[line_index - 1]),
                        "confidence": max(0.0, min(1.0, score)),
                        "durationMs": round(per_line_duration, 3),
                    }
                },
            }
            output_cases.append(paddle_case)
            queue_cases.append(
                {
                    "caseId": identifier,
                    "documentId": document_id,
                    "pageIndex": 0,
                    "lineIndex": line_index - 1,
                    "box": box,
                    "cropPath": crop_relative,
                    "pageRenderPath": page_relative,
                    "cropSha256": crop_digest,
                    "status": PENDING,
                    "confirmedTranscription": "",
                    "reviewer": "",
                    "reviewedAt": "",
                }
            )
        print(
            f"Paddle progress {document_offset}/{len(rows)}: "
            f"{len(polygons)} lines (text hidden)"
        )

    created_at = utc_now()
    dataset_digest = f"sha256:{dataset_lock_digest}"
    paddle_payload = {
        "schemaVersion": "phase14.7-paddle-stage/1.0.0",
        "createdAt": created_at,
        "containsRealPII": True,
        "groundTruthPresent": False,
        "predictionsHiddenDuringReview": True,
        "datasetId": dataset_root.name,
        "datasetDigest": dataset_digest,
        "documentCount": len(rows),
        "lineCount": len(output_cases),
        "cropProfile": {
            "name": CROP_PROFILE,
            "padXRatio": 0.18,
            "padYRatio": 0.12,
            "targetHeight": 64,
            "maximumUpscale": 5.0,
        },
        "models": {
            PADDLE_PROFILE: models["metadata"][PADDLE_PROFILE],
            "paddle_recognizer_raw": recognizer_metadata,
        },
        "benchmarkPolicyDigest": benchmark_lock["policy"]["policyDigest"],
        "cases": output_cases,
        "totalDurationMs": round((time.perf_counter() - total_started) * 1000, 3),
    }
    queue_digest = compute_queue_digest(queue_cases)
    queue_payload = {
        "schemaVersion": "phase14.7-private-review-queue/1.0.0",
        "createdAt": created_at,
        "containsRealPII": True,
        "predictionsVisibleDuringReview": False,
        "groundTruthStatus": "PENDING_HUMAN_CONFIRMATION",
        "datasetId": dataset_root.name,
        "datasetDigest": dataset_digest,
        "documentCount": len(rows),
        "lineCount": len(queue_cases),
        "cropProfile": CROP_PROFILE,
        "queueDigest": queue_digest,
        "cases": queue_cases,
    }
    paddle_payload["queueDigest"] = queue_digest
    atomic_write_json(paddle_path, paddle_payload)
    atomic_write_json(queue_path, queue_payload)
    print(
        f"Paddle stage complete: documents={len(rows)}, lines={len(output_cases)}, "
        "recognized text hidden"
    )
    return 0


def build_predictor(config_name: str, weight_path: Path) -> Any:
    from vietocr.tool.config import Cfg
    from vietocr.tool.predictor import Predictor

    config = Cfg.load_config_from_name(config_name)
    config["device"] = "cpu"
    config["cnn"]["pretrained"] = False
    config["weights"] = str(weight_path)
    config["predictor"]["beamsearch"] = False
    return Predictor(config)


def safe_confidence(value: Any) -> float:
    try:
        if hasattr(value, "item"):
            value = value.item()
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def run_vietocr(args: argparse.Namespace) -> int:
    from PIL import Image

    dataset_root = args.dataset_root.resolve()
    rows, dataset_lock_digest = validate_dataset(dataset_root)
    benchmark_lock, models = locked_models(args)
    phase_root = dataset_root / "ground_truth" / "private_phase14_7"
    paddle_path = (
        dataset_root / "predictions" / "phase14_7_paddle_private.json"
    )
    queue_path = phase_root / "review_queue_private.json"
    private_path = (
        dataset_root
        / "predictions"
        / "phase14_7_hidden_predictions_private.json"
    )
    status_path = (
        dataset_root
        / "predictions"
        / "PHASE14_7_HIDDEN_PREDICTIONS_STATUS.json"
    )
    sha_path = dataset_root / "locks" / "phase14_7_hidden_predictions.sha256"
    if private_path.exists() or status_path.exists() or sha_path.exists():
        raise FileExistsError(
            "Phase 14.7 hidden snapshot already exists; refusing overwrite"
        )
    if not paddle_path.is_file() or not queue_path.is_file():
        raise FileNotFoundError("Run the Paddle stage before VietOCR")
    paddle_payload = load_json(paddle_path)
    queue = load_json(queue_path)
    cases = paddle_payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Paddle stage has no crops")
    if int(paddle_payload.get("documentCount", -1)) != len(rows):
        raise ValueError("Paddle stage document count mismatch")
    if int(paddle_payload.get("lineCount", -1)) != len(cases):
        raise ValueError("Paddle stage line count mismatch")
    if queue.get("queueDigest") != paddle_payload.get("queueDigest"):
        raise ValueError("Paddle stage and review queue differ")
    if paddle_payload.get("datasetDigest") != f"sha256:{dataset_lock_digest}":
        raise ValueError("Paddle stage uses a different dataset lock")

    profile_configs = {
        SEQ2SEQ_PROFILE: "vgg_seq2seq",
        TRANSFORMER_PROFILE: "vgg_transformer",
    }
    predictors = {
        profile: build_predictor(
            config_name,
            models["paths"][profile],
        )
        for profile, config_name in profile_configs.items()
    }
    durations = {profile: [] for profile in profile_configs}
    empty_counts = {profile: 0 for profile in profile_configs}
    output_cases: list[dict[str, Any]] = []
    total_started = time.perf_counter()
    for index, source_case in enumerate(cases, start=1):
        crop_path = dataset_root / str(source_case["cropPath"])
        crop_digest = sha256_file(crop_path)
        if crop_digest != source_case["cropSha256"]:
            raise ValueError("A locked crop digest no longer matches")
        predictions = dict(source_case["predictions"])
        with Image.open(crop_path) as opened:
            image = opened.convert("RGB")
            for profile, predictor in predictors.items():
                started = time.perf_counter()
                text, probability = predictor.predict(image, return_prob=True)
                duration_ms = (time.perf_counter() - started) * 1000
                value = str(text)
                predictions[profile] = {
                    "text": value,
                    "confidence": safe_confidence(probability),
                    "durationMs": round(duration_ms, 3),
                }
                durations[profile].append(duration_ms)
                empty_counts[profile] += int(not value.strip())
        output_case = dict(source_case)
        output_case["predictions"] = predictions
        output_cases.append(output_case)
        if index % 25 == 0 or index == len(cases):
            print(
                f"VietOCR progress {index}/{len(cases)} "
                "(predictions remain hidden)"
            )

    model_metadata = dict(paddle_payload["models"])
    model_metadata.update(
        {
            profile: {
                **models["metadata"][profile],
                "config": profile_configs[profile],
            }
            for profile in profile_configs
        }
    )
    created_at = utc_now()
    private_payload = {
        "schemaVersion": "phase14.7-hidden-predictions/1.0.0",
        "createdAt": created_at,
        "containsRealPII": True,
        "predictionsHiddenDuringReview": True,
        "groundTruthPresent": False,
        "datasetId": paddle_payload["datasetId"],
        "datasetDigest": paddle_payload["datasetDigest"],
        "documentCount": len(rows),
        "lineCount": len(output_cases),
        "queueDigest": queue["queueDigest"],
        "cropProfile": paddle_payload["cropProfile"],
        "metricSpecVersion": benchmark_lock["metricSpecVersion"],
        "benchmarkPolicyDigest": benchmark_lock["policy"]["policyDigest"],
        "models": model_metadata,
        "cases": output_cases,
    }
    private_bytes = (
        json.dumps(private_payload, ensure_ascii=False, indent=2).encode("utf-8")
        + b"\n"
    )
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(private_bytes)
    private_digest = hashlib.sha256(private_bytes).hexdigest()
    status_payload = {
        "schemaVersion": "phase14.7-hidden-predictions-status/1.0.0",
        "createdAt": created_at,
        "containsRealPII": False,
        "status": "BLINDED_PREDICTIONS_READY",
        "predictionsHiddenDuringReview": True,
        "groundTruthPresent": False,
        "datasetDigest": paddle_payload["datasetDigest"],
        "documentCount": len(rows),
        "independentSourceDocumentCount": len(
            {row["source_document_id"] for row in rows}
        ),
        "minimumProductionDocumentCount": int(
            benchmark_lock["heldOutProtocol"]["minimumDocumentCount"]
        ),
        "productionPromotionGate": "INSUFFICIENT_DOCUMENTS",
        "lineCount": len(output_cases),
        "queueDigest": queue["queueDigest"],
        "privateArtifactSha256": private_digest,
        "models": model_metadata,
        "runtime": {
            profile: {
                "lineCount": len(values),
                "emptyPredictionCount": empty_counts[profile],
                "meanDurationMs": round(sum(values) / max(1, len(values)), 3),
            }
            for profile, values in durations.items()
        },
        "totalDurationMs": round((time.perf_counter() - total_started) * 1000, 3),
        "vietocrVersion": importlib.metadata.version("vietocr"),
        "device": "cpu",
        "unlockRule": (
            "Human Ground Truth may start only after this artifact and its "
            "SHA-256 lock exist."
        ),
    }
    atomic_write_json(status_path, status_payload)
    sha_path.write_text(
        f"{private_digest}  predictions/{private_path.name}\n",
        encoding="ascii",
    )
    print(
        f"Hidden snapshot sealed: documents={len(rows)}, "
        f"lines={len(output_cases)}, sha256={private_digest}"
    )
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "paddle":
        return run_paddle(args)
    return run_vietocr(args)


if __name__ == "__main__":
    raise SystemExit(main())
