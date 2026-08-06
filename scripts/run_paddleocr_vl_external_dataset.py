#!/usr/bin/env python3
"""Run a private, CPU-first PaddleOCR-VL benchmark over the fixed scan subset."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "ocr_lab" / "api"
for path in (ROOT, API):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from external_dataset_prediction import (  # noqa: E402
    FIELD_SPECS,
    _external_fields,
    _fold,
    classify_phase15_document,
    extract_phase15_document,
)

# Public DATA-21 pin; PaddleOCR 3.7 resolves this pipeline to its registered
# 0.9B engine name. Keep both names in the manifest for reproducibility.
MODEL_NAME = "PaddleOCR-VL-1.6"
RUNTIME_MODEL_NAME = "PaddleOCR-VL-1.6-0.9B"
PIPELINE_VERSION = "v1.6"
VLM_MAX_PIXELS = 500_000
VLM_MAX_NEW_TOKENS = 1_024
SCAN_FORMATS = frozenset({"IMAGE", "PDF_SCAN"})
PREDICTION_SCHEMA_VERSION = "external-dataset-predictions/data21-vl/1.0.0"
REPORT_SCHEMA_VERSION = "data21-paddleocr-vl-benchmark-report/1.0.0"
MARKER_SCHEMA_VERSION = "data21-paddleocr-vl-benchmark/1.0.0"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _tree_manifest(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        return {"available": False, "fileCount": 0, "byteCount": 0, "sha256": None}
    digest = hashlib.sha256()
    file_count = 0
    byte_count = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        file_digest = _sha256(path).encode("ascii")
        size = path.stat().st_size
        digest.update(relative + b"\0" + file_digest + b"\0")
        file_count += 1
        byte_count += size
    return {
        "available": True,
        "fileCount": file_count,
        "byteCount": byte_count,
        "sha256": f"sha256:{digest.hexdigest()}",
    }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return round(ordered[index], 3)


def _private_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ValueError("DATA-21 outputs must stay outside the Git worktree")
    return resolved


def _source_path(dataset_root: Path, record: dict[str, Any]) -> Path:
    relative = Path(str(record.get("sourceRelativePath", "")))
    source = (dataset_root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe sourceRelativePath")
    if dataset_root not in source.parents or not source.is_file():
        raise FileNotFoundError("Benchmark source is unavailable")
    expected = str(record.get("sourceSha256", ""))
    if expected and expected != _sha256(source):
        raise ValueError(f"Source digest mismatch for {record.get('caseId')}")
    return source


def _scan_records(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    records = inventory.get("cases")
    if not isinstance(records, list):
        raise ValueError("Inventory cases are missing")
    selected = [
        record
        for record in records
        if str(record.get("sourceFormat", "")) in SCAN_FORMATS
    ]
    if not selected:
        raise ValueError("Fixed scan subset is empty")
    return selected


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _result_json(result: Any) -> dict[str, Any]:
    payload = getattr(result, "json", result)
    if isinstance(payload, str):
        payload = json.loads(payload)
    return _json_safe(payload) if isinstance(payload, dict) else {"result": _json_safe(payload)}


def _result_markdown(result: Any) -> str:
    markdown = getattr(result, "markdown", {})
    if callable(markdown):
        markdown = markdown()
    if isinstance(markdown, dict):
        return str(markdown.get("markdown_texts", ""))
    return str(markdown or "")


def _markdown_canonical(markdown_pages: Iterable[str]) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    plain_pages: list[str] = []
    for page_index, markdown in enumerate(markdown_pages):
        blocks = []
        for block_index, line in enumerate(markdown.splitlines()):
            text = line.strip()
            if not text:
                continue
            blocks.append(
                {
                    "text": text,
                    "sourceKind": "ocr",
                    "confidence": 1.0,
                    "evidence": {
                        "pageIndex": page_index,
                        "sourceRef": f"paddleocr-vl:{page_index}:{block_index}",
                        "bbox": None,
                    },
                }
            )
        pages.append({"blocks": blocks, "ocrBlocks": blocks})
        plain_pages.append(markdown)
    return {
        "plainText": "\n\n".join(plain_pages),
        "pages": pages,
        "tables": [],
    }


def _empty_fields(category: str) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "value": None,
            "normalizedValue": None,
            "status": "needs_review",
            "extractor": "paddleocr-vl-failed",
            "evidence": [],
        }
        for name in FIELD_SPECS[category]
    }


def _extract_fields(category: str, markdown_pages: list[str]) -> tuple[str, dict[str, dict[str, Any]]]:
    canonical = _markdown_canonical(markdown_pages)
    classification = classify_phase15_document(canonical)
    extraction = extract_phase15_document(canonical, classification)
    predicted_category = {
        "CV": "cv",
        "CONTRACT_DECISION": "contract",
        "DEGREE_CERTIFICATE": "ielts",
    }.get(str(classification.get("documentFamily")), "unknown")
    if predicted_category == "unknown" and "ielts" in _fold(canonical.get("plainText")):
        predicted_category = "ielts"
    return predicted_category, _external_fields(category, canonical, extraction, ocr=True)


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _model_manifest(
    *,
    runtime_root: Path,
    model_dir: Path | None,
    device: str,
    backend: str,
) -> dict[str, Any]:
    return {
        "modelName": MODEL_NAME,
        "runtimeModelName": RUNTIME_MODEL_NAME,
        "pipelineVersion": PIPELINE_VERSION,
        "inferenceSettings": {
            "maxPixels": VLM_MAX_PIXELS,
            "maxNewTokens": VLM_MAX_NEW_TOKENS,
        },
        "backend": backend,
        "device": device,
        "pythonVersion": platform.python_version(),
        "packages": {
            "paddleocr": _package_version("paddleocr"),
            "paddlepaddle": _package_version("paddlepaddle"),
            "paddlex": _package_version("paddlex"),
        },
        "modelDirectory": _tree_manifest(model_dir) if model_dir else None,
        "runtimeTree": _tree_manifest(runtime_root),
    }


def _benchmark_report(
    *,
    dataset: dict[str, Any],
    model_manifest: dict[str, Any],
    requested: int,
    processed: int,
    failed: int,
    page_count: int,
    latencies: list[float],
    peak_python_bytes: int,
    peak_rss_bytes: int | None,
    failures: dict[str, int],
    status: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "evaluationKind": "local-paddleocr-vl-benchmark",
        "datasetId": dataset.get("datasetId"),
        "datasetDigest": dataset.get("contentDigest"),
        "scope": "fixed-development-scan-subset",
        "modelManifest": model_manifest,
        "documents": {
            "requestedCount": requested,
            "processedCount": processed,
            "failedCount": failed,
            "pageCount": page_count,
        },
        "system": {
            "latencyP50Ms": _percentile(latencies, 0.50),
            "latencyP95Ms": _percentile(latencies, 0.95),
            "failureCount": failed,
            "failureRate": round(failed / max(1, requested), 6),
            "peakPythonMemoryBytes": peak_python_bytes,
            "peakRssBytes": peak_rss_bytes,
            "memoryMeasurement": "tracemalloc Python heap; RSS when psutil is available",
        },
        "failuresByCode": failures,
        "quality": {
            "strictFieldExactMatchRate": None,
            "acceptedFieldMatchRate": None,
            "applicableCompletenessRate": None,
            "scoringStatus": "PENDING_DEVELOPMENT_AGGREGATE",
        },
        "safety": {
            "localOnly": True,
            "rawValuesInReport": False,
            "scanAlwaysManualReview": True,
            "fallbackEnabled": False,
            "promotionAllowed": False,
            "evaluateOnceArtifactTouched": False,
        },
        "decision": status,
        "containsRawFieldValues": False,
    }


def _rss_bytes() -> int | None:
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--raw-output-dir", type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu")
    args = parser.parse_args()

    if args.model != MODEL_NAME:
        raise SystemExit(f"DATA-21 pins model {MODEL_NAME}")
    output = _private_path(args.output)
    report_path = _private_path(
        args.report or output.with_name(f"{output.stem}-benchmark-report.json")
    )
    marker_path = _private_path(
        args.marker or output.with_name(f"{output.stem}.marker.json")
    )
    raw_output_dir = _private_path(
        args.raw_output_dir or output.with_name(f"{output.stem}-raw")
    )
    runtime_root = _private_path(
        args.runtime_root or output.with_name(f"{output.stem}-runtime")
    )
    model_dir = _private_path(args.model_dir) if args.model_dir else None
    output_paths = (output, report_path, marker_path)
    if any(path.exists() for path in output_paths):
        raise SystemExit("DATA-21 artifact already exists; choose new private paths")
    if model_dir is not None and not model_dir.is_dir():
        raise SystemExit("--model-dir must point to a local model directory")

    dataset_root = args.dataset_root.expanduser().resolve()
    inventory = _read_object(args.inventory.expanduser().resolve())
    records = _scan_records(inventory)
    dataset = inventory.get("dataset", {})
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    runtime_root.mkdir(parents=True, exist_ok=True)
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(runtime_root)

    try:
        import paddle
        from paddleocr import PaddleOCRVL

        paddle.set_device("cpu" if args.device == "cpu" else "gpu")
        pipeline = PaddleOCRVL(
            pipeline_version=PIPELINE_VERSION,
            vl_rec_model_name=RUNTIME_MODEL_NAME,
            vl_rec_model_dir=str(model_dir) if model_dir else None,
            vl_rec_backend="native",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_layout_detection=True,
            use_chart_recognition=False,
            use_seal_recognition=False,
            use_ocr_for_image_block=False,
            device="cpu" if args.device == "cpu" else "gpu",
        )
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - benchmark must fail closed
        manifest = _model_manifest(
            runtime_root=runtime_root,
            model_dir=model_dir,
            device=args.device,
            backend="native",
        )
        report = _benchmark_report(
            dataset=dataset,
            model_manifest=manifest,
            requested=len(records),
            processed=0,
            failed=len(records),
            page_count=0,
            latencies=[],
            peak_python_bytes=0,
            peak_rss_bytes=_rss_bytes(),
            failures={type(exc).__name__: len(records)},
            status="HOLD",
        )
        _write_json(report_path, report)
        _write_json(
            marker_path,
            {
                "schemaVersion": MARKER_SCHEMA_VERSION,
                "evaluationKind": "local-paddleocr-vl-benchmark",
                "datasetId": dataset.get("datasetId"),
                "reportSha256": _sha256(report_path),
                "modelManifest": manifest,
                "evaluateOnceArtifactTouched": False,
                "promotionAllowed": False,
                "decision": "HOLD",
            },
        )
        raise SystemExit(f"PaddleOCR-VL initialization failed: {type(exc).__name__}") from exc

    documents: list[dict[str, Any]] = []
    latencies: list[float] = []
    failures: dict[str, int] = {}
    processed = 0
    page_count = 0
    peak_python_bytes = 0
    peak_rss_bytes: int | None = None
    tracemalloc.start()
    try:
        for record in records:
            case_id = str(record.get("caseId"))
            category = str(record.get("category"))
            source = _source_path(dataset_root, record)
            started = time.perf_counter()
            markdown_pages: list[str] = []
            raw_pages: list[dict[str, Any]] = []
            failure_code: str | None = None
            try:
                for result in pipeline.predict(
                    str(source),
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_layout_detection=True,
                    use_chart_recognition=False,
                    use_seal_recognition=False,
                    use_ocr_for_image_block=False,
                    max_pixels=VLM_MAX_PIXELS,
                    max_new_tokens=VLM_MAX_NEW_TOKENS,
                ):
                    raw_pages.append({"json": _result_json(result)})
                    markdown_pages.append(_result_markdown(result))
                if not markdown_pages:
                    raise RuntimeError("EMPTY_PREDICTION")
                predicted_category, fields = _extract_fields(category, markdown_pages)
                page_count += len(markdown_pages)
                processed += 1
            except (Exception, SystemExit) as exc:  # noqa: BLE001 - one bad source must not promote
                failure_code = type(exc).__name__
                failures[failure_code] = failures.get(failure_code, 0) + 1
                predicted_category = "unknown"
                fields = _empty_fields(category)
            latency_ms = (time.perf_counter() - started) * 1000.0
            latencies.append(latency_ms)
            _, current_peak = tracemalloc.get_traced_memory()
            peak_python_bytes = max(peak_python_bytes, current_peak)
            current_rss = _rss_bytes()
            if current_rss is not None:
                peak_rss_bytes = max(peak_rss_bytes or 0, current_rss)
            raw_json_path = raw_output_dir / f"{case_id}.json"
            raw_md_path = raw_output_dir / f"{case_id}.md"
            _write_json(raw_json_path, {"caseId": case_id, "pages": raw_pages})
            raw_md_path.write_text("\n\n".join(markdown_pages), encoding="utf-8")
            documents.append(
                {
                    "caseId": case_id,
                    "category": category,
                    "sourceFormat": record.get("sourceFormat"),
                    "sourceFile": source.name,
                    "sourceSha256": record.get("sourceSha256"),
                    "predictedCategory": predicted_category,
                    "classification": {
                        "documentType": None,
                        "documentFamily": None,
                        "status": "needs_review",
                        "confidence": None,
                    },
                    "fields": fields,
                    "evaluationIncluded": True,
                    "processing": {
                        "usesOcr": True,
                        "ocrEngine": MODEL_NAME,
                        "ocrScope": "OCR_ALLOWED",
                        "recommendedAction": "MANUAL_REVIEW",
                        "parserVersion": "data21-paddleocr-vl-markdown-adapter/1.0.0",
                        "latencyMs": round(latency_ms, 3),
                        "failureCode": failure_code,
                    },
                }
            )
    finally:
        tracemalloc.stop()
        try:
            pipeline.close()
        except (Exception, SystemExit):  # noqa: BLE001 - preserve the report on close errors
            failures["PIPELINE_CLOSE_ERROR"] = failures.get("PIPELINE_CLOSE_ERROR", 0) + 1

    manifest = _model_manifest(
        runtime_root=runtime_root,
        model_dir=model_dir,
        device=args.device,
        backend="native",
    )
    status = "BENCHMARK_DONE_FALLBACK_DISABLED" if not failures else "HOLD"
    report = _benchmark_report(
        dataset=dataset,
        model_manifest=manifest,
        requested=len(records),
        processed=processed,
        failed=len(failures) and sum(failures.values()),
        page_count=page_count,
        latencies=latencies,
        peak_python_bytes=peak_python_bytes,
        peak_rss_bytes=peak_rss_bytes,
        failures=failures,
        status=status,
    )
    prediction = {
        "schemaVersion": PREDICTION_SCHEMA_VERSION,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "datasetId": dataset.get("datasetId"),
        "datasetDigest": dataset.get("contentDigest"),
        "documentCount": len(documents),
        "containsRealPII": True,
        "localOnly": True,
        "predictionBlindDuringGroundTruthReview": True,
        "ocrScopePolicy": "data21-fixed-development-scan-subset",
        "modelManifest": manifest,
        "documents": documents,
    }
    _write_json(output, prediction)
    _write_json(report_path, report)
    _write_json(
        marker_path,
        {
            "schemaVersion": MARKER_SCHEMA_VERSION,
            "evaluationKind": "local-paddleocr-vl-benchmark",
            "datasetId": dataset.get("datasetId"),
            "predictionSha256": _sha256(output),
            "reportSha256": _sha256(report_path),
            "modelManifest": manifest,
            "evaluateOnceArtifactTouched": False,
            "promotionAllowed": False,
            "fallbackEnabled": False,
            "decision": status,
        },
    )
    print(
        "DATA-21 benchmark ready: "
        f"processed={processed}/{len(records)} failures={sum(failures.values())} "
        f"p95_ms={report['system']['latencyP95Ms']} decision={status}"
    )
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
