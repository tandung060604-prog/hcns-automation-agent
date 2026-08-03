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
        ("contract_sign_date", False),
        ("effective_date", False),
        ("probation_end_date", False),
        ("employer_name", False),
        ("employer_representative", False),
        ("employee_name", True),
        ("employee_id_number", True),
        ("job_title", False),
        ("workplace", False),
        ("weekly_hours", False),
        ("probation_salary_monthly", True),
        ("allowances_summary", False),
        ("salary_payment_schedule", False),
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
    parser.add_argument(
        "--preserve-from",
        type=Path,
        help="Previous local draft whose non-contract review fields must be preserved.",
    )
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
        if args.preserve_from is not None:
            draft = preserve_non_contract_reviews(draft, _read_object(args.preserve_from))
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


def preserve_non_contract_reviews(
    draft: dict[str, object], previous: dict[str, object]
) -> dict[str, object]:
    """Carry forward CV/IELTS review state while replacing contract cases."""
    previous_cases = {
        str(case.get("caseId")): case
        for case in _objects(previous, "cases")
        if str(case.get("caseId", "")).split("-", 1)[0] != "contract"
    }
    for case in _objects(draft, "cases"):
        case_id = _string(case, "caseId")
        if case_id.split("-", 1)[0] == "contract":
            continue
        prior = previous_cases.get(case_id)
        if prior is None:
            continue
        prior_fields = prior.get("fields")
        if isinstance(prior_fields, list):
            case["fields"] = prior_fields
        for key in ("reviewRequired", "reviewedAt", "reviewer"):
            if key in prior:
                case[key] = prior[key]
    prior_review = previous.get("review")
    if isinstance(prior_review, dict):
        current_review = _object(draft, "review")
        for key in ("reviewer", "reviewedAt", "evidenceReference", "predictionBlindness"):
            if key in prior_review:
                current_review[key] = prior_review[key]
        current_review["status"] = (
            "CONFIRMED"
            if all(
                all(
                    str(field.get("reviewStatus")) == "CONFIRMED"
                    for field in case.get("fields", [])
                )
                for case in _objects(draft, "cases")
            )
            else "IN_PROGRESS"
        )
    return draft


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
