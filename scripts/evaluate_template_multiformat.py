"""Aggregate-only UAT for the two approved templates across local formats."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcns_agent.ports.document_parser import DocumentSource  # noqa: E402
from hcns_agent.templates.service import (  # noqa: E402
    TemplateProcessingService,
    TemplateTechnicalError,
    TemplateUnsupportedError,
    build_default_template_processing_service,
    build_local_template_processing_service,
)

SUPPORTED_FORMATS = ("docx", "pdf", "image", "scan_pdf")
SCHEMAS = {
    "LEAVE_REQUEST": ROOT / "schemas/templates/leave_request_v1.schema.json",
    "OVERTIME_REQUEST": ROOT / "schemas/templates/overtime_request_v1.schema.json",
}
MEDIA_TYPES = {
    "docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
    "pdf": "application/pdf",
    "image": "image/png",
    "scan_pdf": "application/pdf",
}


@dataclass(frozen=True, slots=True)
class EvaluationItem:
    format_name: str
    filename: str
    content: bytes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate DOCX, native PDF, camera image and image-backed PDF "
            "without logging field values"
        )
    )
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "--formats",
        default=",".join(SUPPORTED_FORMATS),
        help="Comma-separated subset: docx,pdf,image,scan_pdf",
    )
    parser.add_argument("--ocr-device", default="cpu")
    parser.add_argument("--minimum-ocr-required-em", type=float, default=0.8)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requested_formats = tuple(
        dict.fromkeys(value.strip() for value in args.formats.split(",") if value.strip())
    )
    unknown = sorted(set(requested_formats) - set(SUPPORTED_FORMATS))
    if unknown:
        raise SystemExit(f"Unsupported evaluation formats: {','.join(unknown)}")
    if not 0.0 <= args.minimum_ocr_required_em <= 1.0:
        raise SystemExit("--minimum-ocr-required-em must be between 0 and 1")

    dataset = _load_dataset(args.data_root)
    records = dataset["documents"]
    if not isinstance(records, list):
        raise SystemExit("Ground Truth documents must be an array")

    service = _build_service(requested_formats, args.ocr_device)
    definitions = {
        str(item["templateId"]): item for item in service.list_templates()
    }
    validators = {
        document_type: Draft202012Validator(_load_json(schema_path))
        for document_type, schema_path in SCHEMAS.items()
    }
    counters = {format_name: Counter() for format_name in requested_formats}
    mismatch_fields = {
        format_name: Counter() for format_name in requested_formats
    }
    technical_errors = {
        format_name: Counter() for format_name in requested_formats
    }
    parser_versions: set[str] = set()
    ocr_engines: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            continue
        template_id = str(record.get("templateId", ""))
        definition = definitions.get(template_id)
        if definition is None:
            continue
        required_fields = tuple(str(value) for value in definition["requiredFields"])
        expected_type = str(record.get("documentType", ""))
        validator = validators.get(expected_type)
        if validator is None:
            continue

        for item in _items_for_record(args.data_root, record, requested_formats):
            metric = counters[item.format_name]
            metric["available"] += 1
            try:
                result = service.process(
                    DocumentSource(
                        document_id=(
                            f"uat-{item.format_name}-{metric['available']:03d}"
                        ),
                        filename=item.filename,
                        content=item.content,
                        declared_media_type=MEDIA_TYPES[item.format_name],
                        source_reference="local-uat",
                    )
                )
            except TemplateTechnicalError as error:
                metric["technicalErrors"] += 1
                technical_errors[item.format_name][error.code] += 1
                continue
            except TemplateUnsupportedError:
                metric["unsupported"] += 1
                continue

            metric["processed"] += 1
            metric["classificationCorrect"] += int(
                result.detection.definition.document_type.value == expected_type
                and result.detection.definition.template_id == template_id
            )
            schema_errors = tuple(validator.iter_errors(result.data))
            metric["schemaErrors"] += len(schema_errors)
            required_exact_for_item = 0
            for field_name in required_fields:
                metric["requiredTotal"] += 1
                exact = result.data.get(field_name) == record.get(field_name)
                metric["requiredExact"] += int(exact)
                required_exact_for_item += int(exact)
                if not exact:
                    mismatch_fields[item.format_name][field_name] += 1

            action = result.validation.recommended_action.value
            metric["autoContinue"] += int(action == "AUTO_CONTINUE")
            metric["manualReview"] += int(action == "MANUAL_REVIEW")
            item_required_exact = required_exact_for_item == len(required_fields)
            metric["falseAutoContinue"] += int(
                action == "AUTO_CONTINUE"
                and (not item_required_exact or bool(schema_errors))
            )
            processing = result.processing
            parser_versions.add(
                f"{processing['parserName']}@{processing['parserVersion']}"
            )
            if processing.get("ocrEngine"):
                ocr_engines.add(str(processing["ocrEngine"]))

    metrics = {
        format_name: _metric_report(
            counters[format_name],
            mismatch_fields[format_name],
            technical_errors[format_name],
        )
        for format_name in requested_formats
    }
    dataset_integrity = _dataset_integrity(args.data_root, dataset)
    gates = _evaluate_gates(
        metrics,
        requested_formats,
        args.minimum_ocr_required_em,
    )
    report = {
        "schemaVersion": "template-multiformat-uat/1.0.0",
        "datasetVersion": dataset.get("version", "unknown"),
        "requestedFormats": list(requested_formats),
        "datasetIntegrity": dataset_integrity,
        "runtime": {
            "parserVersions": sorted(parser_versions),
            "ocrEngines": sorted(ocr_engines),
            "ocrDevice": args.ocr_device,
        },
        "metrics": metrics,
        "gates": gates,
        "passed": all(gates.values()),
        "containsRawFieldValues": False,
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0 if report["passed"] else 1


def _build_service(
    requested_formats: tuple[str, ...],
    device: str,
) -> TemplateProcessingService:
    if {"image", "scan_pdf"} & set(requested_formats):
        return build_local_template_processing_service(device=device)
    return build_default_template_processing_service()


def _items_for_record(
    data_root: Path,
    record: dict[str, Any],
    requested_formats: tuple[str, ...],
) -> Iterable[EvaluationItem]:
    files = record.get("files")
    file_map = files if isinstance(files, dict) else {}
    for format_name in requested_formats:
        if format_name in {"docx", "pdf"}:
            relative = file_map.get(format_name)
            if isinstance(relative, str):
                path = data_root / relative
                if path.is_file():
                    yield EvaluationItem(format_name, path.name, path.read_bytes())
            continue

        if format_name not in {"image", "scan_pdf"}:
            continue
        linked_images = record.get("linkedImageFiles")
        if not isinstance(linked_images, list):
            continue
        for relative in linked_images:
            if not isinstance(relative, str):
                continue
            path = data_root / relative
            if not path.is_file():
                continue
            content = path.read_bytes()
            if format_name == "image":
                yield EvaluationItem(format_name, path.name, content)
            else:
                yield EvaluationItem(
                    format_name,
                    f"{path.stem}.scan.pdf",
                    _image_backed_pdf(content),
                )


def _image_backed_pdf(image_bytes: bytes) -> bytes:
    import fitz
    from PIL import Image

    with Image.open(BytesIO(image_bytes)) as image:
        width, height = image.size
    document = fitz.open()
    try:
        page = document.new_page(width=width, height=height)
        page.insert_image(page.rect, stream=image_bytes)
        return document.tobytes()
    finally:
        document.close()


def _dataset_integrity(data_root: Path, dataset: dict[str, Any]) -> dict[str, object]:
    records = dataset.get("documents")
    documents = records if isinstance(records, list) else []
    referenced = 0
    stale = 0
    linked_images = 0
    for record in documents:
        if not isinstance(record, dict):
            continue
        files = record.get("files")
        if isinstance(files, dict):
            for relative in files.values():
                if not isinstance(relative, str):
                    continue
                referenced += 1
                stale += int(not (data_root / relative).is_file())
        linked = record.get("linkedImageFiles")
        if isinstance(linked, list):
            linked_images += sum(
                1
                for relative in linked
                if isinstance(relative, str) and (data_root / relative).is_file()
            )
    actual_document_files = sum(
        1
        for suffix in ("*.docx", "*.pdf", "*.png", "*.jpg", "*.jpeg")
        for _ in data_root.rglob(suffix)
    )
    return {
        "declaredUniqueDocuments": dataset.get("uniqueDocuments"),
        "declaredExportedFiles": dataset.get("exportedFiles"),
        "actualDocumentFiles": actual_document_files,
        "referencedFiles": referenced,
        "staleFileReferences": stale,
        "linkedImagesAvailable": linked_images,
    }


def _metric_report(
    metric: Counter[str],
    mismatches: Counter[str],
    errors: Counter[str],
) -> dict[str, object]:
    return {
        "available": metric["available"],
        "processed": metric["processed"],
        "classification": {
            "correct": metric["classificationCorrect"],
            "rate": _rate(metric["classificationCorrect"], metric["processed"]),
        },
        "requiredFieldExactMatch": {
            "correct": metric["requiredExact"],
            "total": metric["requiredTotal"],
            "rate": _rate(metric["requiredExact"], metric["requiredTotal"]),
        },
        "schemaErrorCount": metric["schemaErrors"],
        "autoContinueCount": metric["autoContinue"],
        "manualReviewCount": metric["manualReview"],
        "falseAutoContinueCount": metric["falseAutoContinue"],
        "technicalErrorCount": metric["technicalErrors"],
        "unsupportedCount": metric["unsupported"],
        "mismatchFields": dict(sorted(mismatches.items())),
        "technicalErrors": dict(sorted(errors.items())),
    }


def _evaluate_gates(
    metrics: dict[str, dict[str, object]],
    requested_formats: tuple[str, ...],
    minimum_ocr_required_em: float,
) -> dict[str, bool]:
    gates: dict[str, bool] = {}
    for format_name in requested_formats:
        metric = metrics[format_name]
        classification = metric["classification"]
        required = metric["requiredFieldExactMatch"]
        assert isinstance(classification, dict)
        assert isinstance(required, dict)
        available = int(metric["available"])
        processed = int(metric["processed"])
        is_ocr = format_name in {"image", "scan_pdf"}
        required_gate = minimum_ocr_required_em if is_ocr else 1.0
        gates[f"{format_name}:all_available_processed"] = (
            available > 0
            and processed == available
            and int(metric["technicalErrorCount"]) == 0
            and int(metric["unsupportedCount"]) == 0
        )
        gates[f"{format_name}:classification"] = (
            int(classification["correct"]) == processed
        )
        gates[f"{format_name}:required_field_em"] = (
            float(required["rate"]) >= required_gate
        )
        gates[f"{format_name}:schema"] = int(metric["schemaErrorCount"]) == 0
        gates[f"{format_name}:no_false_auto_continue"] = (
            int(metric["falseAutoContinueCount"]) == 0
        )
        if is_ocr:
            gates[f"{format_name}:review_routing"] = (
                int(metric["manualReviewCount"]) == processed
            )
    return gates


def _load_dataset(data_root: Path) -> dict[str, Any]:
    path = data_root / "json" / "ground_truth_10_samples.json"
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise SystemExit("Ground Truth root must be an object")
    return payload


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
