"""Local-only Ground Truth review gate for the Phase 11.6 CCCD held-out set.

Review endpoints expose only the source image and the user's private Ground
Truth draft. Sealed predictions remain inaccessible during review; the
post-evaluation inspector reads them only after the queue is locked and the
one-time evaluator has produced its private report.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import unicodedata
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FIELD_ORDER = (
    "identityNumber",
    "fullName",
    "dateOfBirth",
    "sex",
    "nationality",
    "placeOfOrigin",
    "placeOfResidence",
    "dateOfExpiry",
)
DOCUMENT_ID_RE = re.compile(r"^CCCD-HO-\d{3}$")
MAX_FIELD_LENGTH = 500
DISPOSITION_IN_SCOPE = "IN_SCOPE_FRONT"
DISPOSITION_OUT_OF_SCOPE_BACK = "OUT_OF_SCOPE_BACK"
DISPOSITIONS = {DISPOSITION_IN_SCOPE, DISPOSITION_OUT_OF_SCOPE_BACK}
MAX_DISPOSITION_REASON_LENGTH = 240
_WRITE_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_authorized(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError("CCCD held-out root is unavailable")
    authorization = _load_json(root / "authorization.json")
    if authorization.get("authorizedLocalDocumentsOnly") is not True:
        raise PermissionError("CCCD held-out corpus is not authorized for local access")
    if authorization.get("processingRightsConfirmed") is not True:
        raise PermissionError("CCCD held-out processing rights are not confirmed")
    return authorization


def _manifest(root: Path) -> dict[str, Any]:
    manifest = _load_json(root / "manifest_private.json")
    if manifest.get("documentCount") != len(manifest.get("records", [])):
        raise ValueError("CCCD held-out manifest count is inconsistent")
    return manifest


def _queue_path(root: Path) -> Path:
    return root / "ground_truth" / "review_queue_private.json"


def _load_queue(root: Path) -> dict[str, Any]:
    path = _queue_path(root)
    if not path.is_file():
        raise FileNotFoundError("Ground Truth review queue is unavailable")
    return _load_json(path)


def _record(root: Path, document_id: str) -> dict[str, Any]:
    if not DOCUMENT_ID_RE.fullmatch(document_id):
        raise ValueError("Invalid CCCD held-out document id")
    manifest = _manifest(root)
    record = next(
        (item for item in manifest.get("records", []) if item.get("documentId") == document_id),
        None,
    )
    if record is None:
        raise FileNotFoundError("CCCD held-out document not found")
    return record


def _source_path(root: Path, record: dict[str, Any]) -> Path:
    relative = Path(str(record.get("sourcePath", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe CCCD held-out source path")
    source = (root / relative).resolve()
    if root.resolve() not in source.parents or not source.is_file():
        raise FileNotFoundError("CCCD held-out source image is unavailable")
    return source


def _queue_document(queue: dict[str, Any], document_id: str) -> dict[str, Any]:
    document = next(
        (item for item in queue.get("documents", []) if item.get("documentId") == document_id),
        None,
    )
    if document is None:
        raise FileNotFoundError("Ground Truth review document not found")
    return document


def _reviewed_fields(document: dict[str, Any]) -> int:
    fields = document.get("fields", {})
    return sum(
        1
        for field_name in FIELD_ORDER
        if isinstance(fields.get(field_name), dict)
        and (
            bool(str(fields[field_name].get("value", "")).strip())
            or fields[field_name].get("notPresent") is True
        )
    )


def _disposition(document: dict[str, Any]) -> str:
    value = str(document.get("disposition", DISPOSITION_IN_SCOPE)).strip()
    return value if value in DISPOSITIONS else DISPOSITION_IN_SCOPE


def _is_in_scope(document: dict[str, Any]) -> bool:
    return _disposition(document) == DISPOSITION_IN_SCOPE


def load_review_summary(root: Path) -> dict[str, Any]:
    """Return only non-prediction review metadata for the local UI."""
    _require_authorized(root)
    manifest = _manifest(root)
    queue = _load_queue(root)
    confirmed = root / "ground_truth" / "ground_truth_confirmed_private.json"
    evaluation = root / "evaluation" / "evaluate_once_private.json"
    documents: list[dict[str, Any]] = []
    queue_by_id = {item.get("documentId"): item for item in queue.get("documents", [])}
    for record in manifest.get("records", []):
        document_id = str(record.get("documentId", ""))
        source = _source_path(root, record)
        review = queue_by_id.get(document_id, {})
        documents.append(
            {
                "documentId": document_id,
                "documentIndex": record.get("documentIndex"),
                "sourceFormat": record.get("sourceFormat", "IMAGE"),
                "sourceFile": source.name,
                "previewAvailable": True,
                "reviewStatus": review.get("status", "PENDING"),
                "disposition": _disposition(review),
                "exclusionReason": review.get("exclusionReason"),
                "reviewedFieldCount": _reviewed_fields(review),
                "fieldCount": len(FIELD_ORDER),
            }
        )
    ground_truth_status = (
        "CONFIRMED"
        if confirmed.is_file() and queue.get("groundTruthStatus") == "CONFIRMED"
        else str(queue.get("groundTruthStatus", "PENDING_HUMAN_CONFIRMATION"))
    )
    evaluation_status = "COMPLETE" if evaluation.is_file() else "NOT_RUN"
    eligible_documents = [item for item in documents if item["disposition"] == DISPOSITION_IN_SCOPE]
    excluded_documents = [item for item in documents if item["disposition"] != DISPOSITION_IN_SCOPE]
    return {
        "schemaVersion": "phase11.6-cccd-ground-truth-review/1.0.0",
        "datasetId": manifest.get("datasetId"),
        "datasetDigest": manifest.get("datasetDigest"),
        "documentCount": len(eligible_documents),
        "sourceDocumentCount": len(documents),
        "excludedDocumentCount": len(excluded_documents),
        "fieldCount": len(FIELD_ORDER),
        "fields": list(FIELD_ORDER),
        "groundTruthStatus": ground_truth_status,
        "evaluationStatus": evaluation_status,
        "predictionsHiddenDuringReview": True,
        "localOnly": True,
        "documentIds": [item["documentId"] for item in documents],
        "documents": documents,
        "canLock": ground_truth_status != "CONFIRMED"
        and bool(eligible_documents)
        and all(
            (
                item["disposition"] != DISPOSITION_IN_SCOPE
                and item["reviewStatus"] == "EXCLUDED"
            )
            or item["reviewedFieldCount"] == len(FIELD_ORDER)
            for item in documents
        ),
        "canEvaluate": ground_truth_status == "CONFIRMED" and evaluation_status == "NOT_RUN",
    }


def load_review_document(root: Path, document_id: str) -> dict[str, Any]:
    """Return source metadata and the private Ground Truth draft only."""
    _require_authorized(root)
    record = _record(root, document_id)
    queue = _load_queue(root)
    review = _queue_document(queue, document_id)
    source = _source_path(root, record)
    return {
        "schemaVersion": "phase11.6-cccd-ground-truth-review-document/1.0.0",
        "documentId": document_id,
        "documentIndex": record.get("documentIndex"),
        "sourceFormat": record.get("sourceFormat", "IMAGE"),
        "sourceFile": source.name,
        "previewAvailable": True,
        "reviewStatus": review.get("status", "PENDING"),
        "disposition": _disposition(review),
        "exclusionReason": review.get("exclusionReason"),
        "fields": {
            field_name: {
                "value": str(review.get("fields", {}).get(field_name, {}).get("value", "")),
                "notPresent": (
                    review.get("fields", {}).get(field_name, {}).get("notPresent") is True
                ),
            }
            for field_name in FIELD_ORDER
        },
        "verificationAssertions": review.get(
            "verificationAssertions",
            {"comparedWithImage": False, "allTextChecked": False},
        ),
        "predictionsHidden": True,
    }


def _normalized_text(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value or "")).strip().casefold()


def _ascii_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        char for char in normalized if not unicodedata.combining(char)
    ).casefold().strip()


def _evaluation_field(field: Any) -> dict[str, Any]:
    if not isinstance(field, dict):
        field = {}
    evidence = field.get("evidence")
    evidence_out: dict[str, Any] = {
        "pageIndex": None,
        "bbox": None,
        "candidateCount": 0,
    }
    if isinstance(evidence, dict):
        evidence_out = {
            "pageIndex": evidence.get("pageIndex"),
            "bbox": evidence.get("bbox"),
            "candidateCount": len(evidence.get("candidates", []))
            if isinstance(evidence.get("candidates"), list)
            else 0,
        }
    return {
        "value": field.get("value"),
        "asciiValue": field.get("asciiValue"),
        "status": field.get("status"),
        "confidence": field.get("confidence"),
        "errorSignals": field.get("errorSignals", []),
        "selectionMode": field.get("selectionMode"),
        "evidence": evidence_out,
    }


def _field_comparison(
    ground_truth: dict[str, Any], prediction: dict[str, Any]
) -> dict[str, Any]:
    not_present = ground_truth.get("notPresent") is True
    expected = None if not_present else ground_truth.get("value")
    predicted = prediction.get("value")
    if not_present:
        return {
            "status": "NOT_IN_SOURCE",
            "strictExact": None,
            "asciiExact": None,
            "errorClass": None,
        }
    strict_exact = _normalized_text(expected) == _normalized_text(predicted)
    ascii_exact = _ascii_text(expected) == _ascii_text(predicted)
    signals = prediction.get("errorSignals")
    error_class = "EXACT" if strict_exact else None
    if error_class is None and not _normalized_text(predicted):
        error_class = "NOT_FOUND"
    if error_class is None and ascii_exact:
        error_class = "DIACRITICS_ONLY"
    if error_class is None and isinstance(signals, list) and signals:
        error_class = str(signals[0]).upper()
    if error_class is None:
        error_class = "MISMATCH"
    return {
        "status": "EXACT" if strict_exact else "MISMATCH",
        "strictExact": strict_exact,
        "asciiExact": ascii_exact,
        "errorClass": error_class,
    }


def load_evaluation_document(root: Path, document_id: str) -> dict[str, Any]:
    """Expose one evaluated document only after the one-time gate completed."""
    _require_authorized(root)
    confirmed_path = root / "ground_truth" / "ground_truth_confirmed_private.json"
    report_path = root / "evaluation" / "evaluate_once_private.json"
    sealed_path = root / "predictions" / "sealed_predictions_private.json"
    if not confirmed_path.is_file() or not report_path.is_file():
        raise ValueError("Post-evaluation output is not available")
    confirmed = _load_json(confirmed_path)
    if confirmed.get("groundTruthStatus") != "CONFIRMED":
        raise ValueError("Ground Truth must be confirmed before output inspection")
    record = _record(root, document_id)
    review = next(
        (
            item
            for item in confirmed.get("documents", [])
            if item.get("documentId") == document_id
        ),
        None,
    )
    if not isinstance(review, dict):
        raise ValueError("Document is excluded from the evaluated metric")
    sealed = _load_json(sealed_path)
    prediction = next(
        (
            item
            for item in sealed.get("documents", [])
            if item.get("documentId") == document_id
        ),
        None,
    )
    if not isinstance(prediction, dict):
        raise FileNotFoundError("Sealed prediction is unavailable for this document")
    phase_fields = {
        phase: prediction.get(phase, {}).get("fields", {})
        if isinstance(prediction.get(phase), dict)
        else {}
        for phase in ("phase11_5", "phase11_6")
    }
    fields: dict[str, Any] = {}
    for field_name in FIELD_ORDER:
        ground_truth = review.get("fields", {}).get(field_name, {})
        if not isinstance(ground_truth, dict):
            ground_truth = {}
        phase_output = {
            phase: _evaluation_field(values.get(field_name))
            for phase, values in phase_fields.items()
        }
        fields[field_name] = {
            "groundTruth": {
                "value": None
                if ground_truth.get("notPresent") is True
                else ground_truth.get("value"),
                "notPresent": ground_truth.get("notPresent") is True,
            },
            "phase11_5": phase_output["phase11_5"],
            "phase11_6": phase_output["phase11_6"],
            "comparison": {
                phase: _field_comparison(ground_truth, phase_output[phase])
                for phase in ("phase11_5", "phase11_6")
            },
        }
    report = _load_json(report_path)
    return {
        "schemaVersion": "phase11.6-cccd-evaluation-document/1.0.0",
        "evaluationKind": report.get("evaluationKind"),
        "evaluatedAt": report.get("evaluatedAt"),
        "documentId": document_id,
        "documentIndex": record.get("documentIndex"),
        "sourceFile": Path(str(record.get("sourcePath", ""))).name,
        "documentCount": report.get("documentCount"),
        "fields": fields,
        "localOnly": True,
        "predictionsHiddenDuringReview": True,
    }


def resolve_review_source(root: Path, document_id: str) -> Path:
    _require_authorized(root)
    return _source_path(root, _record(root, document_id))


def set_review_disposition(
    root: Path,
    document_id: str,
    disposition: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Set whether a source belongs to the front-side OCR metric set."""
    _require_authorized(root)
    if disposition not in DISPOSITIONS:
        raise ValueError("Unsupported document disposition")
    _record(root, document_id)
    normalized_reason = " ".join(str(reason or "").split()).strip()
    if len(normalized_reason) > MAX_DISPOSITION_REASON_LENGTH:
        raise ValueError("Disposition reason is too large")
    with _WRITE_LOCK:
        queue = _load_queue(root)
        if queue.get("groundTruthStatus") == "CONFIRMED":
            raise ValueError("Ground Truth is already locked")
        document = _queue_document(queue, document_id)
        document["disposition"] = disposition
        document["dispositionSetAt"] = utc_now()
        document["reviewer"] = "local_user"
        if disposition == DISPOSITION_OUT_OF_SCOPE_BACK:
            document["status"] = "EXCLUDED"
            document["exclusionReason"] = normalized_reason or "back_side_outside_front_schema"
            document["fields"] = {
                field_name: {"value": "", "notPresent": False}
                for field_name in FIELD_ORDER
            }
            document["verificationAssertions"] = {
                "comparedWithImage": False,
                "allTextChecked": False,
            }
        else:
            document["status"] = "PENDING"
            document.pop("exclusionReason", None)
            document["fields"] = {
                field_name: {"value": "", "notPresent": False}
                for field_name in FIELD_ORDER
            }
            document["verificationAssertions"] = {
                "comparedWithImage": False,
                "allTextChecked": False,
            }
        _write_json_atomic(_queue_path(root), queue)
    return {
        "saved": True,
        "documentId": document_id,
        "disposition": disposition,
        "reviewStatus": document["status"],
        "metricIncluded": disposition == DISPOSITION_IN_SCOPE,
    }


