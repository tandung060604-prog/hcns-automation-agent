"""Build a typed, source-preserving projection from a sealed HR Ground Truth.

The projection is a local/private working artifact for DATA-09.  It never
changes the sealed Ground Truth and it does not read model predictions.  Every
field keeps its reviewed source value alongside a typed canonical value so a
normalization mistake can be sent back to human review without losing the
original evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from hcns_agent.application.external_dataset import ExternalDatasetError

OUT_OF_SCOPE_REVIEW_FORMATS: dict[str, frozenset[str]] = {
    "cv": frozenset({"PLAIN_TEXT", "PPTX"}),
}

FIELD_SPECS: dict[str, dict[str, dict[str, object]]] = {
    "contract": {
        "contract_number": {"dataType": "string"},
        "contract_sign_date": {"dataType": "date"},
        "effective_date": {"dataType": "date"},
        "probation_end_date": {"dataType": "date"},
        "employer_name": {"dataType": "string"},
        "employer_representative": {"dataType": "string"},
        "employee_name": {"dataType": "string"},
        "employee_id_number": {"dataType": "string"},
        "job_title": {"dataType": "string"},
        "workplace": {"dataType": "string"},
        "weekly_hours": {"dataType": "number", "unit": "hours_per_week"},
        "probation_salary_monthly": {
            "dataType": "integer",
            "unit": "VND",
            "currency": "VND",
        },
        "allowances_summary": {"dataType": "string", "completeness": "PARTIAL"},
        "salary_payment_schedule": {"dataType": "string", "completeness": "PARTIAL"},
    },
    "cv": {
        "full_name": {"dataType": "string"},
        "headline": {"dataType": "string"},
        "email": {"dataType": "string"},
        "phone_number": {"dataType": "string"},
        "address": {"dataType": "string"},
        "desired_role": {"dataType": "string"},
        "years_experience": {"dataType": "number", "unit": "years"},
        "experience": {"dataType": "string", "completeness": "PARTIAL"},
        "skills": {"dataType": "string", "completeness": "PARTIAL"},
        "education": {"dataType": "string", "completeness": "PARTIAL"},
    },
    "ielts": {
        "recipient_name": {
            "dataType": "string",
            "semantic": "family_name_plus_first_name",
        },
        "credential_id": {"dataType": "string"},
        "credential_type": {"dataType": "string"},
        "overall_score": {
            "dataType": "number",
            "unit": "IELTS_BAND",
            "scale": "IELTS_BAND",
            "minimum": 0,
            "maximum": 9,
            "step": 0.5,
        },
        "issue_date": {"dataType": "date"},
    },
}

# Long narrative fields are useful even when the reviewer cannot recover the
# whole paragraph.  Keep their source text, but let DATA-09 mark a non-empty
# value as partial instead of failing the typed projection.
PARTIAL_TEXT_FIELDS: dict[str, frozenset[str]] = {
    "contract": frozenset({"allowances_summary", "salary_payment_schedule"}),
    "cv": frozenset({"experience", "skills", "education"}),
    "ielts": frozenset(),
}


class TypedNormalizationError(ValueError):
    """Raised when a reviewed source value cannot be typed safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--seal-marker", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def build_typed_projection(
    ground_truth: dict[str, object],
    inventory: dict[str, object],
    seal_marker: dict[str, object],
    *,
    ground_truth_sha256: str,
) -> dict[str, object]:
    """Validate the seal and return the source-preserving typed projection."""

    _validate_seal(ground_truth, inventory, seal_marker, ground_truth_sha256)
    inventory_cases = _objects(inventory, "cases")
    inventory_by_id = {str(case["caseId"]): case for case in inventory_cases}
    ground_truth_cases = _objects(ground_truth, "cases")
    if set(inventory_by_id) != {str(case.get("caseId")) for case in ground_truth_cases}:
        raise ExternalDatasetError("Ground Truth and inventory case IDs do not match")

    documents: list[dict[str, object]] = []
    for ground_truth_case in sorted(ground_truth_cases, key=lambda item: str(item["caseId"])):
        case_id = _string(ground_truth_case, "caseId")
        inventory_case = inventory_by_id[case_id]
        category = _string(inventory_case, "category")
        source_format = _string(inventory_case, "sourceFormat")
        expected_type = _string(inventory_case, "documentType")
        if _string(ground_truth_case, "documentType") != expected_type:
            raise ExternalDatasetError(f"Document type drift: {case_id}")
        try:
            field_specs = FIELD_SPECS[category]
        except KeyError as error:
            raise ExternalDatasetError(f"Unsupported typed category: {category}") from error
        fields = _objects(ground_truth_case, "fields")
        field_by_name = {str(field.get("name")): field for field in fields}
        if set(field_by_name) != set(field_specs):
            raise ExternalDatasetError(f"Field contract drift: {case_id}")

        scope_status = (
            "OUT_OF_SCOPE"
            if source_format in OUT_OF_SCOPE_REVIEW_FORMATS.get(category, frozenset())
            else "ACTIVE"
        )
        if scope_status == "ACTIVE":
            pending = [
                name
                for name, field in field_by_name.items()
                if field.get("reviewStatus") != "CONFIRMED"
            ]
            if pending:
                raise ExternalDatasetError(
                    f"Active case has unconfirmed fields: {case_id} ({len(pending)})"
                )

        typed_fields = [
            _typed_field(
                name,
                field_by_name[name].get("value"),
                field_specs[name],
                scope_status,
                str(field_by_name[name].get("reviewStatus")),
            )
            for name in field_specs
        ]
        documents.append(
            {
                "caseId": case_id,
                "category": category,
                "documentType": expected_type,
                "sourceFormat": source_format,
                "pageCount": _integer(inventory_case, "pageCount"),
                "scopeStatus": scope_status,
                "fields": typed_fields,
            }
        )

    dataset = _object(ground_truth, "dataset")
    return {
        "schemaVersion": "1.0.0",
        "dataset": {
            "datasetId": _string(dataset, "datasetId"),
            "version": _string(dataset, "version"),
            "contentDigest": _string(dataset, "contentDigest"),
            "groundTruthSha256": ground_truth_sha256,
            "groundTruthStatus": "SEALED",
        },
        "sourcePolicy": {
            "localOnly": True,
            "sourceValuesPreserved": True,
            "predictionsOpened": False,
            "predictionBlind": True,
            "completenessPolicy": {
                "mode": "FIELD_LEVEL",
                "partialTextFields": {
                    category: sorted(fields) for category, fields in PARTIAL_TEXT_FIELDS.items()
                },
                "partialGate": "NON_EMPTY_TEXT",
                "emptyValuesRemainMissing": True,
            },
        },
        "documents": documents,
    }


