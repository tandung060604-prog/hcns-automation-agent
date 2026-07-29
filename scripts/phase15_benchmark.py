#!/usr/bin/env python3
"""Run the Phase 15 five-family synthetic HR document benchmark.

The pipeline is deliberately split across runtimes:

1. ``prepare`` renders image/PDF pages into a private, resumable work area.
2. ``paddle`` uses PaddleOCR only for line geometry and audit evidence.
3. ``vietocr`` uses Seq2Seq as primary and Transformer as verifier.
4. ``evaluate`` runs unified ingestion/classification/extraction and writes
   aggregate metrics without raw OCR or Ground Truth values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
_API = _ROOT / "apps" / "ocr_lab" / "api"
for _path in (_SRC, _API):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from phase15_idp import (  # noqa: E402
    IDP_PARSER_VERSION,
    build_phase15_business_json,
    classify_phase15_document,
    extract_phase15_document,
)

from hcns_agent.application.ocr_metrics import (  # noqa: E402
    METRIC_SPEC_VERSION,
    evaluate_text_pairs,
    normalize_for_evaluation,
)
from hcns_agent.application.phase14_7_protocol import (  # noqa: E402
    bbox_balanced_bounds,
)

SCHEMA_VERSION = "phase15-five-family-benchmark/1.0.0"
PREDICTION_ROOT_NAME = "phase15_multi_format_private"
POLICY_CONFIG = _ROOT / "config" / "phase14_8_recognition_policy.json"
PRIVATE_RUNTIME = (
    Path(value) if (value := os.environ.get("HCNS_PRIVATE_RUNTIME")) else None
)
PADDLE_MODEL_ROOT = (
    Path(value) if (value := os.environ.get("PADDLE_MODEL_ROOT")) else None
)
SYNTHETIC_CATEGORY_PREFIXES = ("02_", "03_", "04_", "05_", "06_")

EXPECTED_TYPE_ALIASES = {
    "CV_VIETNAMESE": "CV",
    "DEGREE_OR_CERTIFICATE": "DEGREE_CERTIFICATE",
}

EXPECTED_FAMILY_BY_CATEGORY = {
    "02_CV_TIENG_VIET": "CV",
    "03_DON_NGHI_PHEP_BIEU_MAU_HANH_CHINH": "ADMINISTRATIVE_REQUEST",
    "04_HOP_DONG_QUYET_DINH_NHAN_SU": "CONTRACT_DECISION",
    "05_BANG_CAP_CHUNG_CHI": "DEGREE_CERTIFICATE",
    "06_PHIEU_NHAN_VIEN_BANG_BIEU_SCAN": "EMPLOYEE_FORM_TABLE",
}

GROUND_TRUTH_PATHS: dict[str, dict[str, tuple[str, ...]]] = {
    "CV": {
        "fullName": ("name",),
        "headline": ("headline",),
        "email": ("contact.Email", "contact.email"),
        "phoneNumber": (
            "contact.Điện thoại",
            "contact.Số điện thoại",
            "contact.phone",
        ),
        "address": ("contact.Địa chỉ", "contact.address"),
    },
    "ADMINISTRATIVE_REQUEST": {
        "documentTitle": ("title",),
        "requestNumber": ("number",),
        "employeeName": ("name",),
        "employeeId": ("employee_id",),
        "department": ("department",),
        "jobTitle": ("position",),
        "reason": ("reason", "purpose"),
        "startDate": ("from", "date", "start"),
        "endDate": ("to_date", "end"),
    },
    "CONTRACT_DECISION": {
        "documentNumber": ("number",),
        "employeeName": ("employee", "name"),
        "employeeId": ("employee_id",),
        "jobTitle": ("position",),
        "action": ("subject", "type"),
        "salary": ("salary",),
        "startDate": ("start_date",),
        "endDate": ("end_date",),
        "effectiveDate": ("effective_date",),
    },
    "DEGREE_CERTIFICATE": {
        "recipientName": ("recipient",),
        "credentialType": ("credential_type",),
        "credentialId": ("credential_id",),
        "issuingOrganization": ("issuer", "issuer_sub"),
        "fieldOfStudy": ("field", "program"),
        "degreeLevel": ("degree_level",),
        "classification": ("classification",),
        "issueDate": ("issue_date",),
    },
    "EMPLOYEE_FORM_TABLE": {
        "formNumber": ("form_no",),
        "employeeName": ("name",),
        "employeeId": ("employee_id",),
        "dateOfBirth": ("dob",),
        "gender": ("gender",),
        "department": ("department",),
        "jobTitle": ("position",),
        "email": ("email",),
        "phoneNumber": ("phone",),
        "address": ("contact_address", "permanent_address"),
        "organization": ("organization",),
        "joinDate": ("join_date",),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--policy-config", type=Path, default=POLICY_CONFIG)
    parser.add_argument(
        "--private-runtime",
        type=Path,
        default=PRIVATE_RUNTIME,
        help="Private runtime root or HCNS_PRIVATE_RUNTIME",
    )
    parser.add_argument(
        "--paddle-model-root",
        type=Path,
        default=PADDLE_MODEL_ROOT,
        help="Local Paddle model root or PADDLE_MODEL_ROOT",
    )
    parser.add_argument("--overwrite", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    subparsers.add_parser("paddle")
    subparsers.add_parser("vietocr")
    subparsers.add_parser("evaluate")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def work_root(args: argparse.Namespace) -> Path:
    return (
        args.work_root
        if args.work_root
        else args.dataset_root / "predictions" / PREDICTION_ROOT_NAME
    ).resolve()


def policy_config(args: argparse.Namespace) -> dict[str, Any]:
    config = load_json(args.policy_config)
    policy = config.get("policy", {})
    expected = {
        "primaryProfile": "vietocr_vgg_seq2seq",
        "verifierProfile": "vietocr_vgg_transformer",
        "detectorEvidenceProfile": "paddle_detector_raw",
        "autoReplaceSelectedText": False,
    }
    for key, value in expected.items():
        if policy.get(key) != value:
            raise ValueError(f"Phase 15 requires locked Phase 14.8 policy {key}={value!r}")
    if config.get("status") != "SHADOW_REVIEW_ONLY":
        raise ValueError("Phase 14.8 policy must remain SHADOW_REVIEW_ONLY")
    return config


def synthetic_rows(dataset_root: Path) -> list[dict[str, Any]]:
    manifest = load_json(dataset_root / "manifest.json")
    if not isinstance(manifest, list):
        raise ValueError("Dataset manifest must be a list")
    rows = [
        row
        for row in manifest
        if str(row.get("category", "")).startswith(SYNTHETIC_CATEGORY_PREFIXES)
        and row.get("annotation_file")
    ]
    if len(rows) != 25:
        raise ValueError(f"Expected 25 synthetic HR documents, found {len(rows)}")
    for row in rows:
        source = dataset_root / str(row["file"])
        annotation = dataset_root / str(row["annotation_file"])
        if not source.is_file() or not annotation.is_file():
            raise FileNotFoundError("Synthetic source or annotation is missing")
    return sorted(rows, key=lambda row: str(row["id"]))


def render_pages(source: Path, destination: Path) -> list[Path]:
    import pypdfium2 as pdfium
    from PIL import Image, ImageOps

    destination.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".pdf":
        document = pdfium.PdfDocument(source)
        try:
            paths: list[Path] = []
            for page_index in range(len(document)):
                page = document[page_index]
                try:
                    image = page.render(scale=300 / 72).to_pil().convert("RGB")
                finally:
                    page.close()
                path = destination / f"page_{page_index + 1:03d}.png"
                image.save(path, "PNG", optimize=True)
                paths.append(path)
            return paths
        finally:
            document.close()

    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    path = destination / "page_001.png"
    image.save(path, "PNG", optimize=True)
    return [path]


def run_prepare(args: argparse.Namespace) -> int:
    dataset_root = args.dataset_root.resolve()
    output_root = work_root(args)
    manifest_path = output_root / "prepared_manifest_private.json"
    if manifest_path.exists() and not args.overwrite:
        raise FileExistsError("Prepared Phase 15 manifest exists; pass --overwrite")
    policy = policy_config(args)
    rows = synthetic_rows(dataset_root)
    prepared: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index, row in enumerate(rows, start=1):
        source = dataset_root / str(row["file"])
        annotation = dataset_root / str(row["annotation_file"])
        pages = render_pages(source, output_root / "pages" / str(row["id"]))
        prepared.append(
            {
                "documentId": row["id"],
                "category": row["category"],
                "sourcePath": source.relative_to(dataset_root).as_posix(),
                "sourceSha256": sha256_file(source),
                "sourceFormat": row["format"],
                "annotationPath": annotation.relative_to(dataset_root).as_posix(),
                "annotationSha256": sha256_file(annotation),
                "pagePaths": [
                    path.relative_to(output_root).as_posix() for path in pages
                ],
                "pageSha256": [sha256_file(path) for path in pages],
            }
        )
        print(f"Prepare progress {index}/{len(rows)} (content hidden)")
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "stage": "PREPARED",
        "createdAt": utc_now(),
        "containsRealPII": False,
        "datasetKind": "SYNTHETIC_REGRESSION",
        "documentCount": len(prepared),
        "policyDigest": policy["policy"]["policyDigest"],
        "documents": prepared,
        "durationMs": round((time.perf_counter() - started) * 1000, 3),
    }
    atomic_json(manifest_path, payload)
    print(f"Prepare complete: documents={len(prepared)}")
    return 0


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


def validate_file_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"{label} no longer matches its locked SHA-256")


def run_paddle(args: argparse.Namespace) -> int:
    from paddleocr import PaddleOCR
    from PIL import Image

    if args.paddle_model_root is None:
        raise ValueError(
            "--paddle-model-root or PADDLE_MODEL_ROOT is required"
        )
    output_root = work_root(args)
    prepared_path = output_root / "prepared_manifest_private.json"
    geometry_path = output_root / "paddle_geometry_private.json"
    if geometry_path.exists() and not args.overwrite:
        raise FileExistsError("Paddle geometry exists; pass --overwrite")
    prepared = load_json(prepared_path)
    policy = policy_config(args)
    detector_dir = args.paddle_model_root / "PP-OCRv4_mobile_det"
    recognizer_dir = args.paddle_model_root / "latin_PP-OCRv3_mobile_rec"
    detector_weight = detector_dir / "inference.pdiparams"
    detector_lock = next(
        model
        for model in policy["models"]
        if model["profile"] == "paddle_detector_raw"
    )
    validate_file_hash(
        detector_weight,
        str(detector_lock["sha256"]),
        "Paddle detector",
    )
    if not (recognizer_dir / "inference.pdiparams").is_file():
        raise FileNotFoundError("Paddle audit recognizer is missing")
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
    documents = []
    total_lines = 0
    started = time.perf_counter()
    for document_index, document in enumerate(prepared["documents"], start=1):
        pages = []
        for page_index, (relative, digest) in enumerate(
            zip(
                document["pagePaths"],
                document["pageSha256"],
                strict=True,
            )
        ):
            page_path = output_root / relative
            validate_file_hash(page_path, digest, "Rendered page")
            with Image.open(page_path) as opened:
                image = opened.convert("RGB")
            page_started = time.perf_counter()
            results = list(
                ocr.predict(
                    str(page_path),
                    text_det_limit_side_len=2000,
                    text_det_limit_type="max",
                    text_det_thresh=0.25,
                    text_det_box_thresh=0.45,
                    text_det_unclip_ratio=1.6,
                    text_rec_score_thresh=0.0,
                )
            )
            page_duration = (time.perf_counter() - page_started) * 1000
            if len(results) != 1:
                raise ValueError("One rendered page must produce one Paddle page")
            payload = result_payload(results[0])
            texts = list(payload.get("rec_texts") or [])
            scores = list(payload.get("rec_scores") or [])
            polygons = list(payload.get("rec_polys") or [])
            lines = []
            crop_dir = (
                output_root
                / "crops"
                / str(document["documentId"])
                / f"page_{page_index + 1:03d}"
            )
            crop_dir.mkdir(parents=True, exist_ok=True)
            for line_index, polygon in enumerate(polygons):
                box = [
                    [round(float(point[0]), 3), round(float(point[1]), 3)]
                    for point in polygon
                ]
                left, top, right, bottom = bbox_balanced_bounds(
                    box,
                    image_width=image.width,
                    image_height=image.height,
                )
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
                case_source = json.dumps(
                    [
                        document["documentId"],
                        page_index,
                        line_index,
                        box,
                    ],
                    separators=(",", ":"),
                ).encode("utf-8")
                case_id = hashlib.sha256(case_source).hexdigest()[:24]
                crop_path = crop_dir / f"{case_id}.png"
                crop.save(crop_path, "PNG", optimize=True)
                lines.append(
                    {
                        "caseId": case_id,
                        "lineIndex": line_index,
                        "box": box,
                        "cropPath": crop_path.relative_to(output_root).as_posix(),
                        "cropSha256": sha256_file(crop_path),
                        "paddleAuditText": (
                            str(texts[line_index])
                            if line_index < len(texts)
                            else ""
                        ),
                        "paddleAuditConfidence": (
                            float(scores[line_index])
                            if line_index < len(scores)
                            else 0.0
                        ),
                    }
                )
            total_lines += len(lines)
            pages.append(
                {
                    "pageIndex": page_index,
                    "pagePath": relative,
                    "pageDurationMs": round(page_duration, 3),
                    "lines": lines,
                }
            )
        documents.append(
            {
                "documentId": document["documentId"],
                "pages": pages,
            }
        )
        print(
            f"Paddle progress {document_index}/{prepared['documentCount']} "
            "(text hidden)"
        )
    atomic_json(
        geometry_path,
        {
            "schemaVersion": SCHEMA_VERSION,
            "stage": "PADDLE_GEOMETRY_READY",
            "createdAt": utc_now(),
            "containsRealPII": bool(prepared.get("containsRealPII")),
            "datasetKind": prepared.get(
                "datasetKind",
                "SYNTHETIC_REGRESSION",
            ),
            "documentCount": len(documents),
            "lineCount": total_lines,
            "policyDigest": policy["policy"]["policyDigest"],
            "paddleSelectionEligible": False,
            "documents": documents,
            "durationMs": round((time.perf_counter() - started) * 1000, 3),
        },
    )
    print(f"Paddle complete: documents={len(documents)}, lines={total_lines}")
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

    if args.private_runtime is None:
        raise ValueError("--private-runtime or HCNS_PRIVATE_RUNTIME is required")
    output_root = work_root(args)
    geometry = load_json(output_root / "paddle_geometry_private.json")
    prediction_path = output_root / "phase15_recognition_private.json"
    if prediction_path.exists() and not args.overwrite:
        raise FileExistsError("Phase 15 recognition exists; pass --overwrite")
    config = policy_config(args)
    model_locks = {model["profile"]: model for model in config["models"]}
    model_paths = {
        "vietocr_vgg_seq2seq": (
            args.private_runtime / "vietocr_models" / "vgg_seq2seq.pth"
        ),
        "vietocr_vgg_transformer": (
            args.private_runtime / "vietocr_models" / "vgg_transformer.pth"
        ),
    }
    for profile, path in model_paths.items():
        validate_file_hash(path, model_locks[profile]["sha256"], profile)
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
    documents = []
    verified_count = 0
    review_count = 0
    durations: dict[str, list[float]] = defaultdict(list)
    started = time.perf_counter()
    processed_lines = 0
    for document in geometry["documents"]:
        pages = []
        for page in document["pages"]:
            texts = []
            scores = []
            boxes = []
            line_verification = []
            for line in page["lines"]:
                crop_path = output_root / str(line["cropPath"])
                validate_file_hash(
                    crop_path,
                    str(line["cropSha256"]),
                    "Phase 15 line crop",
                )
                predictions = {}
                with Image.open(crop_path) as opened:
                    image = opened.convert("RGB")
                    for profile, predictor in predictors.items():
                        line_started = time.perf_counter()
                        text, probability = predictor.predict(
                            image,
                            return_prob=True,
                        )
                        duration_ms = (
                            time.perf_counter() - line_started
                        ) * 1000
                        durations[profile].append(duration_ms)
                        predictions[profile] = {
                            "text": str(text),
                            "confidence": safe_confidence(probability),
                            "durationMs": round(duration_ms, 3),
                        }
                primary = predictions["vietocr_vgg_seq2seq"]
                verifier = predictions["vietocr_vgg_transformer"]
                exact_agreement = (
                    bool(normalize_for_evaluation(primary["text"]))
                    and normalize_for_evaluation(primary["text"])
                    == normalize_for_evaluation(verifier["text"])
                )
                status = "verified" if exact_agreement else "needs_review"
                verified_count += int(exact_agreement)
                review_count += int(not exact_agreement)
                texts.append(primary["text"])
                scores.append(primary["confidence"])
                boxes.append(line["box"])
                line_verification.append(
                    {
                        "caseId": line["caseId"],
                        "lineIndex": line["lineIndex"],
                        "status": status,
                        "primary": primary,
                        "verifier": verifier,
                        "detectorEvidence": {
                            "profile": "paddle_detector_raw",
                            "text": line["paddleAuditText"],
                            "confidence": line["paddleAuditConfidence"],
                            "selectionEligible": False,
                        },
                        "selectedProfile": "vietocr_vgg_seq2seq",
                        "autoReplacementApplied": False,
                        "rule": (
                            "strict_primary_verifier_agreement"
                            if exact_agreement
                            else "preserve_primary_and_require_review"
                        ),
                    }
                )
                processed_lines += 1
                if processed_lines % 100 == 0:
                    print(
                        f"VietOCR progress {processed_lines}/{geometry['lineCount']} "
                        "(text hidden)"
                    )
            pages.append(
                {
                    "pageIndex": page["pageIndex"],
                    "recognizedTexts": texts,
                    "recognitionScores": scores,
                    "recognizedBoxes": boxes,
                    "lineVerification": line_verification,
                }
            )
        documents.append(
            {
                "documentId": document["documentId"],
                "pages": pages,
            }
        )
    atomic_json(
        prediction_path,
        {
            "schemaVersion": SCHEMA_VERSION,
            "stage": "PHASE14_8_RECOGNITION_READY",
            "createdAt": utc_now(),
            "containsRealPII": bool(geometry.get("containsRealPII")),
            "datasetKind": geometry.get(
                "datasetKind",
                "SYNTHETIC_REGRESSION",
            ),
            "documentCount": len(documents),
            "lineCount": processed_lines,
            "policy": config["policy"],
            "models": {
                profile: {
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for profile, path in model_paths.items()
            },
            "summary": {
                "verifiedLineCount": verified_count,
                "needsReviewLineCount": review_count,
                "verifiedRate": round(
                    verified_count / max(1, processed_lines),
                    6,
                ),
            },
            "runtime": {
                profile: {
                    "lineCount": len(values),
                    "meanDurationMs": round(
                        sum(values) / max(1, len(values)),
                        3,
                    ),
                }
                for profile, values in durations.items()
            },
            "documents": documents,
            "durationMs": round((time.perf_counter() - started) * 1000, 3),
        },
    )
    print(
        f"VietOCR complete: documents={len(documents)}, "
        f"lines={processed_lines}, needsReview={review_count}"
    )
    return 0


def nested_value(payload: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def flatten_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return "\n".join(flatten_value(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(flatten_value(item) for item in value)
    return str(value)


def expected_field(
    fields: dict[str, Any],
    paths: tuple[str, ...],
) -> tuple[bool, str]:
    for path in paths:
        present, value = nested_value(fields, path)
        if present:
            return True, flatten_value(value)
    return False, ""


def predicted_field(
    extraction: dict[str, Any],
    field_name: str,
) -> str:
    field = extraction.get("fields", {}).get(field_name, {})
    value = field.get("normalizedValue")
    if value is None:
        value = field.get("value")
    return flatten_value(value)


def table_counts(
    expected_rows: Any,
    predicted_tables: list[dict[str, Any]],
) -> dict[str, int]:
    if not isinstance(expected_rows, list):
        return {
            "documentCount": 0,
            "expectedRowCount": 0,
            "exactRowCount": 0,
            "expectedCellCount": 0,
            "exactCellCount": 0,
        }
    predicted_rows = [
        row.get("values") or []
        for table in predicted_tables
        for row in table.get("rows", [])
    ]
    exact_rows = 0
    expected_cells = 0
    exact_cells = 0
    for row_index, expected_row in enumerate(expected_rows):
        expected_values = (
            list(expected_row)
            if isinstance(expected_row, list)
            else list(expected_row.values())
            if isinstance(expected_row, dict)
            else [expected_row]
        )
        predicted_row = (
            predicted_rows[row_index]
            if row_index < len(predicted_rows)
            else []
        )
        if isinstance(predicted_row, dict):
            predicted_values = list(predicted_row.values())
        elif isinstance(predicted_row, list):
            predicted_values = predicted_row
        else:
            predicted_values = [predicted_row]
        normalized_expected = [
            normalize_for_evaluation(flatten_value(value))
            for value in expected_values
        ]
        normalized_prediction = [
            normalize_for_evaluation(flatten_value(value))
            for value in predicted_values
        ]
        exact_rows += int(normalized_expected == normalized_prediction)
        expected_cells += len(normalized_expected)
        exact_cells += sum(
            expected == (
                normalized_prediction[index]
                if index < len(normalized_prediction)
                else ""
            )
            for index, expected in enumerate(normalized_expected)
        )
    return {
        "documentCount": 1,
        "expectedRowCount": len(expected_rows),
        "exactRowCount": exact_rows,
        "expectedCellCount": expected_cells,
        "exactCellCount": exact_cells,
    }


def sum_counts(items: list[dict[str, int]]) -> dict[str, int]:
    keys = (
        "documentCount",
        "expectedRowCount",
        "exactRowCount",
        "expectedCellCount",
        "exactCellCount",
    )
    return {key: sum(item[key] for item in items) for key in keys}


def metric_payload(
    *,
    document_count: int,
    subtype_correct: int,
    family_correct: int,
    field_pairs: list[tuple[str, str]],
    completeness: list[float],
    table_metrics: list[dict[str, int]],
) -> dict[str, Any]:
    text = evaluate_text_pairs(field_pairs)
    tables = sum_counts(table_metrics)
    return {
        "documentCount": document_count,
        "subtypeClassificationAccuracy": round(
            subtype_correct / max(1, document_count),
            6,
        ),
        "familyClassificationAccuracy": round(
            family_correct / max(1, document_count),
            6,
        ),
        "evaluatedFieldCount": text.case_count,
        "fieldExactMatchCount": text.strict_exact_count,
        "fieldExactMatchRate": text.strict_exact_rate,
        "meanDocumentCompleteness": round(
            sum(completeness) / max(1, len(completeness)),
            6,
        ),
        "fieldTextCer": text.character_error_rate,
        "fieldTextDer": text.diacritic_error_rate,
        "tableDocumentCount": tables["documentCount"],
        "expectedTableRowCount": tables["expectedRowCount"],
        "tableRowExactMatchRate": round(
            tables["exactRowCount"] / max(1, tables["expectedRowCount"]),
            6,
        ),
        "expectedTableCellCount": tables["expectedCellCount"],
        "tableCellAccuracy": round(
            tables["exactCellCount"] / max(1, tables["expectedCellCount"]),
            6,
        ),
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    rows = []
    for family, metrics in report["byFamily"].items():
        rows.append(
            "| "
            + " | ".join(
                (
                    family,
                    str(metrics["documentCount"]),
                    f"{metrics['subtypeClassificationAccuracy']:.2%}",
                    f"{metrics['fieldExactMatchRate']:.2%}",
                    f"{metrics['meanDocumentCompleteness']:.2%}",
                    f"{metrics['fieldTextCer']:.2%}",
                    f"{metrics['fieldTextDer']:.2%}",
                    f"{metrics['tableCellAccuracy']:.2%}",
                )
            )
            + " |"
        )
    overall = report["overall"]
    markdown = f"""# Phase 15 — Multi-format HR Document IDP

