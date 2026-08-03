"""Run the DATA-09 post-seal aggregate-only normalization pilot.

The input projection contains source values and is therefore local/private. The
report emitted by this script contains counts only: no field value, source path,
OCR text, prediction or document identifier is copied to the report.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from hcns_agent.application.external_dataset import ExternalDatasetError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def build_aggregate_report(projection: dict[str, object]) -> dict[str, object]:
    _validate_projection(projection)
    documents = _objects(projection, "documents")
    active_documents = [
        document for document in documents if document.get("scopeStatus") == "ACTIVE"
    ]
    status_counts: Counter[str] = Counter()
    data_type_counts: Counter[str] = Counter()
    category_counts: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "documentCount": 0,
            "fieldCount": 0,
            "normalizationStatusCounts": Counter(),
            "dataTypeCounts": Counter(),
        }
    )
    for document in active_documents:
        category = _string(document, "category")
        category_counts[category]["documentCount"] += 1
        fields = _objects(document, "fields")
        category_counts[category]["fieldCount"] += len(fields)
        for field in fields:
            status = _string(field, "normalizationStatus")
            data_type = _string(field, "dataType")
            status_counts[status] += 1
            data_type_counts[data_type] += 1
            category_counts[category]["normalizationStatusCounts"][status] += 1
            category_counts[category]["dataTypeCounts"][data_type] += 1

    normalized_count = status_counts.get("NORMALIZED", 0)
    missing_count = status_counts.get("MISSING", 0)
    needs_review_count = status_counts.get("NEEDS_REVIEW", 0)
    return {
        "schemaVersion": "1.0.0",
        "pilot": "DATA-09",
        "dataset": _object(projection, "dataset"),
        "scope": {
            "inventoryDocumentCount": len(documents),
            "activeDocumentCount": len(active_documents),
            "outOfScopeDocumentCount": len(documents) - len(active_documents),
            "activeFieldCount": sum(
                len(_objects(document, "fields")) for document in active_documents
            ),
        },
        "normalization": {
            "statusCounts": dict(sorted(status_counts.items())),
            "dataTypeCounts": dict(sorted(data_type_counts.items())),
            "normalizedFieldCount": normalized_count,
            "missingFieldCount": missing_count,
            "needsReviewFieldCount": needs_review_count,
            "byCategory": {
                category: {
                    "documentCount": int(values["documentCount"]),
                    "fieldCount": int(values["fieldCount"]),
                    "normalizationStatusCounts": dict(
                        sorted(values["normalizationStatusCounts"].items())
                    ),
                    "dataTypeCounts": dict(sorted(values["dataTypeCounts"].items())),
                }
                for category, values in sorted(category_counts.items())
            },
        },
        "reportPolicy": {
            "aggregateOnly": True,
            "containsRawFieldValues": False,
            "containsRawOcrText": False,
            "containsPredictions": False,
            "predictionsOpened": False,
            "promotionAllowed": False,
        },
        "promotionDecision": {
            "status": "HOLD",
            "reasons": [
                "DATA-09 is an aggregate-only typed normalization pilot",
                "predictions remain unopened",
                "typed normalization does not approve model or dataset promotion",
            ],
        },
    }


def main() -> int:
    args = parse_args()
    if args.output.exists() and not args.overwrite:
        raise SystemExit("Aggregate pilot report exists; pass --overwrite")
    try:
        projection = _read_object(args.projection)
        report = build_aggregate_report(projection)
    except (OSError, ExternalDatasetError) as error:
        raise SystemExit(f"Aggregate pilot rejected: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "Aggregate-only pilot complete: "
        f"activeDocuments={report['scope']['activeDocumentCount']} "
        f"activeFields={report['scope']['activeFieldCount']} decision=HOLD"
    )
    print(f"Aggregate report written outside repository: {args.output.resolve()}")
    return 0


def _validate_projection(projection: dict[str, object]) -> None:
    if projection.get("schemaVersion") != "1.0.0":
        raise ExternalDatasetError("Unsupported typed projection schema")
    dataset = _object(projection, "dataset")
    if dataset.get("groundTruthStatus") != "SEALED":
        raise ExternalDatasetError("Aggregate pilot requires SEALED Ground Truth")
    policy = _object(projection, "sourcePolicy")
    if policy.get("predictionsOpened") is not False or policy.get("predictionBlind") is not True:
        raise ExternalDatasetError("Projection is not prediction-blind")
    if policy.get("sourceValuesPreserved") is not True or policy.get("localOnly") is not True:
        raise ExternalDatasetError("Projection source policy is incomplete")
    documents = _objects(projection, "documents")
    if not documents:
        raise ExternalDatasetError("Projection contains no documents")
    for document in documents:
        if document.get("scopeStatus") not in {"ACTIVE", "OUT_OF_SCOPE"}:
            raise ExternalDatasetError("Unsupported document scope status")
        _objects(document, "fields")
        if document.get("scopeStatus") == "OUT_OF_SCOPE" and any(
            field.get("normalizationStatus") != "OUT_OF_SCOPE"
            for field in _objects(document, "fields")
        ):
            raise ExternalDatasetError("Out-of-scope fields must not be normalized")


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


if __name__ == "__main__":
    raise SystemExit(main())
