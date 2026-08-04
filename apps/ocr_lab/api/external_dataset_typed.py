"""Read-only DATA-11 access to the approved typed external-dataset projection.

This module deliberately has no write path.  It validates the projection,
approval marker and aggregate report as one immutable bundle before serving any
summary, document detail or export response.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from external_dataset_review import FIELD_SPECS

CASE_ID_RE = re.compile(r"^(?:cv|contract|ielts)-\d{3}$")
PROJECTION_SCHEMA_VERSION = "1.0.0"
APPROVAL_SCHEMA_VERSION = "external-dataset-typed-approval/1.0.0"
EXPORT_SCHEMA_VERSION = "external-dataset-typed-export/1.0.0"
SUPPORTED_DATA_TYPES = frozenset({"string", "number", "integer", "date"})
SUPPORTED_STATUSES = frozenset({"NORMALIZED", "MISSING", "NEEDS_REVIEW", "OUT_OF_SCOPE"})
SUPPORTED_COMPLETENESS = frozenset({"FULL", "PARTIAL", "MISSING", "NOT_APPLICABLE"})


class TypedDatasetError(ValueError):
    """Raised when the approved typed artifact bundle is unavailable or drifts."""


@dataclass(frozen=True)
class TypedDatasetPaths:
    projection: Path
    approval: Path
    aggregate_report: Path


def resolve_typed_paths(
    root: Path,
    *,
    projection_path: Path | None = None,
    approval_path: Path | None = None,
    aggregate_report_path: Path | None = None,
) -> TypedDatasetPaths:
    root = root.expanduser().resolve()
    stem = root.name
    return TypedDatasetPaths(
        projection=(
            projection_path.expanduser().resolve()
            if projection_path is not None
            else root.parent / f"{stem}-typed-canonical.json"
        ),
        approval=(
            approval_path.expanduser().resolve()
            if approval_path is not None
            else root.parent / f"{stem}-typed-canonical-APPROVED.json"
        ),
        aggregate_report=(
            aggregate_report_path.expanduser().resolve()
            if aggregate_report_path is not None
            else root.parent / f"{stem}-data09-aggregate-pilot.json"
        ),
    )


def load_typed_artifacts(paths: TypedDatasetPaths) -> dict[str, Any]:
    projection = _read_object(paths.projection)
    approval = _read_object(paths.approval)
    report = _read_object(paths.aggregate_report)
    _validate_projection(projection)
    _validate_approval(projection, approval, report, paths)
    _validate_report(projection, report)
    return {"projection": projection, "approval": approval, "report": report}


def load_typed_summary(paths: TypedDatasetPaths) -> dict[str, Any]:
    artifacts = load_typed_artifacts(paths)
    projection = artifacts["projection"]
    approval = artifacts["approval"]
    report = artifacts["report"]
    documents = [
        _document_summary(document)
        for document in projection["documents"]
        if document["scopeStatus"] == "ACTIVE"
    ]
    return {
        "schemaVersion": "external-dataset-typed-summary/1.0.0",
        "dataset": _public_dataset(projection["dataset"]),
        "approval": {
            "status": approval["approvalStatus"],
            "approvedBy": approval["approvedBy"],
            "approvedAt": approval["approvedAt"],
            "readOnly": True,
            "predictionsOpened": False,
            "promotionAllowed": False,
        },
        "scope": report["scope"],
        "normalization": report["normalization"],
        "documents": documents,
        "policy": {
            "localOnly": True,
            "readOnly": True,
            "containsRawFieldValues": False,
            "containsPredictions": False,
            "promotionAllowed": False,
        },
    }


def load_typed_document(
    paths: TypedDatasetPaths,
    case_id: str,
    *,
    include_source_value: bool = False,
) -> dict[str, Any]:
    if not CASE_ID_RE.fullmatch(case_id):
        raise TypedDatasetError("Invalid typed dataset case id")
    artifacts = load_typed_artifacts(paths)
    document = next(
        (
            item
            for item in artifacts["projection"]["documents"]
            if item.get("caseId") == case_id
        ),
        None,
    )
    if document is None:
        raise FileNotFoundError("Typed dataset case not found")
    if document["scopeStatus"] != "ACTIVE":
        raise TypedDatasetError("Typed dataset case is outside active scope")
    fields = [_public_field(field, include_source_value) for field in document["fields"]]
    return {
        "schemaVersion": "external-dataset-typed-document/1.0.0",
        "caseId": document["caseId"],
        "category": document["category"],
        "documentType": document["documentType"],
        "sourceFormat": document["sourceFormat"],
        "pageCount": document["pageCount"],
        "scopeStatus": "ACTIVE",
        "fields": fields,
        "policy": {
            "localOnly": True,
            "readOnly": True,
            "containsRawFieldValues": include_source_value,
            "containsPredictions": False,
            "predictionsOpened": False,
            "promotionAllowed": False,
        },
    }


def build_typed_export(paths: TypedDatasetPaths, format_name: str) -> tuple[bytes, str, str]:
    artifacts = load_typed_artifacts(paths)
    projection = artifacts["projection"]
    active_documents = [
        document
        for document in projection["documents"]
        if document["scopeStatus"] == "ACTIVE"
    ]
    if format_name == "json":
        payload = {
            "schemaVersion": EXPORT_SCHEMA_VERSION,
            "dataset": _public_dataset(projection["dataset"]),
            "approvalStatus": artifacts["approval"]["approvalStatus"],
            "readOnly": True,
            "containsSourceValues": False,
            "containsPredictions": False,
            "documents": [
                {
                    "caseId": document["caseId"],
                    "category": document["category"],
                    "documentType": document["documentType"],
                    "sourceFormat": document["sourceFormat"],
                    "pageCount": document["pageCount"],
                    "fields": [_public_field(field, False) for field in document["fields"]],
                }
                for document in active_documents
            ],
        }
        return (
            (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
            "application/json; charset=utf-8",
            "external-dataset-typed-export.json",
        )
    if format_name == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            [
                "caseId",
                "category",
                "documentType",
                "sourceFormat",
                "pageCount",
                "fieldName",
                "dataType",
                "normalizedValue",
                "unit",
                "currency",
                "normalizationStatus",
                "completenessStatus",
            ]
        )
        for document in active_documents:
            for field in document["fields"]:
                writer.writerow(
                    [
                        document["caseId"],
                        document["category"],
                        document["documentType"],
                        document["sourceFormat"],
                        document["pageCount"],
                        field["name"],
                        field["dataType"],
                        "" if field["normalizedValue"] is None else field["normalizedValue"],
                        field.get("unit", ""),
                        field.get("currency", ""),
                        field["normalizationStatus"],
                        field.get("completenessStatus", ""),
                    ]
                )
        return (
            stream.getvalue().encode("utf-8"),
            "text/csv; charset=utf-8",
            "external-dataset-typed-export.csv",
        )
    raise TypedDatasetError("Export format must be json or csv")


def _document_summary(document: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    completeness_counts: dict[str, int] = {}
    for field in document["fields"]:
        status = str(field["normalizationStatus"])
        counts[status] = counts.get(status, 0) + 1
        completeness = field.get("completenessStatus")
        if completeness is not None:
            completeness_counts[completeness] = completeness_counts.get(completeness, 0) + 1
    result = {
        "caseId": document["caseId"],
        "category": document["category"],
        "documentType": document["documentType"],
        "sourceFormat": document["sourceFormat"],
        "pageCount": document["pageCount"],
        "scopeStatus": document["scopeStatus"],
        "fieldCount": len(document["fields"]),
        "normalizationStatusCounts": dict(sorted(counts.items())),
    }
    if completeness_counts:
        result["completenessStatusCounts"] = dict(sorted(completeness_counts.items()))
    return result


def _public_field(field: dict[str, Any], include_source_value: bool) -> dict[str, Any]:
    output = {
        key: value
        for key, value in field.items()
        if key not in {"sourceValue", "reviewStatus"}
    }
    if include_source_value:
        output["sourceValue"] = field.get("sourceValue")
    return output


def _public_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "datasetId": dataset["datasetId"],
        "version": dataset["version"],
        "contentDigest": dataset["contentDigest"],
        "groundTruthStatus": dataset["groundTruthStatus"],
    }


def _validate_projection(projection: dict[str, Any]) -> None:
    if projection.get("schemaVersion") != PROJECTION_SCHEMA_VERSION:
        raise TypedDatasetError("Unsupported typed projection schema")
    dataset = _object(projection, "dataset")
    for key in ("datasetId", "version", "contentDigest", "groundTruthSha256"):
        _non_empty_string(dataset, key)
    if dataset.get("groundTruthStatus") != "SEALED":
        raise TypedDatasetError("Typed projection requires SEALED Ground Truth")
    policy = _object(projection, "sourcePolicy")
    if any(
        policy.get(key) is not expected
        for key, expected in (
            ("localOnly", True),
            ("sourceValuesPreserved", True),
            ("predictionsOpened", False),
            ("predictionBlind", True),
        )
    ):
        raise TypedDatasetError("Typed projection source policy is unsafe")
    completeness_policy = policy.get("completenessPolicy")
    if completeness_policy is not None and (
        not isinstance(completeness_policy, dict)
        or any(
            completeness_policy.get(key) != expected
            for key, expected in (
                ("mode", "FIELD_LEVEL"),
                ("partialGate", "NON_EMPTY_TEXT"),
                ("emptyValuesRemainMissing", True),
            )
        )
    ):
        raise TypedDatasetError("Typed completeness policy is unsafe")
    documents = _objects(projection, "documents")
    if not documents:
        raise TypedDatasetError("Typed projection has no documents")
    seen: set[str] = set()
    for document in documents:
        case_id = _non_empty_string(document, "caseId")
        if not CASE_ID_RE.fullmatch(case_id) or case_id in seen:
            raise TypedDatasetError("Typed projection case identity is invalid")
        seen.add(case_id)
        category = _non_empty_string(document, "category")
        if category not in FIELD_SPECS:
            raise TypedDatasetError("Typed projection category is invalid")
        _non_empty_string(document, "documentType")
        _non_empty_string(document, "sourceFormat")
        if not isinstance(document.get("pageCount"), int) or document["pageCount"] < 1:
            raise TypedDatasetError("Typed projection pageCount is invalid")
        scope = document.get("scopeStatus")
        if scope not in {"ACTIVE", "OUT_OF_SCOPE"}:
            raise TypedDatasetError("Typed projection scopeStatus is invalid")
        fields = _objects(document, "fields")
        expected_names = tuple(FIELD_SPECS[category])
        names = tuple(str(field.get("name")) for field in fields)
        if names != expected_names:
            raise TypedDatasetError(f"Typed field contract mismatch for {case_id}")
        for field in fields:
            _validate_field(field, scope)


def _validate_field(field: dict[str, Any], scope: str) -> None:
    _non_empty_string(field, "name")
    if field.get("dataType") not in SUPPORTED_DATA_TYPES:
        raise TypedDatasetError("Typed field dataType is invalid")
    if field.get("normalizationStatus") not in SUPPORTED_STATUSES:
        raise TypedDatasetError("Typed field normalizationStatus is invalid")
    if (
        "completenessStatus" in field
        and field.get("completenessStatus") not in SUPPORTED_COMPLETENESS
    ):
        raise TypedDatasetError("Typed field completenessStatus is invalid")
    if field.get("reviewStatus") not in {"PENDING", "CONFIRMED"}:
        raise TypedDatasetError("Typed field reviewStatus is invalid")
    if scope == "OUT_OF_SCOPE" and field.get("normalizationStatus") != "OUT_OF_SCOPE":
        raise TypedDatasetError("Out-of-scope field was normalized")


def _validate_approval(
    projection: dict[str, Any],
    approval: dict[str, Any],
    report: dict[str, Any],
    paths: TypedDatasetPaths,
) -> None:
    if approval.get("schemaVersion") != APPROVAL_SCHEMA_VERSION:
        raise TypedDatasetError("Unsupported typed approval marker")
    if approval.get("approvalStatus") != "APPROVED":
        raise TypedDatasetError("Typed projection is not approved")
    _non_empty_string(approval, "approvedBy")
    _non_empty_string(approval, "approvedAt")
    if approval.get("predictionsOpened") is not False:
        raise TypedDatasetError("Approval marker says predictions were opened")
    if approval.get("promotionAllowed") is not False:
        raise TypedDatasetError("Approval marker enables promotion")
    marker_dataset = _object(approval, "dataset")
    if marker_dataset != projection["dataset"]:
        raise TypedDatasetError("Approval marker dataset metadata drifted")
    if approval.get("typedProjectionSha256") != _sha256(paths.projection):
        raise TypedDatasetError("Typed projection SHA-256 drifted")
    if approval.get("aggregateReportSha256") != _sha256(paths.aggregate_report):
        raise TypedDatasetError("Aggregate report SHA-256 drifted")
    if report.get("reportPolicy", {}).get("predictionsOpened") is not False:
        raise TypedDatasetError("Aggregate report is not prediction-blind")


def _validate_report(projection: dict[str, Any], report: dict[str, Any]) -> None:
    if report.get("schemaVersion") != "1.0.0" or report.get("pilot") != "DATA-09":
        raise TypedDatasetError("Unsupported DATA-09 aggregate report")
    report_dataset = _object(report, "dataset")
    if report_dataset != projection["dataset"]:
        raise TypedDatasetError("Aggregate report dataset metadata drifted")
    policy = _object(report, "reportPolicy")
    if any(
        policy.get(key) is not expected
        for key, expected in (
            ("aggregateOnly", True),
            ("containsRawFieldValues", False),
            ("containsRawOcrText", False),
            ("containsPredictions", False),
            ("predictionsOpened", False),
            ("promotionAllowed", False),
        )
    ):
        raise TypedDatasetError("Aggregate report policy is unsafe")
    active_documents = [
        document for document in projection["documents"] if document["scopeStatus"] == "ACTIVE"
    ]
    active_fields = sum(len(document["fields"]) for document in active_documents)
    status_counts: dict[str, int] = {}
    completeness_counts: dict[str, int] = {}
    for document in active_documents:
        for field in document["fields"]:
            status = str(field["normalizationStatus"])
            status_counts[status] = status_counts.get(status, 0) + 1
            completeness = field.get("completenessStatus")
            if completeness is not None:
                completeness_counts[str(completeness)] = completeness_counts.get(
                    str(completeness), 0
                ) + 1
    scope = _object(report, "scope")
    if (
        scope.get("activeDocumentCount") != len(active_documents)
        or scope.get("activeFieldCount") != active_fields
    ):
        raise TypedDatasetError("Aggregate scope counts drifted from projection")
    if _object(report, "normalization").get("statusCounts") != dict(sorted(status_counts.items())):
        raise TypedDatasetError("Aggregate normalization counts drifted from projection")
    reported_completeness = _object(report, "normalization").get("completenessStatusCounts")
    if completeness_counts and reported_completeness is not None and reported_completeness != dict(
        sorted(completeness_counts.items())
    ):
        raise TypedDatasetError("Aggregate completeness counts drifted from projection")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise TypedDatasetError("Typed artifact is unavailable") from error
    return f"sha256:{digest.hexdigest()}"


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TypedDatasetError("Typed artifact JSON is unavailable") from error
    if not isinstance(payload, dict):
        raise TypedDatasetError("Typed artifact root must be an object")
    return payload


def _object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise TypedDatasetError(f"{key} must be an object")
    return value


def _objects(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypedDatasetError(f"{key} must be an object list")
    return value


def _non_empty_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypedDatasetError(f"{key} must be a non-empty string")
    return value
