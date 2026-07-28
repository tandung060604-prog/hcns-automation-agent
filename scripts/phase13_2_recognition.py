"""Build and run a fixed private Vietnamese line-recognition corpus.

Raw crops, Ground Truth and predictions belong in private-data and must never be
committed. The script prints aggregate counts only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import time
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LineCandidate:
    source_path: Path
    source_relative_path: str
    source_sha256: str
    page_index: int
    bbox: tuple[float, float, float, float]
    text: str
    has_extended_vietnamese: bool
    selection_key: str


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare_corpus(
            source_root=args.source_root,
            output_root=args.output_root,
            max_cases=args.max_cases,
            dpi=args.dpi,
            dataset_id=args.dataset_id,
            dataset_version=args.dataset_version,
            overwrite=args.overwrite,
        )
        return 0
    if args.command == "run":
        run_backend(
            backend=args.backend,
            manifest_path=args.manifest,
            output_path=args.output,
            device=args.device,
            batch_size=args.batch_size,
            model_identifier=args.model_identifier,
            model_storage_directory=args.model_storage_directory,
            overwrite=args.overwrite,
        )
        return 0
    if args.command == "select":
        select_recognizer(
            report_paths=args.report,
            baseline_model=args.baseline_model,
            output_path=args.output,
            overwrite=args.overwrite,
        )
        return 0
    if args.command == "summarize":
        build_summary(
            ground_truth_path=args.ground_truth,
            prediction_paths=args.prediction,
            report_paths=args.report,
            selection_path=args.selection,
            output_path=args.output,
            overwrite=args.overwrite,
        )
        return 0
    parser.error("A Phase 13.2 command is required")
    return 2


def prepare_corpus(
    *,
    source_root: Path,
    output_root: Path,
    max_cases: int,
    dpi: int,
    dataset_id: str,
    dataset_version: str,
    overwrite: bool,
) -> None:
    if max_cases < 30:
        raise ValueError("max_cases must be at least 30")
    if dpi < 150:
        raise ValueError("dpi must be at least 150")
    if not source_root.is_dir():
        raise ValueError("source_root must be an existing directory")

    manifest_path = output_root / "corpus_manifest.json"
    ground_truth_path = output_root / "ground_truth.json"
    if (manifest_path.exists() or ground_truth_path.exists()) and not overwrite:
        raise FileExistsError("Corpus already exists; use --overwrite to rebuild deterministically")

    candidates = collect_pdf_line_candidates(source_root)
    selected = select_candidates(candidates, max_cases=max_cases)
    if len(selected) < max_cases:
        raise ValueError(f"Only {len(selected)} eligible lines found; expected {max_cases}")

    crop_root = output_root / "crops"
    crop_root.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    ground_truth_cases: list[dict[str, str]] = []
    grouped: dict[Path, list[tuple[int, LineCandidate]]] = defaultdict(list)
    for index, candidate in enumerate(selected, start=1):
        grouped[candidate.source_path].append((index, candidate))

    scale = dpi / 72.0
    for source_path, source_cases in grouped.items():
        fitz = _import("fitz")
        with fitz.open(source_path) as document:
            for index, candidate in source_cases:
                page = document[candidate.page_index]
                page_rect = page.rect
                x0, y0, x1, y1 = candidate.bbox
                horizontal_padding = max(2.0, (x1 - x0) * 0.015)
                vertical_padding = max(1.5, (y1 - y0) * 0.20)
                clip = fitz.Rect(
                    max(page_rect.x0, x0 - horizontal_padding),
                    max(page_rect.y0, y0 - vertical_padding),
                    min(page_rect.x1, x1 + horizontal_padding),
                    min(page_rect.y1, y1 + vertical_padding),
                )
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    clip=clip,
                    alpha=False,
                )
                case_id = f"LINE-{index:04d}"
                crop_name = f"{case_id}.png"
                crop_path = crop_root / crop_name
                pixmap.save(crop_path)
                crop_digest = _sha256_file(crop_path)
                cases.append(
                    {
                        "caseId": case_id,
                        "cropRelativePath": f"crops/{crop_name}",
                        "cropSha256": crop_digest,
                        "sourceRelativePath": candidate.source_relative_path,
                        "sourceSha256": candidate.source_sha256,
                        "pageIndex": candidate.page_index,
                        "bbox": [round(value, 4) for value in candidate.bbox],
                        "hasExtendedVietnamese": candidate.has_extended_vietnamese,
                    }
                )
                ground_truth_cases.append({"caseId": case_id, "text": candidate.text})

    content_digest = _corpus_digest(cases, ground_truth_cases)
    manifest = {
        "schemaVersion": "1.0.0",
        "datasetId": dataset_id,
        "datasetVersion": dataset_version,
        "contentDigest": content_digest,
        "sourceKind": "synthetic-native-pdf-lines",
        "dpi": dpi,
        "caseCount": len(cases),
        "extendedVietnameseCaseCount": sum(
            int(case["hasExtendedVietnamese"]) for case in cases
        ),
        "cases": cases,
    }
    ground_truth = {
        "datasetId": dataset_id,
        "datasetVersion": dataset_version,
        "contentDigest": content_digest,
        "authorizedForLocalEvaluation": True,
        "cases": ground_truth_cases,
    }
    _write_json(manifest_path, manifest, overwrite=True)
    _write_json(ground_truth_path, ground_truth, overwrite=True)
    print(
        {
            "status": "prepared",
            "caseCount": len(cases),
            "extendedVietnameseCaseCount": manifest["extendedVietnameseCaseCount"],
            "contentDigest": content_digest,
        }
    )


def collect_pdf_line_candidates(source_root: Path) -> list[LineCandidate]:
    fitz = _import("fitz")
    candidates: list[LineCandidate] = []
    for source_path in sorted(source_root.rglob("*.pdf")):
        relative_path = source_path.relative_to(source_root).as_posix()
        source_sha256 = _sha256_file(source_path)
        with fitz.open(source_path) as document:
            for page_index, page in enumerate(document):
                page_dict = page.get_text("dict")
                for block in page_dict.get("blocks", []):
                    for line in block.get("lines", []):
                        spans = line.get("spans", [])
                        text = _normalize_text(
                            "".join(str(span.get("text", "")) for span in spans)
                        )
                        if not _eligible_text(text):
                            continue
                        bbox = _line_bbox(spans)
                        if bbox is None:
                            continue
                        has_extended = any(
                            character.isalpha() and not character.isascii()
                            for character in text
                        )
                        identity = json.dumps(
                            [relative_path, page_index, bbox, text],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        candidates.append(
                            LineCandidate(
                                source_path=source_path,
                                source_relative_path=relative_path,
                                source_sha256=source_sha256,
                                page_index=page_index,
                                bbox=bbox,
                                text=text,
                                has_extended_vietnamese=has_extended,
                                selection_key=hashlib.sha256(
                                    identity.encode("utf-8")
                                ).hexdigest(),
                            )
                        )
    return candidates


def select_candidates(
    candidates: Sequence[LineCandidate],
    *,
    max_cases: int,
) -> list[LineCandidate]:
    extended = sorted(
        (case for case in candidates if case.has_extended_vietnamese),
        key=lambda case: case.selection_key,
    )
    plain = sorted(
        (case for case in candidates if not case.has_extended_vietnamese),
        key=lambda case: case.selection_key,
    )
    extended_target = min(len(extended), math.ceil(max_cases * 0.85))
    selected = extended[:extended_target]
    selected.extend(plain[: max_cases - len(selected)])
    if len(selected) < max_cases:
        selected.extend(extended[extended_target : extended_target + max_cases - len(selected)])
    return sorted(
        selected[:max_cases],
        key=lambda case: (
            case.source_relative_path,
            case.page_index,
            case.bbox[1],
            case.bbox[0],
        ),
    )


def run_backend(
    *,
    backend: str,
    manifest_path: Path,
    output_path: Path,
    device: str,
    batch_size: int,
    model_identifier: str | None,
    model_storage_directory: Path | None,
    overwrite: bool,
) -> None:
    manifest = _read_json(manifest_path)
    cases = _manifest_cases(manifest, manifest_path.parent)
    if output_path.exists() and not overwrite:
        raise FileExistsError("Prediction output already exists; use --overwrite")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    recognizers: dict[
        str,
        Callable[
            [list[tuple[str, Path]], str, int, str | None, Path | None],
            tuple[str, str, list[dict[str, Any]]],
        ],
    ] = {
        "paddle": _run_paddle,
        "easyocr": _run_easyocr,
        "vietocr": _run_vietocr,
    }
    backend_version, resolved_model, predictions = recognizers[backend](
        cases,
        device,
        batch_size,
        model_identifier,
        model_storage_directory,
    )
    payload = {
        "datasetId": manifest["datasetId"],
        "datasetVersion": manifest["datasetVersion"],
        "backendName": backend,
        "backendVersion": backend_version,
        "modelIdentifier": resolved_model,
        "cases": predictions,
    }
    _write_json(output_path, payload, overwrite=overwrite)
    print(
        {
            "status": "predicted",
            "backend": backend,
            "modelIdentifier": resolved_model,
            "caseCount": len(predictions),
        }
    )


def _run_paddle(
    cases: list[tuple[str, Path]],
    device: str,
    batch_size: int,
    model_identifier: str | None,
    model_storage_directory: Path | None,
) -> tuple[str, str, list[dict[str, Any]]]:
    del model_storage_directory
    paddleocr = _import("paddleocr")
    model_name = model_identifier or "latin_PP-OCRv5_mobile_rec"
    model = paddleocr.TextRecognition(model_name=model_name, device=device)
    predictions: list[dict[str, Any]] = []
    for offset in range(0, len(cases), batch_size):
        batch = cases[offset : offset + batch_size]
        started = time.perf_counter()
        results = list(
            model.predict(
                input=[str(path) for _, path in batch],
                batch_size=len(batch),
            )
        )
        duration_ms = (time.perf_counter() - started) * 1000 / max(1, len(batch))
        if len(results) != len(batch):
            raise RuntimeError("PaddleOCR returned a different result count")
        for (case_id, _), result in zip(batch, results, strict=True):
            data = _result_mapping(result)
            predictions.append(
                {
                    "caseId": case_id,
                    "text": str(data.get("rec_text", "")),
                    "confidence": _confidence(data.get("rec_score", 0.0)),
                    "durationMs": round(duration_ms, 4),
                }
            )
    return importlib.metadata.version("paddleocr"), model_name, predictions


def _run_easyocr(
    cases: list[tuple[str, Path]],
    device: str,
    batch_size: int,
    model_identifier: str | None,
    model_storage_directory: Path | None,
) -> tuple[str, str, list[dict[str, Any]]]:
    del device, batch_size
    easyocr = _import("easyocr")
    cv2 = _import("cv2")
    model_name = model_identifier or "easyocr-vi-greedy"
    kwargs: dict[str, Any] = {"gpu": False, "verbose": False}
    if model_storage_directory is not None:
        kwargs["model_storage_directory"] = str(model_storage_directory)
    reader = easyocr.Reader(["vi"], **kwargs)
    predictions: list[dict[str, Any]] = []
    for case_id, path in cases:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise RuntimeError(f"Cannot read crop for {case_id}")
        height, width = image.shape[:2]
        started = time.perf_counter()
        results = reader.recognize(
            image,
            horizontal_list=[[0, width, 0, height]],
            free_list=[],
            decoder="greedy",
            batch_size=1,
            detail=1,
            reformat=False,
            contrast_ths=0.05,
            adjust_contrast=0.7,
        )
        duration_ms = (time.perf_counter() - started) * 1000
        text, confidence = _easyocr_value(results)
        predictions.append(
            {
                "caseId": case_id,
                "text": text,
                "confidence": confidence,
                "durationMs": round(duration_ms, 4),
            }
        )
    return importlib.metadata.version("easyocr"), model_name, predictions


def _run_vietocr(
    cases: list[tuple[str, Path]],
    device: str,
    batch_size: int,
    model_identifier: str | None,
    model_storage_directory: Path | None,
) -> tuple[str, str, list[dict[str, Any]]]:
    del batch_size, model_storage_directory
    config_module = _import("vietocr.tool.config")
    predictor_module = _import("vietocr.tool.predictor")
    image_module = _import("PIL.Image")
    model_name = model_identifier or "vgg_seq2seq"
    config = config_module.Cfg.load_config_from_name(model_name)
    config["device"] = device
    config["cnn"]["pretrained"] = False
    predictor = predictor_module.Predictor(config)
    predictions: list[dict[str, Any]] = []
    for case_id, path in cases:
        with image_module.open(path) as image:
            rgb_image = image.convert("RGB")
            started = time.perf_counter()
            text, probability = predictor.predict(rgb_image, return_prob=True)
            duration_ms = (time.perf_counter() - started) * 1000
        predictions.append(
            {
                "caseId": case_id,
                "text": str(text),
                "confidence": _confidence(probability),
                "durationMs": round(duration_ms, 4),
            }
        )
    return importlib.metadata.version("vietocr"), model_name, predictions


def select_recognizer(
    *,
    report_paths: Sequence[Path],
    baseline_model: str,
    output_path: Path,
    overwrite: bool,
) -> None:
    if len(report_paths) < 2:
        raise ValueError("At least two aggregate reports are required")
    reports = [_read_json(path) for path in report_paths]
    dataset_keys = {
        (
            report.get("datasetId"),
            report.get("datasetVersion"),
            report.get("datasetContentDigest"),
        )
        for report in reports
    }
    if len(dataset_keys) != 1:
        raise ValueError("All reports must use the same dataset version and digest")
    by_model = {str(report["modelIdentifier"]): report for report in reports}
    if baseline_model not in by_model:
        raise ValueError("baseline_model is not present in reports")

    def ranking(report: dict[str, Any]) -> tuple[float, float, float, float]:
        metrics = report["metrics"]
        return (
            -float(metrics["exactMatchRate"]),
            float(metrics["diacriticErrorRate"]),
            -float(metrics["acceptedPrecision"]),
            float(metrics["latencyP95Ms"]),
        )

    winner = min(reports, key=ranking)
    baseline = by_model[baseline_model]
    winner_metrics = winner["metrics"]
    baseline_metrics = baseline["metrics"]
    exact_not_worse = (
        float(winner_metrics["exactMatchRate"])
        >= float(baseline_metrics["exactMatchRate"])
    )
    der_not_worse = (
        float(winner_metrics["diacriticErrorRate"])
        <= float(baseline_metrics["diacriticErrorRate"])
    )
    materially_better = (
        float(winner_metrics["exactMatchRate"])
        > float(baseline_metrics["exactMatchRate"])
        or float(winner_metrics["diacriticErrorRate"])
        < float(baseline_metrics["diacriticErrorRate"])
    )
    winner_model = str(winner["modelIdentifier"])
    if winner_model == baseline_model:
        status = "KEEP_BASELINE"
    elif exact_not_worse and der_not_worse and materially_better:
        status = "SELECTED_FOR_PILOT"
    else:
        status = "HOLD"

    payload = {
        "schemaVersion": "1.0.0",
        "datasetId": winner["datasetId"],
        "datasetVersion": winner["datasetVersion"],
        "datasetContentDigest": winner["datasetContentDigest"],
        "status": status,
        "baselineModel": baseline_model,
        "selectedModel": winner_model if status != "HOLD" else None,
        "rankingPolicy": [
            "highest exactMatchRate",
            "lowest diacriticErrorRate",
            "highest acceptedPrecision",
            "lowest latencyP95Ms",
        ],
        "models": [
            {
                "backendName": report["backendName"],
                "backendVersion": report["backendVersion"],
                "modelIdentifier": report["modelIdentifier"],
                "exactMatchRate": report["metrics"]["exactMatchRate"],
                "diacriticErrorRate": report["metrics"]["diacriticErrorRate"],
                "acceptedPrecision": report["metrics"]["acceptedPrecision"],
                "latencyP95Ms": report["metrics"]["latencyP95Ms"],
            }
            for report in sorted(reports, key=ranking)
        ],
    }
    _write_json(output_path, payload, overwrite=overwrite)
    print(
        {
            "status": status,
            "baselineModel": baseline_model,
            "selectedModel": payload["selectedModel"],
        }
    )


def build_summary(
    *,
    ground_truth_path: Path,
    prediction_paths: Sequence[Path],
    report_paths: Sequence[Path],
    selection_path: Path,
    output_path: Path,
    overwrite: bool,
) -> None:
    ground_truth = _read_json(ground_truth_path)
    references = {
        str(case["caseId"]): _normalize_text(str(case["text"]))
        for case in ground_truth["cases"]
    }
    submissions = [_read_json(path) for path in prediction_paths]
    reports = [_read_json(path) for path in report_paths]
    selection = _read_json(selection_path)
    predictions_by_model: dict[str, dict[str, str]] = {}
    for submission in submissions:
        model = str(submission["modelIdentifier"])
        values = {
            str(case["caseId"]): _normalize_text(str(case["text"]))
            for case in submission["cases"]
        }
        if values.keys() != references.keys():
            raise ValueError(f"Prediction case IDs do not match for {model}")
        predictions_by_model[model] = values

    report_by_model = {
        str(report["modelIdentifier"]): report for report in reports
    }
    if report_by_model.keys() != predictions_by_model.keys():
        raise ValueError("Prediction and aggregate report model sets must match")

    categories = {
        "Có ký tự Việt mở rộng": lambda value: any(
            character.isalpha() and not character.isascii() for character in value
        ),
        "Chữ hoa": lambda value: any(character.isalpha() for character in value)
        and value.upper() == value,
        "Có chữ số": lambda value: any(character.isdigit() for character in value),
        "Dòng ngắn (≤12 ký tự)": lambda value: len(value) <= 12,
        "Dòng dài (≥40 ký tự)": lambda value: len(value) >= 40,
    }
    category_rows: list[tuple[str, str, int, float]] = []
    for model, values in predictions_by_model.items():
        for category, predicate in categories.items():
            case_ids = [
                case_id
                for case_id, reference in references.items()
                if predicate(reference)
            ]
            exact_count = sum(
                values[case_id] == references[case_id] for case_id in case_ids
            )
            category_rows.append(
                (
                    model,
                    category,
                    len(case_ids),
                    exact_count / len(case_ids) if case_ids else 0.0,
                )
            )

    agreement_rows: list[tuple[str, str, int, float]] = []
    model_names = sorted(predictions_by_model)
    for left_index, left_model in enumerate(model_names):
        for right_model in model_names[left_index + 1 :]:
            left = predictions_by_model[left_model]
            right = predictions_by_model[right_model]
            agreed_ids = [
                case_id
                for case_id in references
                if left[case_id] == right[case_id]
            ]
            exact_agreement = sum(
                left[case_id] == references[case_id] for case_id in agreed_ids
            )
            agreement_rows.append(
                (
                    left_model,
                    right_model,
                    len(agreed_ids),
                    exact_agreement / len(agreed_ids) if agreed_ids else 0.0,
                )
            )

    lines = [
        "# Phase 13.2 — Vietnamese Line Recognition",
        "",
        f"- Dataset: `{ground_truth['datasetId']}` `{ground_truth['datasetVersion']}`",
        f"- Digest: `{ground_truth['contentDigest']}`",
        f"- Số crop: {len(references)}",
        f"- Quyết định: **{selection['status']}**",
        f"- Recognizer được chọn: `{selection.get('selectedModel')}`",
        "",
        "## Kết quả tổng hợp",
        "",
        "| Model | Exact Match | CER | DER | Accepted precision | Latency p95 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model, report in sorted(
        report_by_model.items(),
        key=lambda item: (
            -float(item[1]["metrics"]["exactMatchRate"]),
            float(item[1]["metrics"]["diacriticErrorRate"]),
        ),
    ):
        metrics = report["metrics"]
        lines.append(
            f"| `{model}` | {_percent(metrics['exactMatchRate'])} | "
            f"{_percent(metrics['characterErrorRate'])} | "
            f"{_percent(metrics['diacriticErrorRate'])} | "
            f"{_percent(metrics['acceptedPrecision'])} | "
            f"{float(metrics['latencyP95Ms']):.1f} ms |"
        )
    lines.extend(
        [
            "",
            "## Exact Match theo nhóm",
            "",
            "| Model | Nhóm | Support | Exact Match |",
            "|---|---|---:|---:|",
        ]
    )
    for model, category, support, exact_rate in category_rows:
        lines.append(
            f"| `{model}` | {category} | {support} | {_percent(exact_rate)} |"
        )
    lines.extend(
        [
            "",
            "## Đồng thuận giữa recognizer",
            "",
            "| Model A | Model B | Số dòng đồng thuận | Precision khi đồng thuận |",
            "|---|---|---:|---:|",
        ]
    )
    for left, right, count, precision in agreement_rows:
        lines.append(
            f"| `{left}` | `{right}` | {count} | {_percent(precision)} |"
        )
    lines.extend(
        [
            "",
            "## Kết luận",
            "",
            "- Model được chọn chỉ ở trạng thái pilot; corpus synthetic không phải bằng "
            "chứng production.",
            "- Chỉ auto-accept khi recognizer chính và recognizer kiểm chứng đồng thuận; "
            "trường hợp khác phải `needs_review`.",
            "- Raw Ground Truth, crop và prediction tiếp tục nằm ngoài Git.",
            "",
        ]
    )
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {output_path.name}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print({"status": "summarized", "modelCount": len(reports), "caseCount": len(references)})


def _manifest_cases(
    manifest: dict[str, Any],
    corpus_root: Path,
) -> list[tuple[str, Path]]:
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Manifest cases must be a non-empty array")
    cases: list[tuple[str, Path]] = []
    for raw_case in raw_cases:
        case_id = str(raw_case["caseId"])
        relative_path = Path(str(raw_case["cropRelativePath"]))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"Unsafe crop path for {case_id}")
        crop_path = (corpus_root / relative_path).resolve()
        if not crop_path.is_file():
            raise ValueError(f"Missing crop for {case_id}")
        if _sha256_file(crop_path) != raw_case["cropSha256"]:
            raise ValueError(f"Crop digest mismatch for {case_id}")
        cases.append((case_id, crop_path))
    return cases


def _easyocr_value(results: Any) -> tuple[str, float]:
    if not results:
        return "", 0.0
    item = results[0]
    if len(item) < 3:
        return "", 0.0
    return str(item[1]), _confidence(item[2])


def _result_mapping(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    json_value = getattr(result, "json", None)
    if isinstance(json_value, dict):
        result_value = json_value.get("res", json_value)
        return result_value if isinstance(result_value, dict) else {}
    return {}


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _line_bbox(spans: Sequence[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    boxes = [span.get("bbox") for span in spans if span.get("bbox")]
    if not boxes:
        return None
    return (
        min(float(box[0]) for box in boxes),
        min(float(box[1]) for box in boxes),
        max(float(box[2]) for box in boxes),
        max(float(box[3]) for box in boxes),
    )


def _eligible_text(text: str) -> bool:
    if not 3 <= len(text) <= 100:
        return False
    return sum(character.isalpha() for character in text) >= 2


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def _percent(value: Any) -> str:
    return f"{float(value) * 100:.2f}%"


def _corpus_digest(
    cases: Sequence[dict[str, Any]],
    ground_truth_cases: Sequence[dict[str, str]],
) -> str:
    text_by_id = {case["caseId"]: case["text"] for case in ground_truth_cases}
    canonical = [
        {
            "caseId": case["caseId"],
            "cropSha256": case["cropSha256"],
            "sourceSha256": case["sourceSha256"],
            "pageIndex": case["pageIndex"],
            "bbox": case["bbox"],
            "text": text_by_id[case["caseId"]],
        }
        for case in cases
    ]
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _import(module_name: str) -> Any:
    return __import__(module_name, fromlist=["*"])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 13.2 line recognition benchmark")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="Create fixed line crops from native PDFs")
    prepare.add_argument("--source-root", type=Path, required=True)
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.add_argument("--max-cases", type=int, default=240)
    prepare.add_argument("--dpi", type=int, default=300)
    prepare.add_argument("--dataset-id", default="synthetic-hr-vi-lines")
    prepare.add_argument("--dataset-version", default="1.0.0")
    prepare.add_argument("--overwrite", action="store_true")

    run = commands.add_parser("run", help="Run one recognizer on the fixed crops")
    run.add_argument("--backend", choices=("paddle", "easyocr", "vietocr"), required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--device", default="cpu")
    run.add_argument("--batch-size", type=int, default=8)
    run.add_argument("--model-identifier")
    run.add_argument("--model-storage-directory", type=Path)
    run.add_argument("--overwrite", action="store_true")

    select = commands.add_parser("select", help="Rank aggregate recognition reports")
    select.add_argument("--report", type=Path, action="append", required=True)
    select.add_argument("--baseline-model", required=True)
    select.add_argument("--output", type=Path, required=True)
    select.add_argument("--overwrite", action="store_true")

    summarize = commands.add_parser(
        "summarize",
        help="Build an aggregate Markdown report without raw text",
    )
    summarize.add_argument("--ground-truth", type=Path, required=True)
    summarize.add_argument("--prediction", type=Path, action="append", required=True)
    summarize.add_argument("--report", type=Path, action="append", required=True)
    summarize.add_argument("--selection", type=Path, required=True)
    summarize.add_argument("--output", type=Path, required=True)
    summarize.add_argument("--overwrite", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