def save_review(root: Path, document_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist one reviewed document after source-image assertions pass."""
    _require_authorized(root)
    if payload.get("assertions", {}).get("comparedWithImage") is not True:
        raise ValueError("Image comparison assertion is required")
    if payload.get("assertions", {}).get("allTextChecked") is not True:
        raise ValueError("Full text/diacritic check assertion is required")
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("fields must be an object")
    unknown = set(fields) - set(FIELD_ORDER)
    if unknown:
        raise ValueError("Unsupported Ground Truth field")
    normalized: dict[str, dict[str, Any]] = {}
    for field_name in FIELD_ORDER:
        item = fields.get(field_name)
        if not isinstance(item, dict):
            raise ValueError(f"Missing Ground Truth field: {field_name}")
        value = item.get("value", "")
        not_present = item.get("notPresent") is True
        if not isinstance(value, str):
            raise ValueError("Ground Truth values must be text")
        value = " ".join(value.split()).strip()
        if len(value) > MAX_FIELD_LENGTH:
            raise ValueError("Ground Truth field is too large")
        if not_present and value:
            raise ValueError("A not-present field must be empty")
        if not not_present and not value:
            raise ValueError("Enter a value or mark the field absent")
        normalized[field_name] = {"value": value, "notPresent": not_present}
    _record(root, document_id)
    with _WRITE_LOCK:
        queue = _load_queue(root)
        if queue.get("groundTruthStatus") == "CONFIRMED":
            raise ValueError("Ground Truth is already locked")
        document = _queue_document(queue, document_id)
        if not _is_in_scope(document):
            raise ValueError("Document is out of scope for front-side Ground Truth")
        document["fields"] = normalized
        document["status"] = "REVIEWED"
        document["reviewedAt"] = utc_now()
        document["reviewer"] = "local_user"
        document["verificationAssertions"] = {
            "comparedWithImage": True,
            "allTextChecked": True,
        }
        _write_json_atomic(_queue_path(root), queue)
    return {
        "saved": True,
        "documentId": document_id,
        "reviewStatus": "REVIEWED",
        "reviewedFieldCount": len(FIELD_ORDER),
    }


def lock_ground_truth(root: Path, *, confirm: bool) -> dict[str, Any]:
    """Lock the complete private queue without opening predictions."""
    _require_authorized(root)
    if confirm is not True:
        raise ValueError("Explicit Ground Truth lock confirmation is required")
    with _WRITE_LOCK:
        queue = _load_queue(root)
        if queue.get("groundTruthStatus") == "CONFIRMED":
            raise ValueError("Ground Truth is already locked")
        documents = queue.get("documents", [])
        if len(documents) != int(queue.get("documentCount", 0)):
            raise ValueError("Ground Truth queue count is inconsistent")
        eligible_documents = [item for item in documents if _is_in_scope(item)]
        excluded_documents = [item for item in documents if not _is_in_scope(item)]
        if not eligible_documents:
            raise ValueError("At least one in-scope document is required")
        if any(_reviewed_fields(item) != len(FIELD_ORDER) for item in eligible_documents):
            raise ValueError("Every document and field must be reviewed before locking")
        if any(item.get("status") != "EXCLUDED" for item in excluded_documents):
            raise ValueError("Out-of-scope documents must be explicitly excluded")
        now = utc_now()
        confirmed_payload = {
            "schemaVersion": "phase11.6-cccd-ground-truth/1.0.0",
            "confirmedAt": now,
            "reviewer": "local_user",
            "containsRealPII": True,
            "predictionsVisibleDuringGroundTruthReview": False,
            "groundTruthStatus": "CONFIRMED",
            "datasetId": queue.get("datasetId"),
            "datasetDigest": queue.get("datasetDigest"),
            "documentCount": len(eligible_documents),
            "sourceDocumentCount": len(documents),
            "excludedDocumentCount": len(excluded_documents),
            "excludedDocuments": [
                {
                    "documentId": item.get("documentId"),
                    "disposition": _disposition(item),
                    "reason": item.get("exclusionReason"),
                }
                for item in excluded_documents
            ],
            "documents": eligible_documents,
        }
        confirmed_path = root / "ground_truth" / "ground_truth_confirmed_private.json"
        _write_json_atomic(confirmed_path, confirmed_payload)
        queue["groundTruthStatus"] = "CONFIRMED"
        queue["confirmedAt"] = now
        queue["reviewer"] = "local_user"
        _write_json_atomic(_queue_path(root), queue)
        lock_payload = {
            "schemaVersion": "phase11.6-cccd-ground-truth-lock/1.0.0",
            "lockedAt": now,
            "groundTruthStatus": "CONFIRMED",
            "documentCount": len(eligible_documents),
            "sourceDocumentCount": len(documents),
            "excludedDocumentCount": len(excluded_documents),
            "datasetId": queue.get("datasetId"),
            "groundTruthSha256": _sha256(confirmed_path),
            "predictionsOpened": False,
        }
        _write_json_atomic(root / "ground_truth" / "GROUND_TRUTH_LOCK.json", lock_payload)
    return {
        "locked": True,
        "groundTruthStatus": "CONFIRMED",
        "documentCount": len(eligible_documents),
        "sourceDocumentCount": len(documents),
        "excludedDocumentCount": len(excluded_documents),
        "predictionsOpened": False,
    }


def evaluate_once(root: Path, *, python_executable: str, script_path: Path) -> dict[str, Any]:
    """Run the immutable evaluator once after Ground Truth is locked."""
    _require_authorized(root)
    confirmed = root / "ground_truth" / "ground_truth_confirmed_private.json"
    sealed = root / "predictions" / "sealed_predictions_private.json"
    report = root / "evaluation" / "evaluate_once_private.json"
    if not confirmed.is_file():
        raise ValueError("Ground Truth must be locked before evaluate-once")
    if not sealed.is_file():
        raise FileNotFoundError("Sealed prediction snapshot is unavailable")
    if report.exists():
        raise FileExistsError("Evaluate-once has already run")
    import subprocess

    completed = subprocess.run(
        [python_executable, str(script_path), "--data-root", str(root)],
        cwd=str(script_path.parents[1]),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "Evaluation failed").strip()
        raise RuntimeError(message[-1000:])
    if not report.is_file():
        raise RuntimeError("Evaluation did not create its aggregate report")
    result = _load_json(report)
    return {
        "status": result.get("promotionGate", {}).get("status", "SHADOW_REVIEW_ONLY"),
        "evaluationKind": result.get("evaluationKind"),
        "documentCount": result.get("documentCount"),
        "metrics": result.get("metrics", {}),
        "promotionGate": result.get("promotionGate", {}),
    }