def main() -> int:
    args = parse_args()
    if args.output.exists() and not args.overwrite:
        raise SystemExit("Typed projection exists; pass --overwrite")
    try:
        ground_truth = _read_object(args.ground_truth)
        inventory = _read_object(args.inventory)
        seal_path = args.seal_marker or _default_seal_path(args.ground_truth)
        seal_marker = _read_object(seal_path)
        ground_truth_sha256 = _sha256_file(args.ground_truth)
        projection = build_typed_projection(
            ground_truth,
            inventory,
            seal_marker,
            ground_truth_sha256=ground_truth_sha256,
        )
    except (OSError, ExternalDatasetError, TypedNormalizationError) as error:
        raise SystemExit(f"Typed projection rejected: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    active_documents = sum(
        document["scopeStatus"] == "ACTIVE" for document in projection["documents"]
    )
    active_fields = sum(
        len(document["fields"])
        for document in projection["documents"]
        if document["scopeStatus"] == "ACTIVE"
    )
    print(
        f"Typed projection complete: activeDocuments={active_documents} "
        f"activeFields={active_fields} predictionsOpened=false"
    )
    print(f"Private typed projection written outside repository: {args.output.resolve()}")
    return 0


def _typed_field(
    name: str,
    source_value: object,
    spec: dict[str, object],
    scope_status: str,
    review_status: str,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "name": name,
        "reviewStatus": review_status,
        "sourceValue": source_value,
        "dataType": spec["dataType"],
        "completenessStatus": "NOT_APPLICABLE",
    }
    for key in ("unit", "currency", "semantic", "scale", "minimum", "maximum", "step"):
        if key in spec:
            entry[key] = spec[key]
    if scope_status != "ACTIVE":
        entry.update(normalizedValue=None, normalizationStatus="OUT_OF_SCOPE")
        return entry
    if source_value is None or (isinstance(source_value, str) and not source_value.strip()):
        entry.update(
            normalizedValue=None,
            normalizationStatus="MISSING",
            completenessStatus="MISSING",
        )
        return entry
    try:
        normalized = _normalize_value(str(spec["dataType"]), source_value, name)
    except TypedNormalizationError as error:
        entry.update(
            normalizedValue=None,
            normalizationStatus="NEEDS_REVIEW",
            normalizationReason=str(error),
        )
        return entry
    entry.update(
        normalizedValue=normalized,
        normalizationStatus="NORMALIZED",
        completenessStatus="PARTIAL" if spec.get("completeness") == "PARTIAL" else "FULL",
    )
    return entry


def _normalize_value(data_type: str, source_value: object, field_name: str) -> object:
    if data_type == "string":
        return str(source_value).strip()
    if data_type == "date":
        return _parse_date(str(source_value), field_name)
    if data_type == "number":
        value = _parse_number(str(source_value), field_name)
        if field_name == "overall_score" and not _is_ielts_step(value):
            raise TypedNormalizationError("IELTS overall score must use 0.5 increments")
        if field_name == "overall_score" and not 0 <= value <= 9:
            raise TypedNormalizationError("IELTS overall score must be between 0 and 9")
        return _json_number(value)
    if data_type == "integer":
        return _parse_salary(source_value, field_name)
    raise TypedNormalizationError(f"Unsupported data type: {data_type}")


