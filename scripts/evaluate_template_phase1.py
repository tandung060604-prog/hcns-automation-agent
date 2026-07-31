"""Aggregate-only regression evaluation for the local 14-document fixture set."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.templates.service import build_default_template_processing_service

ROOT = Path(__file__).resolve().parents[1]
GROUPS = (
    (
        "leave_request",
        "leave_requests",
        "LEAVE_REQUEST",
        "leave-request-v1",
        "schemas/templates/leave_request_v1.schema.json",
    ),
    (
        "overtime_request",
        "overtime_requests",
        "OVERTIME_REQUEST",
        "overtime-request-v1",
        "schemas/templates/overtime_request_v1.schema.json",
    ),
)
IGNORED_COMPARISON_FIELDS = frozenset({"templateId", "templateVersion"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate template-first Phase 1 without logging fixture values"
    )
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    service = build_default_template_processing_service()
    document_count = 0
    classification_correct = 0
    required_total = 0
    required_exact = 0
    all_field_total = 0
    all_field_exact = 0
    schema_error_count = 0
    auto_continue_count = 0
    mismatch_fields: Counter[str] = Counter()

    for group, folder, expected_type, expected_template, schema_relative in GROUPS:
        records = load_json(
            args.data_root / "json" / f"{group}_ground_truth_7_samples.json"
        )
        schema = load_json(ROOT / schema_relative)
        validator = Draft202012Validator(schema)
        definition = next(
            template
            for template in service.list_templates()
            if template["templateId"] == expected_template
        )
        required_fields = tuple(str(value) for value in definition["requiredFields"])
        for record in records:
            filename = Path(str(record["sourceFile"])).name
            payload = (args.data_root / folder / filename).read_bytes()
            result = service.process(
                DocumentSource(
                    document_id=str(record["documentId"]),
                    filename=filename,
                    content=payload,
                    declared_media_type=(
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    source_reference=str(record["documentId"]),
                )
            )
            data = result.data
            document_count += 1
            if (
                result.detection.definition.document_type.value == expected_type
                and result.detection.definition.template_id == expected_template
            ):
                classification_correct += 1
            if result.validation.recommended_action.value == "AUTO_CONTINUE":
                auto_continue_count += 1
            errors = tuple(validator.iter_errors(data))
            schema_error_count += len(errors)
            for field_name in required_fields:
                required_total += 1
                if data.get(field_name) == record.get(field_name):
                    required_exact += 1
                else:
                    mismatch_fields[field_name] += 1
            for field_name, expected_value in record.items():
                if field_name in IGNORED_COMPARISON_FIELDS:
                    continue
                all_field_total += 1
                if data.get(field_name) == expected_value:
                    all_field_exact += 1
                else:
                    mismatch_fields[field_name] += 1

    report = {
        "schemaVersion": "template-first-phase1-evaluation/1.0.0",
        "documentCount": document_count,
        "classification": {
            "correct": classification_correct,
            "accuracy": _rate(classification_correct, document_count),
        },
        "requiredFieldExactMatch": {
            "correct": required_exact,
            "total": required_total,
            "rate": _rate(required_exact, required_total),
        },
        "allLabeledFieldExactMatch": {
            "correct": all_field_exact,
            "total": all_field_total,
            "rate": _rate(all_field_exact, all_field_total),
        },
        "schemaErrorCount": schema_error_count,
        "autoContinueCount": auto_continue_count,
        "mismatchFields": dict(sorted(mismatch_fields.items())),
        "containsRawFieldValues": False,
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    passed = (
        document_count == 14
        and classification_correct == document_count
        and required_exact == required_total
        and schema_error_count == 0
    )
    return 0 if passed else 1


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
