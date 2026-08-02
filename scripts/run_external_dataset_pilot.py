"""Run an aggregate-only local intake pilot over an external inventory.

No OCR text, field values, source paths or per-document payloads are written to
the report.  The pilot is intentionally not a promotion benchmark because this
dataset has no independently reviewed Ground Truth in the repository contract.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from hcns_agent.adapters.easyocr import EasyOcrEngine
from hcns_agent.adapters.external_dataset import count_source_format_and_pages
from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.application.external_dataset import (
    ExternalDatasetError,
    read_inventory,
    validate_inventory,
)
from hcns_agent.bootstrap import build_default_pipeline
from hcns_agent.domain.errors import DocumentIntakeError
from hcns_agent.domain.understanding import QualityStatus
from hcns_agent.ports.document_parser import DocumentSource


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ocr-backend", choices=("easyocr", "mock"), default="easyocr")
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = read_inventory(args.inventory)
    try:
        validate_inventory(
            args.dataset_root,
            inventory,
            page_counter=count_source_format_and_pages,
        )
    except ExternalDatasetError as error:
        raise SystemExit(f"Pilot rejected: {error}") from error
    if args.output.exists() and not args.overwrite:
        raise SystemExit("Pilot report exists; pass --overwrite")

    ocr_engine = _build_ocr_engine(args.ocr_backend, args.model_root)
    pipeline = build_default_pipeline(ocr_engine)
    dataset = _object(inventory, "dataset")
    cases = _objects(inventory, "cases")
    expected_types = {str(case["caseId"]): str(case["documentType"]) for case in cases}
    root = args.dataset_root.resolve(strict=True)
    statuses: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    expected_by_type: dict[str, dict[str, int]] = defaultdict(
        lambda: {"cases": 0, "predictedMatch": 0, "predictedUnknown": 0, "reviewRequired": 0}
    )
    failures: Counter[str] = Counter()
    warning_codes: Counter[str] = Counter()
    parser_names: Counter[str] = Counter()
    latencies: list[float] = []
    processed = 0

    for case in sorted(cases, key=lambda item: str(item["caseId"])):
        case_id = str(case["caseId"])
        source_path = (
            root / Path(*str(case["sourceRelativePath"]).split("/"))
        ).resolve(strict=True)
        content = source_path.read_bytes()
        source = DocumentSource(
            document_id=case_id,
            filename=source_path.name,
            content=content,
            source_reference=f"dataset://{dataset['datasetId']}/{case_id}",
        )
        started = time.perf_counter()
        expected_type = expected_types[case_id]
        expected_metric = expected_by_type[expected_type]
        expected_metric["cases"] += 1
        try:
            result = pipeline.execute(source)
            elapsed = (time.perf_counter() - started) * 1000.0
            latencies.append(elapsed)
            processed += 1
            predicted_type = result.classification.document_type.value
            statuses[result.quality.status.value] += 1
            formats[result.canonical_document.source_format.value] += 1
            expected_metric["predictedMatch"] += int(predicted_type == expected_type)
            expected_metric["predictedUnknown"] += int(predicted_type == "UNKNOWN")
            expected_metric["reviewRequired"] += int(result.quality.review_required)
            for provenance in result.canonical_document.provenance:
                parser_names[provenance.parser_name] += 1
            for warning in result.canonical_document.warnings:
                warning_codes[warning.code] += 1
        except Exception as error:  # noqa: BLE001 - pilot must aggregate failures and continue
            elapsed = (time.perf_counter() - started) * 1000.0
            latencies.append(elapsed)
            code = _failure_code(error)
            failures[code] += 1
            statuses[QualityStatus.REJECTED.value] += 1
            expected_metric["reviewRequired"] += 1

    ground_truth_provided = False
    promotion_reasons: list[str] = []
    if str(dataset["authorizationStatus"]) != "APPROVED":
        promotion_reasons.append("authorizationStatus is not APPROVED")
    if not ground_truth_provided:
        promotion_reasons.append("independent Ground Truth is not provided")
    if int(dataset["pageCount"]) < 30:
        promotion_reasons.append("pilot page count is below the 30-page benchmark minimum")

    report = {
        "schemaVersion": "1.0.0",
        "dataset": {
            "id": dataset["datasetId"],
            "version": dataset["version"],
            "sourceCommit": dataset["sourceCommit"],
            "contentDigest": dataset["contentDigest"],
            "documentCount": dataset["documentCount"],
            "pageCount": dataset["pageCount"],
            "authorizationStatus": dataset["authorizationStatus"],
            "dataClassification": dataset["dataClassification"],
        },
        "backend": {
            "name": ocr_engine.name,
            "packageVersion": _package_version("easyocr" if args.ocr_backend == "easyocr" else ""),
        },
        "policy": {
            "groundTruthProvided": ground_truth_provided,
            "groundTruthSource": "NOT_PROVIDED",
            "reportContainsRawFieldValues": False,
            "reportContainsRawOcrText": False,
            "promotionAllowed": False,
            "ocrReviewRequired": True,
        },
        "metrics": {
            "inventoryVerified": True,
            "caseCount": len(cases),
            "processedCount": processed,
            "failureCount": sum(failures.values()),
            "qualityStatusCounts": dict(sorted(statuses.items())),
            "sourceFormatCounts": dict(sorted(formats.items())),
            "expectedTypeCoverage": {
                key: value for key, value in sorted(expected_by_type.items())
            },
            "failureCodeCounts": dict(sorted(failures.items())),
            "warningCodeCounts": dict(sorted(warning_codes.items())),
            "parserCounts": dict(sorted(parser_names.items())),
            "latencyMs": _latency_metrics(latencies),
        },
        "promotionDecision": {
            "status": "HOLD",
            "reasons": promotion_reasons,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Pilot complete: cases={len(cases)} processed={processed} "
        f"failures={sum(failures.values())} decision=HOLD"
    )
    print(f"Aggregate report written outside repository: {args.output.resolve()}")
    return 0


def _build_ocr_engine(backend: str, model_root: Path | None):
    if backend == "mock":
        return DeterministicMockOcrEngine()
    return EasyOcrEngine.from_default(
        device="cpu",
        model_storage_directory=model_root,
    )


def _latency_metrics(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, max(0, int(round(0.95 * len(ordered))) - 1))
    return {
        "p50": round(statistics.median(ordered), 3),
        "p95": round(ordered[p95_index], 3),
    }


def _failure_code(error: Exception) -> str:
    if isinstance(error, DocumentIntakeError):
        return f"INTAKE_{error.code.value}"
    return f"PILOT_{type(error).__name__.upper()}"


def _package_version(package: str) -> str:
    if not package:
        return "n/a"
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise SystemExit(f"Inventory {key} must be an object")
    return value


def _objects(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SystemExit(f"Inventory {key} must be an object list")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
