"""Prediction-blind Phase 16 held-out protocol for real HR documents.

The source documents, Ground Truth and predictions are private artifacts. Only
aggregate evaluation output is suitable for disclosure review.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hcns_agent.application.ocr_metrics import (
    METRIC_SPEC_VERSION,
    evaluate_text_pairs,
    normalize_for_evaluation,
)

PROTOCOL_VERSION = "phase17-real-five-family-heldout/2.0.0"
PARSER_VERSION = "phase17-structured-hr-parser/2.0.0"
LOCKED_POLICY_DIGEST = (
    "sha256:5dfd0186cacbe29a299c79d774aa4e2575f67a4675d6db15035762ed9b363fb6"
)

FAMILY_SPECS: dict[str, dict[str, Any]] = {
    "CV": {
        "directory": "01_cv",
        "minimum": 2,
        "fields": ("fullName", "headline", "email", "phoneNumber", "address"),
    },
    "ADMINISTRATIVE_REQUEST": {
        "directory": "02_administrative_request",
        "minimum": 2,
        "fields": (
            "documentTitle",
            "requestNumber",
            "employeeName",
            "employeeId",
            "department",
            "jobTitle",
            "reason",
            "startDate",
            "endDate",
        ),
    },
    "CONTRACT_DECISION": {
        "directory": "03_contract_decision",
        "minimum": 4,
        "fields": (
            "documentNumber",
            "employeeName",
            "employeeId",
            "jobTitle",
            "action",
            "salary",
            "startDate",
            "endDate",
            "effectiveDate",
        ),
    },
    "DEGREE_CERTIFICATE": {
        "directory": "04_degree_certificate",
        "minimum": 4,
        "fields": (
            "recipientName",
            "credentialType",
            "credentialId",
            "issuingOrganization",
            "fieldOfStudy",
            "degreeLevel",
            "classification",
            "issueDate",
        ),
    },
    "EMPLOYEE_FORM_TABLE": {
        "directory": "05_employee_form_table",
        "minimum": 3,
        "fields": (
            "formNumber",
            "employeeName",
            "employeeId",
            "dateOfBirth",
            "gender",
            "department",
            "jobTitle",
            "email",
            "phoneNumber",
            "address",
            "organization",
            "joinDate",
        ),
    },
}

TIMESHEET_REVIEW_PROFILE = "TIMESHEET"
TIMESHEET_FIELDS = (
    "documentTitle",
    "timesheetPeriod",
    "organization",
    "department",
    "attendanceLegend",
)

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"})
SENSITIVE_FIELDS = frozenset(
    {
        "fullName",
        "employeeName",
        "employeeId",
        "dateOfBirth",
        "gender",
        "email",
        "phoneNumber",
        "address",
        "recipientName",
    }
)
CONFIRMED = "CONFIRMED"
SKIPPED = "SKIPPED"
PENDING = "PENDING_REVIEW"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def contains_prediction_or_ground_truth(value: Any) -> bool:
    forbidden = {
        "prediction",
        "predictions",
        "recognizedtext",
        "suggestion",
        "groundtruth",
    }
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = "".join(
                character
                for character in str(key).casefold()
                if character.isalnum()
            )
            if normalized in forbidden or contains_prediction_or_ground_truth(child):
                return True
        return False
    if isinstance(value, list):
        return any(contains_prediction_or_ground_truth(child) for child in value)
    return False


def contains_ground_truth(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            "groundtruth"
            in "".join(
                character
                for character in str(key).casefold()
                if character.isalnum()
            )
            or contains_ground_truth(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(contains_ground_truth(child) for child in value)
    return False


def authorization_template() -> dict[str, Any]:
    return {
        "schemaVersion": "phase17-heldout-authorization/2.0.0",
        "datasetId": "phase17-real-five-family-heldout-v2",
        "containsRealPII": True,
        "authorizedLocalDocumentsOnly": True,
        "processingRightsConfirmed": False,
        "documentOwnerConsentOrLawfulBasisConfirmed": False,
        "rightsBasis": "",
        "reviewerId": "local-reviewer",
    }


def collect_known_hashes(roots: Sequence[Path]) -> set[str]:
    hashes: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else root.rglob("*")
        for candidate in candidates:
            if (
                candidate.is_file()
                and candidate.suffix.casefold() in SUPPORTED_EXTENSIONS
            ):
                hashes.add(sha256_file(candidate))
    return hashes


def audit_sources(
    dataset_root: Path,
    *,
    known_hashes: set[str] | None = None,
) -> dict[str, Any]:
    known = known_hashes or set()
    source_root = dataset_root / "source"
    seen: set[str] = set()
    documents: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    duplicate_known = 0
    duplicate_candidate = 0

    for family, spec in FAMILY_SPECS.items():
        folder = source_root / str(spec["directory"])
        files = (
            sorted(
                (
                    path
                    for path in folder.rglob("*")
                    if path.is_file()
                    and path.suffix.casefold() in SUPPORTED_EXTENSIONS
                ),
                key=lambda path: path.as_posix().casefold(),
            )
            if folder.is_dir()
            else []
        )
        family_count = 0
        for path in files:
            digest = sha256_file(path)
            if digest in known:
                duplicate_known += 1
                continue
            if digest in seen:
                duplicate_candidate += 1
                continue
            seen.add(digest)
            family_count += 1
            documents.append(
                {
                    "documentFamily": family,
                    "sourcePath": path.relative_to(dataset_root).as_posix(),
                    "sourceFormat": path.suffix.lstrip(".").upper(),
                    "sourceSha256": digest,
                    "sizeBytes": path.stat().st_size,
                }
            )
        counts[family] = family_count

    deficits = {
        family: max(0, int(spec["minimum"]) - counts.get(family, 0))
        for family, spec in FAMILY_SPECS.items()
    }
    return {
        "schemaVersion": PROTOCOL_VERSION,
        "eligibleDocumentCount": len(documents),
        "countsByFamily": counts,
        "minimumByFamily": {
            family: int(spec["minimum"]) for family, spec in FAMILY_SPECS.items()
        },
        "deficitsByFamily": deficits,
        "duplicateKnownCount": duplicate_known,
        "duplicateCandidateCount": duplicate_candidate,
        "readyToPrepare": (
            not any(deficits.values())
            and duplicate_known == 0
            and duplicate_candidate == 0
        ),
        "documents": documents,
    }


def prepare_manifest(
    dataset_root: Path,
    authorization: Mapping[str, Any],
    audit: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if authorization.get("authorizedLocalDocumentsOnly") is not True:
        raise ValueError("Held-out requires authorized local documents only")
    if authorization.get("processingRightsConfirmed") is not True:
        raise ValueError("Processing rights have not been confirmed")
    if authorization.get("documentOwnerConsentOrLawfulBasisConfirmed") is not True:
        raise ValueError("Consent or another lawful basis has not been confirmed")
    if not str(authorization.get("rightsBasis") or "").strip():
        raise ValueError("Authorization rightsBasis is required")
    if audit.get("readyToPrepare") is not True:
        raise ValueError("Held-out source audit is not ready")

    source_documents = list(audit.get("documents") or [])
    documents = []
    family_indexes = {family: 0 for family in FAMILY_SPECS}
    for source in source_documents:
        family = str(source["documentFamily"])
        family_indexes[family] += 1
        code = "".join(part[0] for part in family.split("_"))
        documents.append(
            {
                "documentId": f"H17-{code}-{family_indexes[family]:03d}",
                **source,
            }
        )
    dataset_identity = [
        {
            "documentId": document["documentId"],
            "documentFamily": document["documentFamily"],
            "sourceSha256": document["sourceSha256"],
        }
        for document in documents
    ]
    dataset_digest = hashlib.sha256(
        canonical_json_bytes(dataset_identity)
    ).hexdigest()
    manifest = {
        "schemaVersion": PROTOCOL_VERSION,
        "datasetId": authorization["datasetId"],
        "datasetDigest": f"sha256:{dataset_digest}",
        "createdAt": utc_now(),
        "containsRealPII": True,
        "authorization": {
            "authorizedLocalDocumentsOnly": True,
            "processingRightsConfirmed": True,
            "documentOwnerConsentOrLawfulBasisConfirmed": True,
            "rightsBasis": str(authorization["rightsBasis"]),
        },
        "predictionsVisibleDuringGroundTruthReview": False,
        "recognitionPolicyDigest": LOCKED_POLICY_DIGEST,
        "parserVersion": PARSER_VERSION,
        "parserLockId": "phase17-parser-lock/1.0.0",
        "metricSpecVersion": METRIC_SPEC_VERSION,
        "documentCount": len(documents),
        "countsByFamily": dict(audit["countsByFamily"]),
        "documents": documents,
    }
    queue_documents = []
    for document in documents:
        family = str(document["documentFamily"])
        queue_documents.append(
            {
                "documentId": document["documentId"],
                "documentFamily": family,
                "sourcePath": document["sourcePath"],
                "sourceSha256": document["sourceSha256"],
                "status": PENDING,
                "fields": {
                    name: {"status": PENDING, "value": ""}
                    for name in FAMILY_SPECS[family]["fields"]
                },
            }
        )
    review_queue = {
        "schemaVersion": "phase17-heldout-ground-truth-queue/2.0.0",
        "datasetId": manifest["datasetId"],
        "datasetDigest": manifest["datasetDigest"],
        "createdAt": utc_now(),
        "containsRealPII": True,
        "predictionsVisibleDuringReview": False,
        "groundTruthStatus": PENDING,
        "reviewerId": str(authorization.get("reviewerId") or "local-reviewer"),
        "documents": queue_documents,
    }
    validate_review_queue(review_queue)
    return manifest, review_queue


def validate_review_queue(queue: Mapping[str, Any]) -> None:
    if queue.get("predictionsVisibleDuringReview") is not False:
        raise ValueError("Ground Truth queue must hide predictions")
    if contains_prediction_or_ground_truth(queue.get("documents", [])):
        raise ValueError("Ground Truth queue contains model output")
    documents = queue.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("Ground Truth queue has no documents")
    document_ids: set[str] = set()
    for document in documents:
        document_id = str(document.get("documentId") or "")
        family = str(document.get("documentFamily") or "")
        if not document_id or document_id in document_ids:
            raise ValueError("Ground Truth document IDs must be unique")
        if family not in FAMILY_SPECS:
            raise ValueError("Ground Truth queue contains an unsupported family")
        document_ids.add(document_id)
        fields = document.get("fields")
        review_profile = str(document.get("reviewProfile") or "")
        expected = set(
            TIMESHEET_FIELDS
            if review_profile == TIMESHEET_REVIEW_PROFILE
            else FAMILY_SPECS[family]["fields"]
        )
        if not isinstance(fields, dict) or set(fields) != expected:
            raise ValueError("Ground Truth field set does not match the family")
        tables = document.get("tables")
        if review_profile == TIMESHEET_REVIEW_PROFILE:
            if family != "EMPLOYEE_FORM_TABLE":
                raise ValueError("TIMESHEET review profile uses the wrong family")
            if (
                not isinstance(tables, dict)
                or set(tables) != {"attendance"}
                or not isinstance(tables["attendance"], dict)
                or not isinstance(tables["attendance"].get("rows"), list)
            ):
                raise ValueError("TIMESHEET Ground Truth table is invalid")
        elif tables is not None:
            raise ValueError("Unexpected Ground Truth table")


def confirmed_ground_truth(queue: Mapping[str, Any]) -> dict[str, Any]:
    validate_review_queue(queue)
    documents = []
    for document in queue["documents"]:
        confirmed_fields = {}
        for name, field in document["fields"].items():
            status = str(field.get("status") or "")
            value = str(field.get("value") or "").strip()
            if status not in {CONFIRMED, SKIPPED}:
                raise ValueError("Every Ground Truth field must be reviewed")
            if status == CONFIRMED and not value:
                raise ValueError("A confirmed Ground Truth value cannot be empty")
            confirmed_fields[name] = {
                "status": status,
                "value": value if status == CONFIRMED else "",
            }
        if document.get("reviewProfile") == TIMESHEET_REVIEW_PROFILE:
            attendance = document["tables"]["attendance"]
            if attendance.get("status") != CONFIRMED or not attendance.get("rows"):
                raise ValueError(
                    "TIMESHEET Ground Truth table must be confirmed"
                )
        documents.append(
            {
                "documentId": document["documentId"],
                "documentFamily": document["documentFamily"],
                **(
                    {
                        "documentType": "TIMESHEET",
                        "reviewProfile": TIMESHEET_REVIEW_PROFILE,
                        "tables": document["tables"],
                    }
                    if document.get("reviewProfile") == TIMESHEET_REVIEW_PROFILE
                    else {}
                ),
                "sourceSha256": document["sourceSha256"],
                "fields": confirmed_fields,
            }
        )
    return {
        "schemaVersion": "phase17-heldout-ground-truth/2.0.0",
        "datasetId": queue["datasetId"],
        "datasetDigest": queue["datasetDigest"],
        "confirmedAt": utc_now(),
        "containsRealPII": True,
        "predictionsVisibleDuringReview": False,
        "groundTruthStatus": "USER_CONFIRMED_HELD_OUT_GROUND_TRUTH",
        "documents": documents,
    }


def seal_predictions(
    predictions: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if contains_ground_truth(predictions):
        raise ValueError("Prediction artifact must not contain Ground Truth")
    if predictions.get("datasetDigest") != manifest.get("datasetDigest"):
        raise ValueError("Predictions use a different dataset")
    if predictions.get("recognitionPolicyDigest") != LOCKED_POLICY_DIGEST:
        raise ValueError("Predictions do not use the locked Phase 14.8 policy")
    if predictions.get("parserVersion") != PARSER_VERSION:
        raise ValueError("Predictions do not use the locked Phase 16 parser")
    expected_ids = {
        str(document["documentId"]) for document in manifest.get("documents", [])
    }
    predicted_documents = predictions.get("documents")
    if not isinstance(predicted_documents, list):
        raise ValueError("Prediction artifact has no documents")
    predicted_ids = {
        str(document.get("documentId") or "") for document in predicted_documents
    }
    if predicted_ids != expected_ids:
        raise ValueError("Prediction document IDs do not match the manifest")
    return {
        "schemaVersion": "phase17-heldout-sealed-predictions/2.0.0",
        "sealedAt": utc_now(),
        "containsRealPII": True,
        "predictionsHiddenDuringReview": True,
        "groundTruthPresent": False,
        "datasetId": manifest["datasetId"],
        "datasetDigest": manifest["datasetDigest"],
        "recognitionPolicyDigest": LOCKED_POLICY_DIGEST,
        "parserVersion": PARSER_VERSION,
        "metricSpecVersion": METRIC_SPEC_VERSION,
        "documents": predicted_documents,
    }


def evaluate_once(
    sealed: Mapping[str, Any],
    ground_truth: Mapping[str, Any],
) -> dict[str, Any]:
    if sealed.get("predictionsHiddenDuringReview") is not True:
        raise ValueError("Predictions were not hidden during review")
    if sealed.get("datasetDigest") != ground_truth.get("datasetDigest"):
        raise ValueError("Ground Truth and predictions use different datasets")
    if (
        ground_truth.get("groundTruthStatus")
        != "USER_CONFIRMED_HELD_OUT_GROUND_TRUTH"
        or ground_truth.get("predictionsVisibleDuringReview") is not False
    ):
        raise ValueError("Ground Truth confirmation evidence is incomplete")

    predicted = {
        str(document["documentId"]): document
        for document in sealed.get("documents", [])
    }
    truth = {
        str(document["documentId"]): document
        for document in ground_truth.get("documents", [])
    }
    if predicted.keys() != truth.keys():
        raise ValueError("Ground Truth and prediction document IDs do not match")

    families: dict[str, list[tuple[str, str, str, str]]] = {
        family: [] for family in FAMILY_SPECS
    }
    table_counts_by_family = {
        family: {
            "expectedRows": 0,
            "exactRows": 0,
            "expectedCells": 0,
            "exactCells": 0,
            "presentCells": 0,
        }
        for family in FAMILY_SPECS
    }
    classification_counts = {
        family: {"documents": 0, "correct": 0} for family in FAMILY_SPECS
    }
    sensitive_false_acceptance = 0
    for document_id, expected_document in truth.items():
        family = str(expected_document["documentFamily"])
        predicted_document = predicted[document_id]
        classification_counts[family]["documents"] += 1
        classification_counts[family]["correct"] += int(
            predicted_document.get("documentFamily") == family
        )
        predicted_fields = predicted_document.get("fields") or {}
        for field_name, expected_field in expected_document["fields"].items():
            if expected_field.get("status") != CONFIRMED:
                continue
            reference = str(expected_field.get("value") or "")
            predicted_field = predicted_fields.get(field_name) or {}
            value = str(
                predicted_field.get("normalizedValue")
                if predicted_field.get("normalizedValue") is not None
                else predicted_field.get("value") or ""
            )
            status = str(predicted_field.get("status") or "not_found")
            families[family].append((field_name, reference, value, status))
            if (
                field_name in SENSITIVE_FIELDS
                and status == "accepted"
                and normalize_for_evaluation(reference)
                != normalize_for_evaluation(value)
            ):
                sensitive_false_acceptance += 1
        expected_tables = expected_document.get("tables") or {}
        if expected_tables:
            predicted_tables = predicted_document.get("tables") or []
            _accumulate_table_counts(
                table_counts_by_family[family],
                expected_tables,
                predicted_tables,
            )

    by_family = {
        family: {
            **_family_metrics(
                pairs,
                classification_counts[family]["documents"],
                classification_counts[family]["correct"],
            ),
            **_table_metrics(table_counts_by_family[family]),
        }
        for family, pairs in families.items()
    }
    all_pairs = [item for pairs in families.values() for item in pairs]
    total_documents = sum(
        value["documents"] for value in classification_counts.values()
    )
    total_correct = sum(
        value["correct"] for value in classification_counts.values()
    )
    overall_table_counts = {
        name: sum(counts[name] for counts in table_counts_by_family.values())
        for name in (
            "expectedRows",
            "exactRows",
            "expectedCells",
            "exactCells",
            "presentCells",
        )
    }
    overall = {
        **_family_metrics(all_pairs, total_documents, total_correct),
        **_table_metrics(overall_table_counts),
    }
    table_gate_passed = (
        overall["expectedTableCellCount"] == 0
        or (
            overall["tableExactCellRate"] >= 0.90
            and overall["tableCompleteness"] >= 0.95
        )
    )
    promotion_eligible = (
        sensitive_false_acceptance == 0
        and overall["classificationAccuracy"] == 1.0
        and overall["fieldExactMatchRate"] >= 0.90
        and overall["fieldCompleteness"] >= 0.95
        and overall["cer"] <= 0.05
        and overall["der"] <= 0.02
        and table_gate_passed
    )
    return {
        "schemaVersion": "phase17-heldout-evaluation/2.0.0",
        "evaluatedAt": utc_now(),
        "containsRealPII": False,
        "evaluationRunCount": 1,
        "thresholdRetuned": False,
        "predictionsWereHidden": True,
        "recognitionPolicyDigest": LOCKED_POLICY_DIGEST,
        "parserVersion": PARSER_VERSION,
        "metricSpecVersion": METRIC_SPEC_VERSION,
        "documentCount": total_documents,
        "byFamily": by_family,
        "overall": overall,
        "sensitiveFieldFalseAcceptanceCount": sensitive_false_acceptance,
        "decision": {
            "controlledPilot": (
                "ELIGIBLE_FOR_CONTROLLED_PILOT"
                if promotion_eligible
                else "NOT_PROMOTED"
            ),
            "production": "NOT_PRODUCTION_READY",
        },
    }


def _family_metrics(
    pairs: list[tuple[str, str, str, str]],
    document_count: int,
    classification_correct: int,
) -> dict[str, Any]:
    text_pairs = [(reference, prediction) for _, reference, prediction, _ in pairs]
    metrics = evaluate_text_pairs(text_pairs)
    present = sum(bool(normalize_for_evaluation(prediction)) for _, _, prediction, _ in pairs)
    accepted = sum(status == "accepted" for _, _, _, status in pairs)
    return {
        "documentCount": document_count,
        "classificationAccuracy": round(
            classification_correct / max(1, document_count),
            6,
        ),
        "evaluatedFieldCount": len(pairs),
        "fieldExactMatchCount": metrics.strict_exact_count,
        "fieldExactMatchRate": metrics.strict_exact_rate,
        "fieldCompleteness": round(present / max(1, len(pairs)), 6),
        "acceptedFieldRate": round(accepted / max(1, len(pairs)), 6),
        "cer": metrics.character_error_rate,
        "wer": metrics.word_error_rate,
        "der": metrics.diacritic_error_rate,
    }


def _normalized_table_row(row: Any) -> list[str]:
    values = row.get("values", []) if isinstance(row, Mapping) else row
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [normalize_for_evaluation(str(value or "")) for value in values]


def _accumulate_table_counts(
    counts: dict[str, int],
    expected_tables: Mapping[str, Any],
    predicted_tables: Any,
) -> None:
    expected = expected_tables.get("attendance") or {}
    expected_rows = expected.get("rows") or []
    predicted_rows = [
        _normalized_table_row(row)
        for table in (predicted_tables if isinstance(predicted_tables, list) else [])
        for row in (table.get("rows", []) if isinstance(table, Mapping) else [])
    ]
    predicted_by_key = {
        row[0]: row for row in predicted_rows if row and row[0]
    }
    for expected_row_value in expected_rows:
        expected_row = _normalized_table_row(expected_row_value)
        if not expected_row:
            continue
        predicted_row = predicted_by_key.get(expected_row[0], [])
        counts["expectedRows"] += 1
        counts["expectedCells"] += len(expected_row)
        counts["presentCells"] += sum(
            index < len(predicted_row) and bool(predicted_row[index])
            for index in range(len(expected_row))
        )
        exact_cells = sum(
            index < len(predicted_row)
            and predicted_row[index] == expected_value
            for index, expected_value in enumerate(expected_row)
        )
        counts["exactCells"] += exact_cells
        counts["exactRows"] += int(exact_cells == len(expected_row))


def _table_metrics(counts: Mapping[str, int]) -> dict[str, Any]:
    expected_rows = int(counts["expectedRows"])
    expected_cells = int(counts["expectedCells"])
    return {
        "expectedTableRowCount": expected_rows,
        "exactTableRowCount": int(counts["exactRows"]),
        "tableExactRowRate": round(
            int(counts["exactRows"]) / max(1, expected_rows),
            6,
        ),
        "expectedTableCellCount": expected_cells,
        "exactTableCellCount": int(counts["exactCells"]),
        "tableExactCellRate": round(
            int(counts["exactCells"]) / max(1, expected_cells),
            6,
        ),
        "tableCompleteness": round(
            int(counts["presentCells"]) / max(1, expected_cells),
            6,
        ),
    }