Dataset: 25 tài liệu synthetic regression. Kết quả này không đủ để promote production.

| Nhóm tài liệu | Số tài liệu | Class. | Field EM | Completeness | CER | DER | Table cell |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Tổng hợp

- Subtype Classification Accuracy: {overall['subtypeClassificationAccuracy']:.2%}
- Family Classification Accuracy: {overall['familyClassificationAccuracy']:.2%}
- Field Exact Match: {overall['fieldExactMatchRate']:.2%}
- Mean Document Completeness: {overall['meanDocumentCompleteness']:.2%}
- Field CER / DER: {overall['fieldTextCer']:.2%} / {overall['fieldTextDer']:.2%}
- Table Cell Accuracy: {overall['tableCellAccuracy']:.2%}

## Diễn giải

- Paddle chỉ cung cấp bounding box và audit evidence; không được chọn text.
- Seq2Seq luôn là primary. Transformer chỉ xác minh; disagreement giữ Seq2Seq và `needs_review`.
- CER/DER được tính trên scalar field có mapping nghiệp vụ, không phải toàn trang.
- Các mảng narrative của CV chưa được đưa vào Exact Match cho tới khi có extractor
  cấu trúc tương ứng; chúng vẫn được phản ánh trong Document Completeness.
- Synthetic chỉ dùng regression. Promotion cần tài liệu thật có quyền sử dụng
  và Ground Truth độc lập.
