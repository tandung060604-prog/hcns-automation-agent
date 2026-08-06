"""Local-only shadow UAT accessors for OCR-HO-V2-008.

This module deliberately reads only the development candidate artifacts and
their source images.  Ground Truth is not loaded or used by the inspector;
the aggregate development report remains the sole scoring artifact.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase11_5_cccd import FIELD_ORDER

SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
DOCUMENT_SCHEMA_VERSION = "ocr-ho-v2-009-shadow-uat/1.0.0"
REPORT_NAME = "CCCD_OCR_HO_V2_008_DEVELOPMENT_COMPARISON.json"
REVIEW_NAME = "OCR_HO_V2_009_SHADOW_UAT_REVIEWS.json"
DECISIONS = {"APPROVE_SHADOW", "REJECT_SHADOW", "NEEDS_FOLLOWUP"}
TARGET_FIELDS = {"placeOfOrigin", "placeOfResidence"}
_REVIEW_LOCK = threading.Lock()


def _artifact_config(root: Path) -> dict[str, str]:
    """Select the newest private candidate without opening Ground Truth."""

    report_dir = root / "output" / "phase11" / "reports"
    if (report_dir / "CCCD_OCR_HO_V2_014_DEVELOPMENT_COMPARISON.json").is_file():
        return {
            "candidateRoot": "phase11_10_v2",
            "reportName": "CCCD_OCR_HO_V2_014_DEVELOPMENT_COMPARISON.json",
            "reviewName": "OCR_HO_V2_014_SHADOW_REVIEWS.json",
            "schemaVersion": "ocr-ho-v2-014-line-aware-shadow/1.0.0",
        }
    if (report_dir / "CCCD_OCR_HO_V2_011_DEVELOPMENT_COMPARISON.json").is_file():
        return {
            "candidateRoot": "phase11_9_v2",
            "reportName": "CCCD_OCR_HO_V2_011_DEVELOPMENT_COMPARISON.json",
            "reviewName": "OCR_HO_V2_013_PROMOTION_REVIEWS.json",
            "schemaVersion": "ocr-ho-v2-013-promotion-review/1.0.0",
        }
    return {
        "candidateRoot": "phase11_8_v2",
        "reportName": REPORT_NAME,
        "reviewName": REVIEW_NAME,
        "schemaVersion": DOCUMENT_SCHEMA_VERSION,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return payload


def _session_root(root: Path) -> Path:
    for candidate in (
        root / "user_uploads-sessions",
        root / "user_uploads" / "sessions",
    ):
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("OCR-HO-V2 shadow session root is unavailable")


def _report_path(root: Path) -> Path:
    config = _artifact_config(root)
    return root / "output" / "phase11" / "reports" / config["reportName"]


def _review_path(root: Path) -> Path:
    config = _artifact_config(root)
    return root / "output" / "phase11" / config["reviewName"]


def _review_store(root: Path) -> dict[str, Any]:
    config = _artifact_config(root)
    path = _review_path(root)
    if not path.is_file():
        return {
            "schemaVersion": config["schemaVersion"],
            "localOnly": True,
            "reviews": {},
        }
    payload = _json(path)
    reviews = payload.get("reviews")
    if not isinstance(reviews, dict):
        raise ValueError("Shadow UAT review store is invalid")
    return payload


def _session_records(root: Path) -> list[dict[str, Any]]:
    config = _artifact_config(root)
    records: list[dict[str, Any]] = []
    for session_dir in _session_root(root).iterdir():
        if not session_dir.is_dir() or not SESSION_ID_RE.fullmatch(session_dir.name):
            continue
        candidate_path = session_dir / config["candidateRoot"] / "field_consensus.json"
        baseline_path = session_dir / "phase11_5" / "identity_card.json"
        result_path = session_dir / "result.json"
        input_dir = session_dir / "input"
        if not all(path.is_file() for path in (candidate_path, baseline_path, result_path)):
            continue
        source_paths = sorted(
            path
            for path in input_dir.glob("document.*")
            if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg", ".png", ".pdf"}
        )
        if not source_paths:
            continue
        result = _json(result_path)
        source = result.get("source") if isinstance(result.get("source"), dict) else {}
        candidate = _json(candidate_path)
        identity_card = candidate.get("identityCard")
        if not isinstance(identity_card, dict):
            continue
        records.append(
            {
                "documentId": session_dir.name,
                "sessionDir": session_dir,
                "sourcePath": source_paths[0],
                "sourceFile": str(source.get("originalFileName") or source_paths[0].name),
                "sourceFormat": str(
                    source.get("format") or source_paths[0].suffix.lstrip(".").upper()
                ),
                "pageCount": int(source.get("pageCount") or 1),
                "candidatePath": candidate_path,
                "baselinePath": baseline_path,
                "candidate": candidate,
                "documentIndex": len(records) + 1,
            }
        )
    return records


def _record(root: Path, document_id: str) -> dict[str, Any]:
    if not SESSION_ID_RE.fullmatch(document_id):
        raise ValueError("Invalid OCR-HO-V2 shadow document id")
    for record in _session_records(root):
        if record["documentId"] == document_id:
            return record
    raise FileNotFoundError("OCR-HO-V2 shadow document not found")


def _review_for(store: dict[str, Any], document_id: str) -> dict[str, Any] | None:
    review = store.get("reviews", {}).get(document_id)
    return review if isinstance(review, dict) else None


def _public_review(review: dict[str, Any] | None) -> dict[str, Any] | None:
    if review is None:
        return None
    return {
        "decision": review.get("decision"),
        "reviewedAt": review.get("reviewedAt"),
        "reviewer": review.get("reviewer"),
        "assertions": review.get("assertions", {}),
        "note": review.get("note", ""),
    }


def _field_projection(field: Any) -> dict[str, Any]:
    if not isinstance(field, dict):
        return {
            "value": None,
            "asciiValue": None,
            "status": None,
            "asciiStatus": None,
            "confidence": None,
            "errorSignals": [],
            "selectionMode": None,
            "evidence": {
                "pageIndex": None,
                "bbox": [],
                "candidateCount": 0,
                "recognizerProfiles": [],
            },
        }
    evidence = field.get("evidence") if isinstance(field.get("evidence"), dict) else {}
    candidates = evidence.get("candidates") if isinstance(evidence.get("candidates"), list) else []
    profiles = sorted(
        {
            str(item.get("profile"))
            for item in candidates
            if isinstance(item, dict) and item.get("profile")
        }
    )
    bbox = evidence.get("bbox")
    if not isinstance(bbox, list):
        bbox = []
    return {
        "value": field.get("value"),
        "asciiValue": field.get("asciiValue"),
        "status": field.get("status"),
        "asciiStatus": field.get("asciiStatus"),
        "confidence": field.get("confidence"),
        "errorSignals": [str(value) for value in field.get("errorSignals", [])]
        if isinstance(field.get("errorSignals"), list)
        else [],
        "selectionMode": field.get("selectionMode"),
        "evidence": {
            "pageIndex": evidence.get("pageIndex"),
            "bbox": bbox,
            "candidateCount": len(candidates),
            "recognizerProfiles": profiles,
        },
    }


def _load_fields(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline = _json(record["baselinePath"]).get("fields")
    candidate = record["candidate"].get("identityCard", {}).get("fields")
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise ValueError("OCR-HO-V2 shadow field artifacts are invalid")
    return baseline, candidate


def load_shadow_summary(root: Path) -> dict[str, Any]:
    """Return aggregate gate plus non-Ground-Truth local review metadata."""
    config = _artifact_config(root)
    report = _json(_report_path(root))
    gate_report = report.get("gates") or report.get("promotionGate", {})
    records = _session_records(root)
    store = _review_store(root)
    review_counts = {"PENDING": 0, "APPROVE_SHADOW": 0, "REJECT_SHADOW": 0, "NEEDS_FOLLOWUP": 0}
    documents: list[dict[str, Any]] = []
    for record in records:
        review = _review_for(store, record["documentId"])
        decision = str(review.get("decision") if review else "PENDING")
        review_counts[decision] = review_counts.get(decision, 0) + 1
        documents.append(
            {
                "documentId": record["documentId"],
                "documentIndex": record["documentIndex"],
                "sourceFile": record["sourceFile"],
                "sourceFormat": record["sourceFormat"],
                "pageCount": record["pageCount"],
                "previewAvailable": True,
                "reviewDecision": decision,
                "reviewedAt": review.get("reviewedAt") if review else None,
            }
        )
    return {
        "schemaVersion": config["schemaVersion"],
        "localOnly": True,
        "containsRealPII": True,
        "groundTruthLoaded": False,
        "predictionMode": "SHADOW_REVIEW_ONLY",
        "candidateVersion": report.get("candidateVersion", "11.10.0"),
        "policyId": report.get("policyId"),
        "datasetRole": report.get("datasetRole"),
        "targetFields": report.get("targetFields", sorted(TARGET_FIELDS)),
        "protectedFields": report.get("protectedFields", []),
        "documentCount": len(records),
        "metrics": report.get("metrics", {}),
        "gates": gate_report,
        "developmentRegressionGate": gate_report.get("developmentRegressionGate", {}),
        "heldoutReadinessGate": gate_report.get("heldoutReadinessGate", {}),
        "promotionGate": gate_report,
        "warningCounts": report.get("warningCounts", {}),
        "reviewCounts": review_counts,
        "documents": documents,
    }


def load_shadow_document(root: Path, document_id: str) -> dict[str, Any]:
    config = _artifact_config(root)
    record = _record(root, document_id)
    report = _json(_report_path(root))
    baseline, candidate = _load_fields(record)
    fields: dict[str, Any] = {}
    for field_name in FIELD_ORDER:
        baseline_field = _field_projection(baseline.get(field_name))
        candidate_field = _field_projection(candidate.get(field_name))
        fields[field_name] = {
            "targetField": field_name in TARGET_FIELDS,
            "changed": (
                baseline_field["value"] != candidate_field["value"]
                or baseline_field["asciiValue"] != candidate_field["asciiValue"]
                or baseline_field["selectionMode"] != candidate_field["selectionMode"]
            ),
            "baseline": baseline_field,
            "candidate": candidate_field,
        }
    return {
        "schemaVersion": config["schemaVersion"],
        "localOnly": True,
        "containsRealPII": True,
        "groundTruthLoaded": False,
        "predictionMode": "SHADOW_REVIEW_ONLY",
        "candidateVersion": report.get("candidateVersion", "11.10.0"),
        "policyId": report.get("policyId"),
        "documentId": record["documentId"],
        "documentIndex": record["documentIndex"],
        "sourceFile": record["sourceFile"],
        "sourceFormat": record["sourceFormat"],
        "pageCount": record["pageCount"],
        "previewAvailable": True,
        "sourceReference": "input/document.*",
        "baselineReference": "phase11_5/identity_card.json",
        "candidateReference": f"{config['candidateRoot']}/field_consensus.json",
        "candidatePolicyLock": record["candidate"].get("policyLock", {}),
        "fields": fields,
        "review": _public_review(_review_for(_review_store(root), document_id)),
    }


def resolve_shadow_source(root: Path, document_id: str) -> Path:
    return _record(root, document_id)["sourcePath"]


def save_shadow_review(root: Path, document_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = _artifact_config(root)
    _record(root, document_id)
    decision = str(payload.get("decision", "")).strip().upper()
    if decision not in DECISIONS:
        raise ValueError("Unsupported shadow UAT decision")
    assertions = payload.get("assertions")
    if not isinstance(assertions, dict) or not all(
        assertions.get(name) is True
        for name in ("comparedWithSource", "checkedChangedFields", "confirmedManualReview")
    ):
        raise ValueError("All shadow UAT assertions are required")
    note = str(payload.get("note", "")).strip()
    if len(note) > 1000:
        raise ValueError("Shadow UAT note is too long")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in note):
        raise ValueError("Shadow UAT note contains a control character")
    reviewed_at = _utc_now()
    path = _review_path(root)
    with _REVIEW_LOCK:
        store = _review_store(root)
        store.setdefault("schemaVersion", config["schemaVersion"])
        store["localOnly"] = True
        store.setdefault("reviews", {})[document_id] = {
            "decision": decision,
            "reviewedAt": reviewed_at,
            "reviewer": "local_user",
            "assertions": {
                "comparedWithSource": True,
                "checkedChangedFields": True,
                "confirmedManualReview": True,
            },
            "note": note,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "saved": True,
        "documentId": document_id,
        "decision": decision,
        "reviewedAt": reviewed_at,
    }
