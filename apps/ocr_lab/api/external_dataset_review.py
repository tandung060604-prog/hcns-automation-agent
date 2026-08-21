"""Local-only Ground Truth review queues for authorized local cohorts.

The review surface intentionally has no prediction reader.  It exposes source
documents and the private Ground Truth draft only; OCR/prediction output is not
part of this module or any of its responses.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import threading
import zipfile
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree

FIELD_SPECS: dict[str, tuple[str, ...]] = {
    "cv": (
        "full_name",
        "headline",
        "email",
        "phone_number",
        "address",
        "desired_role",
        "years_experience",
        "experience",
        "skills",
        "education",
    ),
    "contract": (
        "contract_number",
        "contract_sign_date",
        "effective_date",
        "probation_end_date",
        "employer_name",
        "employer_representative",
        "employee_name",
        "employee_id_number",
        "job_title",
        "workplace",
        "weekly_hours",
        "probation_salary_monthly",
        "allowances_summary",
        "salary_payment_schedule",
    ),
    "ielts": (
        "recipient_name",
        "credential_id",
        "credential_type",
        "overall_score",
        "issue_date",
    ),
}
IELTS_FIELD_SEMANTICS: dict[str, str] = {
    "recipient_name": (
        "Tên hiển thị trên chứng chỉ, giữ đúng thứ tự Family name + First name; "
        "không tự đảo tên."
    ),
    "credential_id": (
        "Mã TRF/credential in trên chứng chỉ; giữ nguyên chữ, số và dấu; "
        "không dùng số CCCD hay mã thí sinh khác."
    ),
    "credential_type": (
        "Loại giấy tờ/chứng chỉ được in trên tài liệu, ví dụ IELTS Test Report Form; "
        "không phải điểm tổng."
    ),
    "overall_score": (
        "Overall band score được in trên chứng chỉ, ví dụ 6.5; không thay bằng "
        "điểm Listening/Reading/Writing/Speaking."
    ),
    "issue_date": (
        "Ngày cấp/ngày phát hành được in trên chứng chỉ; không tự dùng ngày thi "
        "nếu tài liệu không ghi ngày cấp."
    ),
}
OUT_OF_SCOPE_REVIEW_FORMATS: dict[str, frozenset[str]] = {
    "cv": frozenset({"PLAIN_TEXT", "PPTX"}),
}
ALLOWED_SUFFIXES = {".txt", ".docx", ".png", ".jpg", ".jpeg", ".pdf", ".pptx"}
CASE_ID_RE = re.compile(r"^(?:cv|contract|ielts)-\d{3}$")
MAX_FIELD_LENGTH = 2000
MAX_PREVIEW_BYTES = 2 * 1024 * 1024
_WRITE_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
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


def _metadata_paths(
    root: Path,
    inventory_path: Path | None,
    ground_truth_path: Path | None,
) -> tuple[Path, Path]:
    root = root.resolve()
    inventory = (
        inventory_path.expanduser().resolve()
        if inventory_path is not None
        else root.parent / f"{root.name}-public-inventory.json"
    )
    ground_truth = (
        ground_truth_path.expanduser().resolve()
        if ground_truth_path is not None
        else root.parent / f"{root.name}-ground-truth-draft.json"
    )
    return inventory, ground_truth


def _require_local_dataset(
    root: Path,
    inventory_path: Path | None,
    ground_truth_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError("External dataset root is unavailable")
    if (root / ".git").exists():
        raise PermissionError("External dataset review requires a staging root without .git")
    if any((parent / ".git").exists() for parent in root.parents):
        raise PermissionError("External dataset review cannot run inside a Git worktree")
    inventory_file, ground_truth_file = _metadata_paths(root, inventory_path, ground_truth_path)
    if not inventory_file.is_file() or not ground_truth_file.is_file():
        raise FileNotFoundError("External dataset inventory or Ground Truth draft is unavailable")
    inventory = _load_json(inventory_file)
    draft = _load_json(ground_truth_file)
    records = inventory.get("cases")
    cases = draft.get("cases")
    if not isinstance(records, list) or not isinstance(cases, list) or len(records) != len(cases):
        raise ValueError("External dataset inventory and Ground Truth counts are inconsistent")
    inventory_by_id = {str(item.get("caseId")): item for item in records}
    if len(inventory_by_id) != len(records):
        raise ValueError("External dataset inventory contains duplicate case ids")
    for case in cases:
        case_id = str(case.get("caseId", ""))
        record = inventory_by_id.get(case_id)
        category = str(record.get("category", "")) if record else ""
        if not CASE_ID_RE.fullmatch(case_id) or record is None or category not in FIELD_SPECS:
            raise ValueError("External dataset case identity is invalid")
        expected = FIELD_SPECS[category]
        names = tuple(str(field.get("name", "")) for field in case.get("fields", []))
        if names != expected:
            raise ValueError(f"Ground Truth field contract mismatch for {case_id}")
        source = _source_path(root, record)
        expected_sha = str(record.get("sourceSha256", ""))
        actual_sha = f"sha256:{_sha256(source)}"
        if expected_sha and expected_sha != actual_sha:
            raise ValueError(f"Source digest mismatch for {case_id}")
    return inventory, draft, ground_truth_file


def _source_path(root: Path, record: dict[str, Any]) -> Path:
    relative = Path(str(record.get("sourceRelativePath", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe external dataset source path")
    candidates = [
        (root / relative).resolve(),
        (root / "sources" / relative).resolve(),
    ]
    source = next(
        (
            candidate
            for candidate in candidates
            if root.resolve() in candidate.parents and candidate.is_file()
        ),
        candidates[0],
    )
    if root.resolve() not in source.parents or not source.is_file():
        raise FileNotFoundError("External dataset source document is unavailable")
    if source.suffix.casefold() not in ALLOWED_SUFFIXES:
        raise ValueError("Unsupported external dataset source format")
    return source


def _case_maps(
    inventory: dict[str, Any], draft: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {str(item.get("caseId")): item for item in inventory.get("cases", [])},
        {str(item.get("caseId")): item for item in draft.get("cases", [])},
    )


def _is_reviewable(record: dict[str, Any]) -> bool:
    category = str(record.get("category", ""))
    source_format = str(record.get("sourceFormat", ""))
    return source_format not in OUT_OF_SCOPE_REVIEW_FORMATS.get(category, frozenset())


def _field_count(case: dict[str, Any]) -> int:
    return sum(
        1
        for field in case.get("fields", [])
        if str(field.get("reviewStatus", "")) == "CONFIRMED"
    )


def _dataset_status(draft: dict[str, Any]) -> str:
    dataset = draft.get("dataset", {})
    review = draft.get("review", {})
    if dataset.get("groundTruthStatus") == "SEALED" or review.get("status") == "CONFIRMED":
        return "SEALED"
    return str(dataset.get("groundTruthStatus", "DRAFT"))


def load_review_summary(
    root: Path,
    *,
    inventory_path: Path | None = None,
    ground_truth_path: Path | None = None,
) -> dict[str, Any]:
    """Return queue metadata while keeping predictions entirely out of scope."""
    inventory, draft, _ = _require_local_dataset(root, inventory_path, ground_truth_path)
    inventory_by_id, draft_by_id = _case_maps(inventory, draft)
    documents: list[dict[str, Any]] = []
    for case_id, record in inventory_by_id.items():
        case = draft_by_id[case_id]
        source = _source_path(root.resolve(), record)
        category = str(record.get("category", ""))
        fields = FIELD_SPECS[category]
        reviewable = _is_reviewable(record)
        documents.append(
            {
                "caseId": case_id,
                "category": category,
                "documentType": record.get("documentType"),
                "sourceFormat": record.get("sourceFormat"),
                "sourceFile": source.name,
                "pageCount": record.get("pageCount", case.get("pageCount", 1)),
                "previewAvailable": True,
                "reviewStatus": (
                    "OUT_OF_SCOPE"
                    if not reviewable
                    else "CONFIRMED" if _field_count(case) == len(fields) else "PENDING"
                ),
                "reviewedFieldCount": _field_count(case),
                "fieldCount": len(fields),
                "reviewable": reviewable,
                "scopeStatus": "ACTIVE" if reviewable else "OUT_OF_SCOPE",
            }
        )
    status = _dataset_status(draft)
    reviewable_documents = [item for item in documents if item["reviewable"]]
    return {
        "schemaVersion": "external-dataset-ground-truth-review/1.0.0",
        "datasetId": draft.get("dataset", {}).get("datasetId"),
        "datasetVersion": draft.get("dataset", {}).get("version"),
        "contentDigest": draft.get("dataset", {}).get("contentDigest"),
        "documentCount": len(documents),
        "pageCount": sum(int(item.get("pageCount", 0)) for item in documents),
        "fieldCount": sum(int(item["fieldCount"]) for item in documents),
        "reviewableDocumentCount": len(reviewable_documents),
        "reviewablePageCount": sum(int(item.get("pageCount", 0)) for item in reviewable_documents),
        "reviewableFieldCount": sum(int(item["fieldCount"]) for item in reviewable_documents),
        "groundTruthStatus": status,
        "reviewStatus": draft.get("review", {}).get("status", "PENDING"),
        "predictionsHiddenDuringReview": True,
        "localOnly": True,
        "documents": documents,
        "canLock": status not in {"SEALED", "APPROVED"}
        and bool(reviewable_documents)
        and all(
            item["reviewedFieldCount"] == item["fieldCount"]
            for item in reviewable_documents
        ),
    }


def _get_case(
    root: Path,
    case_id: str,
    inventory_path: Path | None,
    ground_truth_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    if not CASE_ID_RE.fullmatch(case_id):
        raise ValueError("Invalid external dataset case id")
    inventory, draft, _ = _require_local_dataset(root, inventory_path, ground_truth_path)
    inventory_by_id, draft_by_id = _case_maps(inventory, draft)
    if case_id not in inventory_by_id or case_id not in draft_by_id:
        raise FileNotFoundError("External dataset case not found")
    record = inventory_by_id[case_id]
    return inventory, draft, record, _source_path(root.resolve(), record)


def load_review_document(
    root: Path,
    case_id: str,
    *,
    inventory_path: Path | None = None,
    ground_truth_path: Path | None = None,
) -> dict[str, Any]:
    inventory, draft, record, source = _get_case(root, case_id, inventory_path, ground_truth_path)
    case = next(item for item in draft["cases"] if item.get("caseId") == case_id)
    category = str(record.get("category", ""))
    field_values = {
        str(field["name"]): {
            "value": field.get("value") if isinstance(field.get("value"), str) else None,
            "reviewStatus": field.get("reviewStatus", "PENDING"),
            "sensitive": bool(field.get("sensitive", False)),
        }
        for field in case.get("fields", [])
    }
    return {
        "schemaVersion": "external-dataset-ground-truth-review-document/1.0.0",
        "caseId": case_id,
        "category": category,
        "documentType": record.get("documentType"),
        "sourceFormat": record.get("sourceFormat"),
        "sourceFile": source.name,
        "pageCount": record.get("pageCount", case.get("pageCount", 1)),
        "reviewable": _is_reviewable(record),
        "scopeStatus": "ACTIVE" if _is_reviewable(record) else "OUT_OF_SCOPE",
        "fields": field_values,
        "reviewStatus": (
            "OUT_OF_SCOPE"
            if not _is_reviewable(record)
            else "CONFIRMED" if _field_count(case) == len(FIELD_SPECS[category]) else "PENDING"
        ),
        "predictionsHidden": True,
        "localOnly": True,
    }


def resolve_review_source(
    root: Path,
    case_id: str,
    *,
    inventory_path: Path | None = None,
    ground_truth_path: Path | None = None,
) -> Path:
    return _get_case(root, case_id, inventory_path, ground_truth_path)[3]


def _extract_xml_text(raw: bytes, *, prefix: str) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.startswith(prefix) and name.endswith(".xml")
        ]
        chunks: list[str] = []
        for name in sorted(names):
            root = ElementTree.fromstring(archive.read(name))
            parts = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
            if parts:
                chunks.append(" ".join("".join(parts).split()))
        return "\n\n".join(item for item in chunks if item)


def load_text_preview(path: Path) -> str:
    if path.stat().st_size > MAX_PREVIEW_BYTES:
        raise ValueError("Source preview is too large")
    suffix = path.suffix.casefold()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        return _extract_xml_text(path.read_bytes(), prefix="word/")
    if suffix == ".pptx":
        return _extract_xml_text(path.read_bytes(), prefix="ppt/slides/")
    raise ValueError("Source format does not have a text preview")


def save_review(
    root: Path,
    case_id: str,
    payload: dict[str, Any],
    *,
    inventory_path: Path | None = None,
    ground_truth_path: Path | None = None,
) -> dict[str, Any]:
    _, draft, record, _ = _get_case(root, case_id, inventory_path, ground_truth_path)
    if not _is_reviewable(record):
        raise ValueError("This source format is outside the active review scope")
    if _dataset_status(draft) in {"SEALED", "APPROVED"}:
        raise ValueError("Ground Truth is already sealed")
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("fields must be an object")
    category = case_id.split("-", 1)[0]
    expected = FIELD_SPECS[category]
    existing_case = next(item for item in draft["cases"] if item.get("caseId") == case_id)
    existing_fields = {
        str(item.get("name")): item for item in existing_case.get("fields", [])
    }
    if set(fields) != set(expected):
        raise ValueError("All and only the fields for this category must be supplied")
    reviewer = " ".join(str(payload.get("reviewer", "local_user")).split()).strip() or "local_user"
    if len(reviewer) > 200:
        raise ValueError("Reviewer name is too large")
    normalized: dict[str, dict[str, Any]] = {}
    for name in expected:
        item = fields[name]
        if not isinstance(item, dict):
            raise ValueError(f"Invalid field payload: {name}")
        value = item.get("value")
        if value is not None and not isinstance(value, str):
            raise ValueError("Ground Truth values must be text or null")
        value = " ".join(value.split()).strip() if isinstance(value, str) else None
        if value is not None and len(value) > MAX_FIELD_LENGTH:
            raise ValueError("Ground Truth field is too large")
        normalized[name] = {
            "name": name,
            "value": value,
            "reviewStatus": "CONFIRMED",
            "sensitive": bool(existing_fields.get(name, {}).get("sensitive", False)),
        }
    _, ground_truth_file = _metadata_paths(root, inventory_path, ground_truth_path)
    with _WRITE_LOCK:
        current = _load_json(ground_truth_file)
        if _dataset_status(current) in {"SEALED", "APPROVED"}:
            raise ValueError("Ground Truth is already sealed")
        current_case = next(item for item in current["cases"] if item.get("caseId") == case_id)
        current_case["fields"] = [normalized[name] for name in expected]
        current_case["reviewRequired"] = False
        current_case["reviewedAt"] = utc_now()
        current_case["reviewer"] = reviewer
        current.setdefault("review", {})["reviewer"] = reviewer
        current["review"]["status"] = "IN_PROGRESS"
        current["review"]["reviewedAt"] = utc_now()
        _write_json_atomic(ground_truth_file, current)
    return {
        "saved": True,
        "caseId": case_id,
        "reviewStatus": "CONFIRMED",
        "reviewedFieldCount": len(expected),
    }


def _coverage_decision_path(root: Path, decision_path: Path | None) -> Path:
    root = root.expanduser().resolve()
    path = (
        decision_path.expanduser().resolve()
        if decision_path is not None
        else root / "coverage-decision.json"
    )
    if path.parent != root:
        raise PermissionError("DATA-31 coverage decision must stay inside the private root")
    return path


def _load_coverage_decisions(
    root: Path,
    decision_path: Path | None,
    dataset_id: str,
) -> tuple[dict[str, Any], Path]:
    path = _coverage_decision_path(root, decision_path)
    if not path.is_file():
        return {
            "schemaVersion": "data31-ground-truth-coverage-decision/1.0.0",
            "datasetId": dataset_id,
            "status": "DRAFT",
            "cases": {},
        }, path
    payload = _load_json(path)
    if payload.get("schemaVersion") != "data31-ground-truth-coverage-decision/1.0.0":
        raise ValueError("DATA-31 coverage decision schema is invalid")
    if payload.get("datasetId") != dataset_id:
        raise ValueError("DATA-31 coverage decision dataset mismatch")
    if not isinstance(payload.get("cases"), dict):
        raise ValueError("DATA-31 coverage decision cases are invalid")
    return payload, path


def _missing_ground_truth_fields(case: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(field.get("name"))
        for field in case.get("fields", [])
        if field.get("value") is None or field.get("value") == ""
    )


def _field_is_sensitive(case: dict[str, Any], name: str) -> bool:
    return any(
        isinstance(field, dict)
        and field.get("name") == name
        and bool(field.get("sensitive", False))
        for field in case.get("fields", [])
    )


def load_coverage_summary(
    root: Path,
    *,
    inventory_path: Path | None = None,
    ground_truth_path: Path | None = None,
    decision_path: Path | None = None,
) -> dict[str, Any]:
    """Expose only DATA-31 missing-field slots and safe coverage metadata."""
    inventory, draft, _ = _require_local_dataset(root, inventory_path, ground_truth_path)
    decisions, _ = _load_coverage_decisions(
        root,
        decision_path,
        str(draft.get("dataset", {}).get("datasetId", "")),
    )
    inventory_by_id, draft_by_id = _case_maps(inventory, draft)
    documents: list[dict[str, Any]] = []
    missing_field_count = 0
    decided_field_count = 0
    out_of_scope_count = 0
    for case_id, record in inventory_by_id.items():
        case = draft_by_id[case_id]
        missing = _missing_ground_truth_fields(case)
        case_decisions = decisions.get("cases", {}).get(case_id, {})
        field_decisions = (
            case_decisions.get("fields", {}) if isinstance(case_decisions, dict) else {}
        )
        decided = [
            name
            for name in missing
            if isinstance(field_decisions.get(name), dict)
            and field_decisions[name].get("disposition") in {"GROUND_TRUTH", "OUT_OF_SCOPE"}
        ]
        out_of_scope_count += sum(
            1
            for name in decided
            if field_decisions[name].get("disposition") == "OUT_OF_SCOPE"
        )
        missing_field_count += len(missing)
        decided_field_count += len(decided)
        source = _source_path(root.resolve(), record)
        documents.append(
            {
                "caseId": case_id,
                "category": record.get("category"),
                "documentType": record.get("documentType"),
                "sourceFormat": record.get("sourceFormat"),
                "sourceFile": source.name,
                "pageCount": record.get("pageCount", case.get("pageCount", 1)),
                "previewAvailable": True,
                "reviewStatus": (
                    "NO_MISSING_GT"
                    if not missing
                    else "CONFIRMED" if len(decided) == len(missing) else "PENDING"
                ),
                "reviewedFieldCount": len(decided),
                "fieldCount": len(missing),
                "reviewable": True,
                "scopeStatus": "NO_MISSING_GT" if not missing else "ACTIVE",
            }
        )
    status = "COMPLETE" if decided_field_count == missing_field_count else "DRAFT"
    return {
        "schemaVersion": "data31-ground-truth-coverage-review/1.0.0",
        "datasetId": draft.get("dataset", {}).get("datasetId"),
        "datasetVersion": draft.get("dataset", {}).get("version"),
        "baselineGroundTruthStatus": draft.get("dataset", {}).get("groundTruthStatus"),
        "decisionStatus": status,
        "documentCount": len(documents),
        "fieldCount": missing_field_count,
        "missingFieldCount": missing_field_count,
        "decidedFieldCount": decided_field_count,
        "outOfScopeCount": out_of_scope_count,
        "groundTruthIsImmutable": True,
        "predictionsHiddenDuringReview": True,
        "localOnly": True,
        "ieltsSemantics": IELTS_FIELD_SEMANTICS,
        "documents": documents,
    }


def load_coverage_document(
    root: Path,
    case_id: str,
    *,
    inventory_path: Path | None = None,
    ground_truth_path: Path | None = None,
    decision_path: Path | None = None,
) -> dict[str, Any]:
    inventory, draft, record, source = _get_case(root, case_id, inventory_path, ground_truth_path)
    decisions, _ = _load_coverage_decisions(
        root,
        decision_path,
        str(draft.get("dataset", {}).get("datasetId", "")),
    )
    case = next(item for item in draft["cases"] if item.get("caseId") == case_id)
    missing = _missing_ground_truth_fields(case)
    case_decisions = decisions.get("cases", {}).get(case_id, {})
    field_decisions = case_decisions.get("fields", {}) if isinstance(case_decisions, dict) else {}
    fields = {
        name: {
            "value": (
                field_decisions[name].get("value")
                if isinstance(field_decisions.get(name), dict)
                and field_decisions[name].get("disposition") == "GROUND_TRUTH"
                else None
            ),
            "reviewStatus": (
                "CONFIRMED"
                if isinstance(field_decisions.get(name), dict)
                and field_decisions[name].get("disposition") in {"GROUND_TRUTH", "OUT_OF_SCOPE"}
                else "PENDING"
            ),
            "disposition": (
                field_decisions[name].get("disposition")
                if isinstance(field_decisions.get(name), dict)
                else None
            ),
            "sensitive": _field_is_sensitive(case, name),
        }
        for name in missing
    }
    complete = all(item["reviewStatus"] == "CONFIRMED" for item in fields.values())
    return {
        "schemaVersion": "data31-ground-truth-coverage-document/1.0.0",
        "caseId": case_id,
        "category": record.get("category"),
        "documentType": record.get("documentType"),
        "sourceFormat": record.get("sourceFormat"),
        "sourceFile": source.name,
        "pageCount": record.get("pageCount", case.get("pageCount", 1)),
        "fields": fields,
        "reviewStatus": "NO_MISSING_GT" if not missing else "CONFIRMED" if complete else "PENDING",
        "predictionsHidden": True,
        "localOnly": True,
        "groundTruthIsImmutable": True,
        "ieltsSemantics": IELTS_FIELD_SEMANTICS,
        "inventorySource": inventory.get("dataset", {}).get("datasetId"),
    }


def save_coverage_decision(
    root: Path,
    case_id: str,
    payload: dict[str, Any],
    *,
    inventory_path: Path | None = None,
    ground_truth_path: Path | None = None,
    decision_path: Path | None = None,
) -> dict[str, Any]:
    """Persist only the private decision overlay; never rewrite sealed Ground Truth."""
    inventory, draft, record, _ = _get_case(root, case_id, inventory_path, ground_truth_path)
    dataset_id = str(draft.get("dataset", {}).get("datasetId", ""))
    missing = _missing_ground_truth_fields(
        next(item for item in draft["cases"] if item.get("caseId") == case_id)
    )
    fields = payload.get("fields")
    if not isinstance(fields, dict) or set(fields) != set(missing):
        raise ValueError("All and only the missing DATA-31 fields must be supplied")
    reviewer = " ".join(str(payload.get("reviewer", "local_user")).split()).strip() or "local_user"
    if len(reviewer) > 200:
        raise ValueError("Reviewer name is too large")
    normalized: dict[str, dict[str, Any]] = {}
    for name in missing:
        item = fields[name]
        if not isinstance(item, dict):
            raise ValueError(f"Invalid coverage decision: {name}")
        disposition = item.get("disposition")
        value = item.get("value")
        if disposition not in {"GROUND_TRUTH", "OUT_OF_SCOPE"}:
            raise ValueError(f"Invalid coverage disposition: {name}")
        if value is not None and not isinstance(value, str):
            raise ValueError("Ground Truth values must be text or null")
        value = " ".join(value.split()).strip() if isinstance(value, str) else None
        if disposition == "GROUND_TRUTH" and not value:
            raise ValueError(f"Ground Truth is required for {name}")
        if disposition == "OUT_OF_SCOPE":
            value = None
        if value is not None and len(value) > MAX_FIELD_LENGTH:
            raise ValueError("Ground Truth field is too large")
        normalized[name] = {
            "value": value,
            "disposition": disposition,
            "reviewStatus": "CONFIRMED",
            "reviewedAt": utc_now(),
            "reviewer": reviewer,
        }
    with _WRITE_LOCK:
        current, path = _load_coverage_decisions(root, decision_path, dataset_id)
        current.setdefault("cases", {})[case_id] = {
            "category": record.get("category"),
            "sourceSha256": record.get("sourceSha256"),
            "fields": normalized,
        }
        current["reviewer"] = reviewer
        current["updatedAt"] = utc_now()
        missing_by_case = {
            str(case.get("caseId")): set(_missing_ground_truth_fields(case))
            for case in draft["cases"]
        }
        complete = all(
            set(case_data.get("fields", {})) == missing_by_case.get(case_id, set())
            and all(
                isinstance(field, dict)
                and field.get("disposition") in {"GROUND_TRUTH", "OUT_OF_SCOPE"}
                for field in case_data.get("fields", {}).values()
            )
            for case_id, case_data in current["cases"].items()
            if missing_by_case.get(case_id, set())
        ) and sum(len(names) for names in missing_by_case.values()) == sum(
            len(case_data.get("fields", {})) for case_data in current["cases"].values()
        )
        current["status"] = "COMPLETE" if complete else "DRAFT"
        _write_json_atomic(path, current)
    summary = load_coverage_summary(
        root,
        inventory_path=inventory_path,
        ground_truth_path=ground_truth_path,
        decision_path=decision_path,
    )
    return {
        "saved": True,
        "caseId": case_id,
        "decisionStatus": summary["decisionStatus"],
        "decidedFieldCount": summary["decidedFieldCount"],
        "missingFieldCount": summary["missingFieldCount"],
        "outOfScopeCount": summary["outOfScopeCount"],
    }


def lock_ground_truth(
    root: Path,
    *,
    confirm: bool,
    inventory_path: Path | None = None,
    ground_truth_path: Path | None = None,
    data23_manifest_path: Path | None = None,
    data23_prediction_lock_path: Path | None = None,
    data23_ground_truth_lock_path: Path | None = None,
) -> dict[str, Any]:
    if confirm is not True:
        raise ValueError("Explicit SEALED confirmation is required")
    inventory, draft, ground_truth_file = _require_local_dataset(
        root, inventory_path, ground_truth_path
    )
    if _dataset_status(draft) in {"SEALED", "APPROVED"}:
        raise ValueError("Ground Truth is already sealed")
    inventory_by_id, _ = _case_maps(inventory, draft)
    if any(
        _field_count(case)
        != len(FIELD_SPECS[str(case["caseId"]).split("-", 1)[0]])
        for case in draft["cases"]
        if _is_reviewable(inventory_by_id[str(case["caseId"])])
    ):
        raise ValueError("Every document and field must be confirmed before sealing")
    data23_paths = (
        data23_manifest_path,
        data23_prediction_lock_path,
        data23_ground_truth_lock_path,
    )
    if any(path is not None for path in data23_paths) and not all(
        path is not None for path in data23_paths
    ):
        raise ValueError("DATA-23 lock paths must be provided together")
    data23_lock_path = None
    data23_manifest_sha = None
    data23_prediction_sha = None
    if data23_manifest_path is not None:
        assert data23_prediction_lock_path is not None
        assert data23_ground_truth_lock_path is not None
        manifest_file = data23_manifest_path.expanduser().resolve(strict=True)
        prediction_lock_file = data23_prediction_lock_path.expanduser().resolve(strict=True)
        data23_lock_path = data23_ground_truth_lock_path.expanduser().resolve()
        manifest = _load_json(manifest_file)
        prediction_lock = _load_json(prediction_lock_file)
        data23_manifest_sha = "sha256:" + hashlib.sha256(
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if prediction_lock.get("manifestSha256") != data23_manifest_sha:
            raise ValueError("DATA-23 prediction lock manifest hash does not match")
        if prediction_lock.get("predictionsOpened") is not False:
            raise ValueError("DATA-23 prediction lock is already open")
        if prediction_lock.get("immutable") is not True:
            raise ValueError("DATA-23 prediction lock is not immutable")
        data23_prediction_sha = prediction_lock.get("predictionSha256")
        if not isinstance(data23_prediction_sha, str) or not data23_prediction_sha:
            raise ValueError("DATA-23 prediction lock is missing prediction hash")
    now = utc_now()
    with _WRITE_LOCK:
        current = _load_json(ground_truth_file)
        current.setdefault("dataset", {})["groundTruthStatus"] = "SEALED"
        current.setdefault("review", {})["status"] = "CONFIRMED"
        current["review"]["reviewer"] = str(current["review"].get("reviewer", "local_user"))
        current["review"]["reviewedAt"] = now
        current["review"]["predictionBlindness"] = True
        _write_json_atomic(ground_truth_file, current)
        lock_path = ground_truth_file.with_name(f"{ground_truth_file.stem}-SEALED.json")
        _write_json_atomic(
            lock_path,
            {
                "schemaVersion": "external-dataset-ground-truth-seal/1.0.0",
                "sealedAt": now,
                "datasetId": current.get("dataset", {}).get("datasetId"),
                "contentDigest": current.get("dataset", {}).get("contentDigest"),
                "fieldCount": sum(len(case.get("fields", [])) for case in current["cases"]),
                "predictionsOpened": False,
                "groundTruthSha256": f"sha256:{_sha256(ground_truth_file)}",
            },
        )
        if data23_lock_path is not None:
            _write_json_atomic(
                data23_lock_path,
                {
                    "schemaVersion": "data23-ground-truth-lock/1.0.0",
                    "manifestSha256": data23_manifest_sha,
                    "predictionSha256": data23_prediction_sha,
                    "groundTruthSha256": f"sha256:{_sha256(ground_truth_file)}",
                    "artifactPath": str(ground_truth_file),
                    "groundTruthStatus": "SEALED",
                    "reviewStatus": "CONFIRMED",
                    "predictionsOpened": False,
                    "immutable": True,
                },
            )
    result = {"locked": True, "groundTruthStatus": "SEALED", "predictionsOpened": False}
    if data23_ground_truth_lock_path is not None:
        result["data23GroundTruthLockPath"] = str(data23_ground_truth_lock_path)
    return result