"""
    path.write_text(markdown, encoding="utf-8")


def run_evaluate(args: argparse.Namespace) -> int:
    from phase12_ingestion import ingest_document

    dataset_root = args.dataset_root.resolve()
    output_root = work_root(args)
    prepared = load_json(output_root / "prepared_manifest_private.json")
    predictions = load_json(output_root / "phase15_recognition_private.json")
    prepared_by_id = {
        str(document["documentId"]): document
        for document in prepared["documents"]
    }
    prediction_by_id = {
        str(document["documentId"]): document
        for document in predictions["documents"]
    }
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "documentCount": 0,
            "subtypeCorrect": 0,
            "familyCorrect": 0,
            "fieldPairs": [],
            "completeness": [],
            "tableMetrics": [],
        }
    )
    private_idp_root = output_root / "idp_results"
    started = time.perf_counter()
    for index, document_id in enumerate(sorted(prepared_by_id), start=1):
        source = prepared_by_id[document_id]
        predicted = prediction_by_id.get(document_id)
        if predicted is None:
            raise ValueError("Recognition output is missing a prepared document")
        source_path = dataset_root / str(source["sourcePath"])
        annotation_path = dataset_root / str(source["annotationPath"])
        validate_file_hash(source_path, source["sourceSha256"], "Source document")
        validate_file_hash(
            annotation_path,
            source["annotationSha256"],
            "Ground Truth annotation",
        )
        annotation = load_json(annotation_path)
        canonical = ingest_document(source_path, predicted["pages"])
        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)
        business = build_phase15_business_json(
            document_id,
            canonical,
            classification,
            extraction,
            contains_real_pii=False,
        )
        atomic_json(
            private_idp_root / f"{document_id}.json",
            {
                "schemaVersion": SCHEMA_VERSION,
                "containsRealPII": False,
                "canonical": canonical,
                "classification": classification,
                "extraction": extraction,
                "business": business,
            },
        )
        expected_type = EXPECTED_TYPE_ALIASES.get(
            str(annotation["document_type"]),
            str(annotation["document_type"]),
        )
        expected_family = EXPECTED_FAMILY_BY_CATEGORY[str(source["category"])]
        group = groups[expected_family]
        group["documentCount"] += 1
        group["subtypeCorrect"] += int(
            classification["documentType"] == expected_type
        )
        group["familyCorrect"] += int(
            classification["documentFamily"] == expected_family
        )
        group["completeness"].append(
            float(extraction["summary"]["documentCompleteness"])
        )
        expected_fields = annotation.get("fields", {})
        for field_name, paths in GROUND_TRUTH_PATHS[expected_family].items():
            present, expected = expected_field(expected_fields, paths)
            if not present:
                continue
            predicted_value = predicted_field(extraction, field_name)
            group["fieldPairs"].append((expected, predicted_value))
        expected_rows = expected_fields.get("rows")
        if expected_rows is None:
            expected_rows = expected_fields.get("items")
        group["tableMetrics"].append(
            table_counts(expected_rows, extraction.get("tables", []))
        )
        print(f"Evaluate progress {index}/{len(prepared_by_id)} (values hidden)")

    by_family = {
        family: metric_payload(
            document_count=values["documentCount"],
            subtype_correct=values["subtypeCorrect"],
            family_correct=values["familyCorrect"],
            field_pairs=values["fieldPairs"],
            completeness=values["completeness"],
            table_metrics=values["tableMetrics"],
        )
        for family, values in sorted(groups.items())
    }
    all_values = {
        "documentCount": sum(value["documentCount"] for value in groups.values()),
        "subtypeCorrect": sum(value["subtypeCorrect"] for value in groups.values()),
        "familyCorrect": sum(value["familyCorrect"] for value in groups.values()),
        "fieldPairs": [
            pair for value in groups.values() for pair in value["fieldPairs"]
        ],
        "completeness": [
            item for value in groups.values() for item in value["completeness"]
        ],
        "tableMetrics": [
            item for value in groups.values() for item in value["tableMetrics"]
        ],
    }
    overall = metric_payload(
        document_count=all_values["documentCount"],
        subtype_correct=all_values["subtypeCorrect"],
        family_correct=all_values["familyCorrect"],
        field_pairs=all_values["fieldPairs"],
        completeness=all_values["completeness"],
        table_metrics=all_values["tableMetrics"],
    )
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "createdAt": utc_now(),
        "containsRealPII": False,
        "datasetKind": "SYNTHETIC_REGRESSION",
        "documentCount": len(prepared_by_id),
        "documentFamilyCount": len(by_family),
        "metricSpecVersion": METRIC_SPEC_VERSION,
        "parserVersion": IDP_PARSER_VERSION,
        "recognitionPolicy": predictions["policy"],
        "metricScope": {
            "classification": "exact subtype and five-family labels",
            "fieldExactMatch": (
                "mapped scalar business fields after NFC + whitespace; "
                "CV narrative arrays are excluded until structured extraction exists"
            ),
            "cerDer": "mapped business-field text, not full-page transcription",
            "tableAccuracy": "position-aligned row and cell exact match",
        },
        "byFamily": by_family,
        "overall": overall,
        "productionPromotionAllowed": False,
        "productionDecision": "SYNTHETIC_REGRESSION_ONLY",
        "durationMs": round((time.perf_counter() - started) * 1000, 3),
    }
    metrics_root = dataset_root / "metrics"
    report_path = metrics_root / "PHASE15_SYNTHETIC_BENCHMARK.json"
    markdown_path = metrics_root / "PHASE15_SYNTHETIC_BENCHMARK.md"
    if report_path.exists() and not args.overwrite:
        raise FileExistsError("Phase 15 report exists; pass --overwrite")
    atomic_json(report_path, report)
    write_markdown(markdown_path, report)
    print(
        f"Evaluation complete: documents={report['documentCount']}, "
        f"families={report['documentFamilyCount']}"
    )
    return 0


def main() -> int:
    args = parse_args()
    commands = {
        "prepare": run_prepare,
        "paddle": run_paddle,
        "vietocr": run_vietocr,
        "evaluate": run_evaluate,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