def _parse_date(value: str, field_name: str) -> str:
    text = value.strip()
    if not text:
        raise TypedNormalizationError(f"{field_name} is empty")
    iso_match = re.search(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", text)
    if iso_match:
        return _valid_date(
            int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)), field_name
        )
    slash_match = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)", text)
    if slash_match:
        return _valid_date(
            int(slash_match.group(3)),
            int(slash_match.group(2)),
            int(slash_match.group(1)),
            field_name,
        )
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    year_index = next((index for index, item in enumerate(numbers) if 1900 <= item <= 2100), None)
    if year_index is not None and len(numbers) >= 3:
        day_month = [item for index, item in enumerate(numbers) if index != year_index][:2]
        if len(day_month) == 2:
            return _valid_date(numbers[year_index], day_month[1], day_month[0], field_name)
    raise TypedNormalizationError(f"{field_name} is not a supported calendar date")


def _parse_number(value: str, field_name: str) -> Decimal:
    text = value.strip().casefold()
    match = re.search(r"(?<!\w)(\d+(?:[.,]\d+)*)(?!\w)", text)
    if not match:
        raise TypedNormalizationError(f"{field_name} has no numeric value")
    number = _decimal_token(match.group(1))
    if field_name == "years_experience":
        month_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:tháng|month)", text)
        if month_match and ("năm" in text or "year" in text):
            number += _decimal_token(month_match.group(1)) / Decimal(12)
    if number < 0:
        raise TypedNormalizationError(f"{field_name} cannot be negative")
    return number


def _parse_salary(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise TypedNormalizationError(f"{field_name} is not numeric")
    if isinstance(value, int):
        if value < 0:
            raise TypedNormalizationError(f"{field_name} cannot be negative")
        return value
    text = str(value).strip().casefold()
    match = re.search(r"(?<!\w)(\d+(?:[.,]\d+)*)(?!\w)", text)
    if not match:
        raise TypedNormalizationError(f"{field_name} has no numeric value")
    token = match.group(1)
    if any(unit in text for unit in ("triệu", "trieu", "million")):
        amount = _decimal_token(token) * Decimal(1_000_000)
    elif any(unit in text for unit in ("nghìn", "ngàn", "nghin", "thousand")):
        amount = _decimal_token(token) * Decimal(1_000)
    else:
        digits = re.sub(r"\D", "", token)
        if not digits:
            raise TypedNormalizationError(f"{field_name} has no integer value")
        amount = Decimal(digits)
    if amount < 0 or amount != amount.to_integral_value():
        raise TypedNormalizationError(f"{field_name} is not a whole currency amount")
    return int(amount)


def _decimal_token(token: str) -> Decimal:
    token = token.replace(" ", "")
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        pieces = token.split(",")
        token = "".join(pieces) if len(pieces[-1]) == 3 else ".".join(pieces)
    elif token.count(".") > 1 or "." in token and len(token.rsplit(".", 1)[1]) == 3:
        token = token.replace(".", "")
    try:
        return Decimal(token)
    except InvalidOperation as error:
        raise TypedNormalizationError("invalid decimal token") from error


def _is_ielts_step(value: Decimal) -> bool:
    doubled = value * Decimal(2)
    return doubled == doubled.to_integral_value()


def _json_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _valid_date(year: int, month: int, day: int, field_name: str) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError as error:
        raise TypedNormalizationError(f"{field_name} is not a valid calendar date") from error


def _validate_seal(
    ground_truth: dict[str, object],
    inventory: dict[str, object],
    marker: dict[str, object],
    ground_truth_sha256: str,
) -> None:
    dataset = _object(ground_truth, "dataset")
    inventory_dataset = _object(inventory, "dataset")
    review = _object(ground_truth, "review")
    if dataset.get("groundTruthStatus") != "SEALED":
        raise ExternalDatasetError("Ground Truth must be SEALED")
    if review.get("status") != "CONFIRMED" or review.get("predictionBlindness") is not True:
        raise ExternalDatasetError("Ground Truth review is not confirmed and prediction-blind")
    for key in ("datasetId", "version", "contentDigest"):
        if dataset.get(key) != inventory_dataset.get(key):
            raise ExternalDatasetError(f"Ground Truth/inventory {key} mismatch")
    if marker.get("predictionsOpened") is not False:
        raise ExternalDatasetError("Seal marker says predictions were opened")
    if marker.get("groundTruthSha256") != ground_truth_sha256:
        raise ExternalDatasetError("Seal marker does not match Ground Truth SHA-256")
    if marker.get("datasetId") != dataset.get("datasetId"):
        raise ExternalDatasetError("Seal marker datasetId mismatch")
    if marker.get("contentDigest") != dataset.get("contentDigest"):
        raise ExternalDatasetError("Seal marker contentDigest mismatch")


def _default_seal_path(ground_truth: Path) -> Path:
    return ground_truth.with_name(f"{ground_truth.stem}-SEALED{ground_truth.suffix}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ExternalDatasetError(f"{path.name} must contain a JSON object")
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
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExternalDatasetError(f"{key} must be an integer")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
