"""Create a review-ready, prediction-blind Ground Truth draft outside Git.

The draft contains source identities and the expected field contract only. It
never copies OCR output or invents field values. An independent reviewer must
fill values and change review statuses before the artifact can be approved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hcns_agent.adapters.external_dataset import count_source_format_and_pages
from hcns_agent.application.external_dataset import (
    ExternalDatasetError,
    read_inventory,
    validate_inventory,
    validate_mapping,
)

FIELD_SPECS: dict[str, tuple[tuple[str, bool], ...]] = {
    "cv": (
        ("full_name", True),
        ("skills", False),
        ("education", False),
    ),
    "contract": (
        ("contract_number", False),
        ("employee_name", True),
        ("start_date", False),
        ("end_date", False),
        ("salary", True),
    ),
    "ielts": (
        ("recipient_name", True),
        ("credential_id", False),
        ("credential_type", False),
        ("overall_score", False),
        ("issue_date", False),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def build_ground_truth_draft(
    inventory: dict[str, object],
    mapping: dict[str, object],
) -> dict[str, object]:
    validate_mapping(inventory, mapping)
    dataset = _object(inventory, "dataset")
    cases = _objects(inventory, "cases")
    draft_cases: list[dict[str, object]] = []
    for case in sorted(cases, key=lambda item: str(item["caseId"])):
        category = _string(case, "category")
        try:
            field_specs = FIELD_SPECS[category]
        except KeyError as error:
            raise ExternalDatasetError(f"No Ground Truth field contract for {category}") from error
        draft_cases.append(
            {
                "caseId": _string(case, "caseId"),
                "sourceRelativePath": _string(case, "sourceRelativePath"),
                "sourceSha256": _string(case, "sourceSha256"),
                "pageCount": _integer(case, "pageCount"),
                "documentType": _string(case, "documentType"),
                "fields": [
                    {
                        "name": field_name,
                        "value": None,
                        "sensitive": sensitive,
                        "reviewStatus": "PENDING",
                    }
                    for field_name, sensitive in field_specs
                ],
                "expectedQualityStatus": "REVIEW_REQUIRED",
                "reviewRequired": True,
            }
        )
    return {
        "schemaVersion": "1.0.0",
        "dataset": {
            "datasetId": _string(dataset, "datasetId"),
            "version": _string(dataset, "version"),
            "sourceCommit": _string(dataset, "sourceCommit"),
            "contentDigest": _string(dataset, "contentDigest"),
            "documentCount": _integer(dataset, "documentCount"),
            "pageCount": _integer(dataset, "pageCount"),
            "groundTruthStatus": "DRAFT",
        },
        "review": {
            "status": "PENDING",
            "reviewMethod": "SOURCE_DOCUMENT_REVIEW",
            "reviewer": "UNASSIGNED",
            "reviewedAt": None,
            "evidenceReference": "PENDING_INDEPENDENT_REVIEW",
            "predictionBlindness": True,
        },
        "cases": draft_cases,
    }


def main() -> int:
    args = parse_args()
    inventory = read_inventory(args.inventory)
    try:
        validate_inventory(
            args.dataset_root,
            inventory,
            page_counter=count_source_format_and_pages,
        )
        mapping = _read_object(args.mapping)
        draft = build_ground_truth_draft(inventory, mapping)
    except ExternalDatasetError as error:
        raise SystemExit(f"Ground Truth draft rejected: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "Ground Truth draft created: "
        f"cases={len(_objects(draft, 'cases'))} status=DRAFT"
    )
    print(f"Review artifact written outside repository: {args.output.resolve()}")
    return 0


def _read_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExternalDatasetError("Mapping is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ExternalDatasetError("Mapping root must be an object")
    return payload


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ExternalDatasetError(f"{key} must be an object")
    return value


def _objects(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ExternalDatasetError(f"{key} must be an object list")
    return value


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExternalDatasetError(f"{key} must be a non-empty string")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ExternalDatasetError(f"{key} must be an integer")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
