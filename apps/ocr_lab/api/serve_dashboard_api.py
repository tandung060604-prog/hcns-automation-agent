#!/usr/bin/env python3
"""Serve baseline results and local-only OCR sessions for the dashboard."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import cv2

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import pypdfium2 as pdfium
except ImportError:  # Evidence-only mode can run without PDF rendering.
    pdfium = None
from cccd_heldout_review import (
    evaluate_once as evaluate_cccd_ground_truth_once,
)
from cccd_heldout_review import (
    load_evaluation_document,
    load_review_document,
    load_review_summary,
    lock_ground_truth,
    resolve_review_source,
    set_review_disposition,
)
from cccd_heldout_review import (
    save_review as save_cccd_ground_truth_review,
)
from document_route_safety import (
    safe_existing_document_route,
    selected_orientations_are_identity,
)
from external_dataset_prediction import (
    PredictionArtifactError,
    load_prediction_document,
    load_prediction_summary,
    resolve_prediction_paths,
)
from external_dataset_review import (
    load_coverage_document as load_data31_coverage_document,
)
from external_dataset_review import (
    load_coverage_summary as load_data31_coverage_summary,
)
from external_dataset_review import (
    load_review_document as load_external_review_document,
)
from external_dataset_review import (
    load_review_summary as load_external_review_summary,
)
from external_dataset_review import (
    load_text_preview as load_external_text_preview,
)
from external_dataset_review import (
    lock_ground_truth as lock_external_ground_truth,
)
from external_dataset_review import (
    resolve_review_source as resolve_external_review_source,
)
from external_dataset_review import (
    save_coverage_decision as save_data31_coverage_decision,
)
from external_dataset_review import (
    save_review as save_external_review,
)
from external_dataset_typed import (
    TypedDatasetError,
    build_typed_export,
    load_typed_document,
    load_typed_summary,
    resolve_typed_paths,
)
from local_server_security import require_local_host_header, require_loopback_host
from mvp_demo_docs import render_leave_docx, render_leave_pdf
from mvp_demo_store import (
    APPLICATION_ID_RE,
    EVENT_QUEUE_CHANGED,
    ROLE_ADMIN,
    ROLE_HR,
    ROLE_USER,
    MvpDemoError,
    MvpDemoStore,
    build_public_user,
)
from template_result_comparison import compare_template_result

try:
    from paddleocr import PaddleOCR
except ImportError:  # Evidence-only mode can run while OCR env is repaired.
    PaddleOCR = None
from ocr_ho_v2_diagnostic import (
    document as load_ocr_ho_diagnostic_document,
)
from ocr_ho_v2_diagnostic import (
    preview as resolve_ocr_ho_diagnostic_preview,
)
from ocr_ho_v2_diagnostic import (
    save as save_ocr_ho_diagnostic,
)
from ocr_ho_v2_diagnostic import (
    summary as load_ocr_ho_diagnostic_summary,
)
from phase9_pipeline import (
    classify_document,
    enrich_result,
    prepare_routed_page,
    reading_order,
)
from phase10_review import review_payload, save_review
from phase11_8_shadow_uat import (
    load_shadow_document,
    load_shadow_summary,
    resolve_shadow_source,
    save_shadow_review,
)
from phase11_cccd import (
    OCR_HO_V2_VERSION,
    ORIENTATION_POLICY,
    SUPPORTED_ORIENTATIONS,
    extract_cccd_fields,
    is_identity_likely,
    orientation_diagnostics,
    prepare_identity_card_page,
    rotate_image,
)
from phase12_ingestion import (
    ingest_document,
    render_native_previews,
)
from phase14_review_store import save_line_review
from phase15_idp import (
    build_phase15_business_json,
    classify_phase15_document,
    extract_phase15_document,
)
from phase15_review import apply_phase15_field_review
from PIL import Image
from run_paddleocr_baseline import draw_ocr_boxes, jsonable
from run_paddleocr_phase7 import PROFILES, prepare_image
from upload_safety import validate_local_upload

from hcns_agent.application.ocr_scope import (
    ocr_allowed_for_document_type,
    ocr_scope_for,
)
from hcns_agent.domain.documents import SourceFormat
from hcns_agent.domain.errors import DocumentIntakeError
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.templates.compatibility import canonicalize_template_payload
from hcns_agent.templates.service import (
    LOCAL_TEMPLATE_RUNTIME_PROFILE,
    STAGE_TIMING_SCHEMA_VERSION,
    TemplateProcessingService,
    TemplateTechnicalError,
    TemplateUnsupportedError,
    build_local_template_processing_service,
    resolve_template_ocr_backend,
)


def _camunda_post(url: str, payload: dict[str, Any]) -> Any:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:  # nosec B310: local Camunda URL only
        body = response.read()
        return json.loads(body.decode("utf-8")) if body else None


def _camunda_get(url: str) -> Any:
    with urlopen(url, timeout=10) as response:  # nosec B310: local Camunda URL only
        return json.loads(response.read().decode("utf-8"))


def _camunda_value(variables: object, name: str) -> str | None:
    if not isinstance(variables, dict):
        return None
    value = variables.get(name)
    if not isinstance(value, dict) or not isinstance(value.get("value"), str):
        return None
    return value["value"]


def _queue_status_label(definition_key: str, *, viewer_is_hr: bool) -> str:
    if definition_key == "HRReview":
        return "Chờ HR duyệt" if viewer_is_hr else "HR đang xử lý"
    if definition_key == "UserReview":
        return "Chờ người nộp xác nhận" if viewer_is_hr else "Đang chờ xử lý"
    return "Đang xử lý"


def _claim_and_complete_camunda_task(
    engine_url: str,
    task_id: str,
    *,
    assignee: str,
    variable_name: str,
    decision: str,
) -> None:
    task = _camunda_get(f"{engine_url}/task/{task_id}")
    if not isinstance(task, dict):
        raise ValueError("Task is unavailable for this local demo role")
    current_assignee = task.get("assignee")
    if current_assignee != assignee:
        if current_assignee not in {None, ""}:
            _camunda_post(f"{engine_url}/task/{task_id}/unclaim", {})
        _camunda_post(
            f"{engine_url}/task/{task_id}/claim",
            {"userId": assignee},
        )
    _camunda_post(
        f"{engine_url}/task/{task_id}/complete",
        {
            "variables": {
                variable_name: {"value": decision, "type": "String"},
            }
        },
    )


def _demo_fast_forward_to_hr_review(engine_url: str, process_id: str) -> bool:
    """Skip UserReview in the MVP demo because the submit form already confirmed data.

    Keep this short: Camunda Parse may re-OCR and stall. MVP already has pending-HR
    fallback so submit should return quickly to the browser/tunnel.
    """
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        tasks = _camunda_get(
            f"{engine_url}/task?processInstanceId={process_id}"
        )
        if not isinstance(tasks, list):
            return False
        if any(
            isinstance(task, dict) and task.get("taskDefinitionKey") == "HRReview"
            for task in tasks
        ):
            return True
        user_tasks = [
            task
            for task in tasks
            if isinstance(task, dict) and task.get("taskDefinitionKey") == "UserReview"
        ]
        if user_tasks:
            task_id = user_tasks[0].get("id")
            if isinstance(task_id, str):
                _claim_and_complete_camunda_task(
                    engine_url,
                    task_id,
                    assignee="local-employee",
                    variable_name="userReviewDecision",
                    decision="UNRESOLVED",
                )
        time.sleep(0.35)
    tasks = _camunda_get(f"{engine_url}/task?processInstanceId={process_id}")
    return isinstance(tasks, list) and any(
        isinstance(task, dict) and task.get("taskDefinitionKey") == "HRReview"
        for task in tasks
    )


def _wait_for_camunda_task(
    engine_url: str,
    process_id: str,
    task_definition_key: str,
    *,
    timeout: float = 20.0,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        tasks = _camunda_get(f"{engine_url}/task?processInstanceId={process_id}")
        if isinstance(tasks, list):
            for task in tasks:
                if (
                    isinstance(task, dict)
                    and task.get("taskDefinitionKey") == task_definition_key
                ):
                    return task
        time.sleep(0.4)
    return None


def _safe_record_event(
    store: MvpDemoStore,
    application_id: str,
    event: str,
    detail: str,
    actor: str,
) -> None:
    if APPLICATION_ID_RE.fullmatch(application_id) is None:
        return
    try:
        store.record_event(application_id, event, detail, actor)
    except MvpDemoError:
        return


def _notify_hr_decision(
    store: MvpDemoStore,
    *,
    owner: str,
    decision: str,
    application_id: str,
    document_ref: str,
    note: str,
) -> None:
    summary = HR_DECISION_MESSAGES.get(decision, decision)
    message = f"{summary}{f' - {note}' if note else ''}"
    store.notify(
        owner,
        message,
        kind=decision,
        application_id=(
            application_id if APPLICATION_ID_RE.fullmatch(application_id) else ""
        ),
        document_id=document_ref,
    )


def _camunda_history_value(variables: object, name: str) -> str | None:
    if not isinstance(variables, list):
        return None
    for variable in variables:
        if (
            isinstance(variable, dict)
            and variable.get("name") == name
            and isinstance(variable.get("value"), str)
        ):
            return variable["value"]
    return None


def _local_camunda_url() -> str:
    return os.getenv("CAMUNDA_REST_URL", "http://127.0.0.1:8080/engine-rest").rstrip("/")


def _parse_cursor(raw: str) -> int:
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _read_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _file_digest(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _benchmark_evidence_metadata(
    report_path: Path | None,
    manifest_path: Path | None,
    report: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Expose only safe aggregate evidence metadata to the local UI."""

    return {
        "displayOnly": True,
        "reportConfigured": bool(report),
        "manifestConfigured": bool(manifest),
        "reportSchemaVersion": report.get("schemaVersion"),
        "datasetId": report.get("datasetId") or manifest.get("datasetId"),
        "reportDigest": _file_digest(report_path),
        "manifestDigest": _file_digest(manifest_path),
        # Aggregate evidence never grants a production promotion decision.
        # Even a stale/incorrect report claiming PASS is displayed as HOLD
        # until a separately approved production gate exists.
        "decision": "HOLD",
        "promotionAllowed": False,
        "containsRawFieldValues": report.get("containsRawFieldValues") is True,
        "groundTruthUsedForScoringOnly": report.get("groundTruthUsedForScoringOnly") is True,
    }


def _template_benchmark_row(
    key: str,
    label: str,
    runtime_types: set[str],
    runtime_counts: Counter[str],
) -> dict[str, Any]:
    if key in {"leave", "overtime"}:
        field_count = 49 if key == "leave" else 77
        note = (
            "15 mẫu native, chọn đúng template 15/15; field regression subset "
            "7 mẫu đạt 49/49 required field. OCR ảnh và PDF scan được đánh giá "
            "riêng theo benchmark gộp."
            if key == "leave"
            else "15 mẫu native, chọn đúng template 15/15; field regression subset "
            "7 mẫu đạt 77/77 required field. 7 field department không có trong "
            "nguồn được giữ null."
        )
        return {
            "key": key,
            "label": label,
            "benchmarkDocumentCount": 15,
            "benchmarkSampleCount": 7,
            "fieldCount": field_count,
            "exactMatchRate": 1.0,
            "fieldPresenceRate": 1.0,
            "acceptedRate": None,
            "acceptedLabel": None,
            "acceptedCoverage": None,
            "cer": None,
            "wer": None,
            "localDocumentCount": sum(runtime_counts.get(item, 0) for item in runtime_types),
            "status": "current",
            "source": "Template-first native regression",
            "note": note,
            "ocrAggregate": "OCR ảnh 86/90; PDF scan 82/90 ở UAT gộp hai loại.",
        }


def build_local_benchmark_summary(handler: type[DashboardHandler]) -> dict[str, Any]:
    runtime_counts: Counter[str] = Counter(
        str(session.get("documentType", ""))
        for session in handler.user_ocr.list_template_sessions()
    )
    rows = [
        _template_benchmark_row(
            "leave",
            "Đơn nghỉ phép",
            {"LEAVE_REQUEST"},
            runtime_counts,
        ),
        _template_benchmark_row(
            "overtime",
            "Đơn tăng ca",
            {"OVERTIME_REQUEST"},
            runtime_counts,
        ),
    ]

    benchmark_payload = _read_optional_json(handler.benchmark_report) or {}
    benchmark_manifest = _read_optional_json(handler.benchmark_manifest) or {}
    inventory_counts: Counter[str] = Counter(
        str(case.get("category", ""))
        for case in benchmark_manifest.get("cases", [])
        if isinstance(case, dict)
    )
    prediction_inventory = _read_optional_json(handler.external_dataset_inventory) or {}
    prediction_inventory_counts: Counter[str] = Counter(
        str(case.get("category", ""))
        for case in prediction_inventory.get("cases", [])
        if isinstance(case, dict)
    )
    category_specs = [
        ("cv", "CV & hồ sơ ứng viên", "CV", {"CV"}),
        ("contract", "Hợp đồng lao động", "EMPLOYMENT_CONTRACT", {"EMPLOYMENT_CONTRACT"}),
        ("ielts", "IELTS / chứng chỉ", "CERTIFICATE", {"CERTIFICATE"}),
    ]
    by_category = benchmark_payload.get("byCategory", {})
    for category, label, runtime_type, _ in category_specs:
        metrics = by_category.get(category, {})
        has_metrics = isinstance(metrics, dict) and bool(metrics)
        prediction_only_count = prediction_inventory_counts.get(category, 0)
        local_count = (
            prediction_only_count
            if prediction_only_count
            else runtime_counts.get(runtime_type, 0)
        )
        prediction_only = not has_metrics and prediction_only_count > 0
        rows.append(
            {
                "key": category,
                "label": label,
                "benchmarkDocumentCount": inventory_counts.get(category, 0),
                "benchmarkSampleCount": inventory_counts.get(category, 0),
                "fieldCount": metrics.get("fields") if has_metrics else None,
                "exactMatchRate": metrics.get("exactRate") if has_metrics else None,
                "fieldPresenceRate": metrics.get("presenceRate") if has_metrics else None,
                "acceptedRate": metrics.get("acceptedRate") if has_metrics else None,
                "acceptedLabel": "accepted match" if has_metrics else None,
                "acceptedCoverage": None,
                "cer": None,
                "wer": None,
                "localDocumentCount": local_count,
                "status": (
                    "current"
                    if has_metrics
                    else ("prediction-only" if prediction_only else "unavailable")
                ),
                "source": (
                    "DATA-29 development aggregate · Ground Truth SEALED"
                    if has_metrics
                    else (
                        "DATA-22 development · prediction-only"
                        if prediction_only
                        else "Benchmark field-level mới"
                    )
                ),
                "note": (
                    "Đánh giá field-level; CER/WER chưa có trong báo cáo này."
                    if has_metrics
                    else (
                        f"{local_count} tài liệu local prediction-only; "
                        "Ground Truth chưa cung cấp nên chưa tính exact/presence."
                        if prediction_only
                        else "Chưa cấu hình báo cáo prediction có Ground Truth."
                    )
                ),
            }
        )

    cccd_count = 0
    cccd_summary = None
    if handler.cccd_heldout_root is not None:
        cccd_summary = load_review_summary(handler.cccd_heldout_root)
        cccd_count = int(cccd_summary.get("documentCount", 0))
    cccd_metrics = (
        cccd_summary.get("evaluation", {}).get("metrics", {}).get("phase11_6", {})
        if cccd_summary
        else {}
    )
    if not isinstance(cccd_metrics, dict):
        cccd_metrics = {}
    rows.append(
        {
            "key": "cccd-front",
            "label": "CCCD mặt trước",
            "benchmarkDocumentCount": cccd_count,
            "benchmarkSampleCount": cccd_count,
            "fieldCount": cccd_metrics.get("evaluatedFieldCount"),
            "exactMatchRate": cccd_metrics.get("strictFieldExactMatch"),
            "fieldPresenceRate": cccd_metrics.get("fieldPresence"),
            "acceptedRate": cccd_metrics.get("acceptedPrecision"),
            "acceptedLabel": "precision",
            "acceptedCoverage": cccd_metrics.get("acceptedCoverage"),
            "cer": cccd_metrics.get("cer"),
            "wer": None,
            "localDocumentCount": cccd_count,
            "status": "confirmed" if cccd_count else "unavailable",
            "source": "Đánh giá CCCD local đã xác nhận",
            "note": (
                f"{cccd_count} mặt trước trong metric; "
                f"{cccd_summary.get('excludedDocumentCount', 0)} tài liệu ngoài phạm vi."
                if cccd_summary
                else "Chưa cấu hình bộ CCCD Ground Truth."
            ),
        }
    )

    aggregate_categories = [
        metrics
        for category in ("contract", "cv", "ielts")
        if isinstance((metrics := by_category.get(category)), dict) and metrics
    ]
    aggregate_field_count = sum(int(metrics.get("fields", 0)) for metrics in aggregate_categories)
    development_aggregate = {
        "label": "DATA-29",
        "scope": "DEVELOPMENT_AGGREGATE",
        "fieldCount": aggregate_field_count,
        "exactFieldCount": sum(
            round(int(metrics.get("fields", 0)) * float(metrics.get("exactRate", 0.0)))
            for metrics in aggregate_categories
        ),
        "acceptedFieldCount": sum(
            round(
                int(metrics.get("fields", 0))
                * float(metrics.get("acceptedRate", metrics.get("exactRate", 0.0)))
            )
            for metrics in aggregate_categories
        ),
        "matchingPolicyVersion": (
            benchmark_payload.get("matchingPolicyVersion")
            or benchmark_payload.get("matchingPolicy", {}).get("version")
        ),
        "decision": "HOLD",
        "promotionAllowed": False,
        "displayOnly": True,
    }

    return {
        "schemaVersion": "local-document-benchmark/1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "evidence": _benchmark_evidence_metadata(
            handler.benchmark_report,
            handler.benchmark_manifest,
            benchmark_payload,
            benchmark_manifest,
        ),
        "developmentAggregate": development_aggregate,
        "rows": [
            next(row for row in rows if row["key"] == key)
            for key in ("cv", "contract", "ielts", "cccd-front", "leave", "overtime")
        ],
        "notes": [
            "Số benchmark là số tài liệu gốc duy nhất; số lượt chạy chỉ tính thêm biến thể ảnh nếu có.",
            "Số local là số tài liệu hiện có trong runtime hoặc hàng review; không thay thế mẫu số benchmark.",
            "CER/WER chỉ hiển thị khi nguồn đã tính hai chỉ số này; trạng thái chưa có không có nghĩa là 0.",
            "Nghỉ phép và tăng ca dùng benchmark Template-first native; OCR ảnh và PDF scan là UAT gộp hai loại, chưa tách điểm theo từng loại.",
        ],
    }

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_REVIEW_BYTES = 2 * 1024 * 1024
MAX_PDF_PAGES = 50
CAMUNDA_UPLOAD_DOCUMENT_TYPES = frozenset(
    {
        "LEAVE_REQUEST",
        "OVERTIME_REQUEST",
        "CV",
        "CERTIFICATE",
        "EMPLOYMENT_CONTRACT",
        "IDENTITY_CARD",
    }
)
DOCUMENT_TYPE_LABELS = {
    "LEAVE_REQUEST": "Đơn xin nghỉ phép",
    "OVERTIME_REQUEST": "Đơn xin tăng ca",
    "CV": "Hồ sơ ứng viên CV",
    "CERTIFICATE": "Chứng chỉ",
    "EMPLOYMENT_CONTRACT": "Hợp đồng lao động",
    "IDENTITY_CARD": "Căn cước công dân",
}
SSE_HEARTBEAT_SECONDS = 15.0
SSE_MAX_STREAM_SECONDS = 600.0
SSE_RETRY_MS = 3000
HR_DECISION_MESSAGES = {
    "CONFIRMED": "HR đã duyệt đơn của bạn",
    "REQUEST_REUPLOAD": "HR yêu cầu nộp lại tài liệu",
    "REJECTED": "HR đã từ chối đơn của bạn",
}
TEMPLATE_RESULT_HIDDEN_FIELDS = frozenset(
    {
        "missingFields",
        "validationErrors",
        "confidence",
        "recommendedAction",
        "documentId",
        "documentType",
        "templateId",
        "templateVersion",
        "documentTitle",
        "sourceFile",
        "schemaVersion",
    }
)
CAMUNDA_PROCESS_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{1,128}\Z")
TEMPLATE_ALLOWED_EXTENSIONS = {
    ".docx",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
}
ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".docx",
    ".xlsx",
}
SESSION_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
PHASE14_CASE_ID_RE = re.compile(r"^[0-9a-f]{20}$")
PHASE14_PROFILE_RE = re.compile(r"^[a-z0-9_]{1,80}$")


def build_index(native_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in native_root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            sample_id = payload.get("sampleId")
            if isinstance(sample_id, str) and sample_id:
                index[sample_id] = path
        except (OSError, json.JSONDecodeError):
            continue
    return index


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_phase11_5_crop(
    data_root: Path,
    session_dir: Path,
    field_name: str,
    variant_name: str,
) -> Path | None:
    """Resolve a Phase 11.5 crop without allowing evidence paths outside private data."""
    session_crop = (
        session_dir / "phase11_5" / "crops" / f"{field_name}_{variant_name}.png"
    )
    if session_crop.is_file():
        return session_crop

    evidence_path = session_dir / "phase11_5" / "field_consensus.json"
    if not evidence_path.is_file():
        return None
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        raw_path = (
            evidence.get("crops", {})
            .get(field_name, {})
            .get(variant_name, {})
            .get("path")
        )
    except (AttributeError, json.JSONDecodeError, OSError):
        return None
    if not raw_path:
        return None

    candidate_path = Path(str(raw_path)).resolve()
    private_root = data_root.resolve()
    if candidate_path.is_file() and private_root in candidate_path.parents:
        return candidate_path
    return None


def deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = " ".join(value.split())
        if normalized and normalized.casefold() not in seen:
            seen.add(normalized.casefold())
            output.append(normalized)
    return output


def extracted_fields_from_template_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return scalar business fields extracted/corrected from a template session."""
    raw = result.get("data")
    if not isinstance(raw, dict):
        raw = result.get("structuredFields")
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or key in TEMPLATE_RESULT_HIDDEN_FIELDS:
            continue
        if isinstance(value, bool) or value is None:
            cleaned[key] = value
        elif isinstance(value, (str, int, float)):
            cleaned[key] = value
    return cleaned


def extract_candidates(text: str) -> dict[str, list[str]]:
    return {
        "emails": deduplicate(re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)),
        "phoneNumbers": deduplicate(
            re.findall(r"(?<!\d)(?:\+?84|0)(?:[\s.\-]?\d){8,10}(?!\d)", text)
        ),
        "dates": deduplicate(re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)),
        "identityNumberCandidates": deduplicate(re.findall(r"(?<!\d)\d{9,12}(?!\d)", text)),
        "employeeCodeCandidates": deduplicate(
            re.findall(r"\b(?:NV|EMP|MSNV)[\s\-:]?[A-Z0-9]{3,12}\b", text, re.I)
        ),
    }


def rescale_boxes(boxes: list[Any], scale: int) -> list[Any]:
    if scale == 1:
        return boxes
    return [
        [[round(float(point[0]) / scale, 3), round(float(point[1]) / scale, 3)] for point in box]
        for box in boxes
    ]


class UserOCRService:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.sessions_root = data_root / "user_uploads" / "sessions"
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self._ocr: PaddleOCR | None = None
        self._lock = threading.Lock()

    @property
    def model_loaded(self) -> bool:
        return self._ocr is not None

    def get_ocr(self) -> PaddleOCR:
        if PaddleOCR is None:
            raise RuntimeError(
                "PaddleOCR runtime is unavailable; evidence remains readable "
                "but new OCR processing is disabled."
            )
        if self._ocr is None:
            profile = PROFILES["v5_enhanced"]
            self._ocr = PaddleOCR(
                text_detection_model_name=profile["textDetection"],
                text_recognition_model_name=profile["textRecognition"],
                device="cpu",
                enable_mkldnn=False,
                cpu_threads=4,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                text_det_limit_side_len=1600,
                text_det_limit_type="max",
                text_det_box_thresh=0.45,
                text_rec_score_thresh=0.0,
            )
        return self._ocr

    def session_dir(self, session_id: str) -> Path | None:
        if not SESSION_ID_RE.fullmatch(session_id):
            return None
        path = self.sessions_root / session_id
        return path if path.is_dir() else None

    def render_pages(self, input_path: Path, pages_dir: Path) -> list[Path]:
        pages_dir.mkdir(parents=True, exist_ok=True)
        if input_path.suffix.lower() == ".pdf":
            if pdfium is None:
                raise RuntimeError("PDF rendering is unavailable in evidence-only mode.")
            document = pdfium.PdfDocument(input_path)
            try:
                if len(document) > MAX_PDF_PAGES:
                    raise ValueError(f"PDF exceeds {MAX_PDF_PAGES} pages")
                if len(document) == 0:
                    raise ValueError("PDF has no pages")
                output: list[Path] = []
                for page_index in range(len(document)):
                    output_path = pages_dir / f"page_{page_index:03d}.png"
                    page = document[page_index]
                    try:
                        page.render(scale=2.0).to_pil().convert("RGB").save(output_path)
                    finally:
                        page.close()
                    output.append(output_path)
                return output
            finally:
                document.close()

        output_path = pages_dir / "page_000.png"
        with Image.open(input_path) as image:
            image.convert("RGB").save(output_path)
        return [output_path]

    def predict_page(
        self,
        page_path: Path,
        visualization_path: Path | None,
    ) -> dict[str, Any]:
        prepared, preprocessing = prepare_image(page_path)
        started = time.perf_counter()
        predictions = list(
            self.get_ocr().predict(
                prepared,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                text_det_limit_side_len=1600,
                text_det_limit_type="max",
                text_det_box_thresh=0.45,
                text_rec_score_thresh=0.0,
            )
        )
        duration_ms = round((time.perf_counter() - started) * 1000)
        texts: list[str] = []
        scores: list[float] = []
        boxes: list[Any] = []
        for prediction in predictions:
            texts.extend(str(value) for value in prediction.get("rec_texts", []))
            scores.extend(float(value) for value in prediction.get("rec_scores", []))
            boxes.extend(jsonable(prediction.get("rec_polys", [])))
        boxes = rescale_boxes(boxes, int(preprocessing["adaptiveUpscale"]))
        if visualization_path is not None:
            visualization_path.parent.mkdir(parents=True, exist_ok=True)
        if boxes and visualization_path is not None:
            draw_ocr_boxes(page_path, boxes, visualization_path)
        return {
            "recognizedTexts": texts,
            "recognizedText": "\n".join(texts),
            "recognitionScores": scores,
            "recognizedBoxes": boxes,
            "avgConfidence": round(sum(scores) / len(scores), 6) if scores else None,
            "durationMs": duration_ms,
            "preprocessing": preprocessing,
            "visualizationAvailable": bool(boxes and visualization_path is not None),
        }

    def apply_phase9(
        self,
        result: dict[str, Any],
        page_paths: list[Path],
        session_dir: Path,
    ) -> dict[str, Any]:
        phase9_started = time.perf_counter()
        raw_text = result.get("phase9", {}).get("rawOcr", {}).get("pages")
        if raw_text:
            classification_text = "\n".join(
                text for page in raw_text for text in page.get("recognizedTexts", [])
            )
        else:
            classification_text = result["document"].get("rawRecognizedText") or result[
                "document"
            ].get("recognizedText", "")
        document_type, _, _ = classify_document(
            classification_text, result["source"].get("format", "")
        )
        routed_pages: list[dict[str, Any]] = []
        route_metadata: list[dict[str, Any] | None] = []
        for page_index, page_path in enumerate(page_paths):
            routed_path = session_dir / "phase9" / "pages" / f"page_{page_index:03d}.png"
            metadata = prepare_routed_page(page_path, document_type, routed_path)
            route_metadata.append(metadata)
            if metadata is None:
                continue
            page_result = self.predict_page(
                routed_path,
                session_dir / "phase9" / "visualization" / f"page_{page_index:03d}.png",
            )
            page_result["pageIndex"] = page_index
            routed_pages.append(page_result)
        enriched = enrich_result(
            result,
            routed_pages=routed_pages or None,
            preprocessing=route_metadata,
        )
        enriched["processing"]["phase9DurationMs"] = round(
            (time.perf_counter() - phase9_started) * 1000
        )
        return enriched

    def apply_phase11(
        self,
        result: dict[str, Any],
        page_paths: list[Path],
        session_dir: Path,
    ) -> dict[str, Any]:
        phase_started = time.perf_counter()
        raw_pages = result.get("phase9", {}).get("rawOcr", {}).get("pages") or result.get(
            "document", {}
        ).get("pages", [])
        candidate_root = session_dir / "phase11" / "orientation_candidates"
        oriented_root = session_dir / "phase11" / "oriented"
        candidate_root.mkdir(parents=True, exist_ok=True)
        oriented_root.mkdir(parents=True, exist_ok=True)

        provisional_pages: list[dict[str, Any]] = []
        oriented_paths: list[Path] = []
        orientation_pages: list[dict[str, Any]] = []
        for page_index, page_path in enumerate(page_paths):
            image = cv2.imread(str(page_path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Cannot read rendered page for Phase 11")
            candidate_records: list[tuple[dict[str, Any], dict[str, Any], Path]] = []
            for rotation_degrees in SUPPORTED_ORIENTATIONS:
                if rotation_degrees == 0:
                    candidate_path = page_path
                    if page_index < len(raw_pages):
                        candidate_page = raw_pages[page_index]
                    else:
                        candidate_page = self.predict_page(candidate_path, None)
                    candidate_image = image
                else:
                    candidate_image = rotate_image(image, rotation_degrees)
                    candidate_path = (
                        candidate_root / f"page_{page_index:03d}_rot_{rotation_degrees:03d}.png"
                    )
                    if not cv2.imwrite(str(candidate_path), candidate_image):
                        raise OSError("Cannot write Phase 11 orientation candidate")
                    candidate_page = self.predict_page(candidate_path, None)
                candidate_page = dict(candidate_page)
                candidate_page["pageIndex"] = page_index
                diagnostic = orientation_diagnostics(
                    candidate_page,
                    rotation_degrees,
                    (candidate_image.shape[1], candidate_image.shape[0]),
                )
                candidate_records.append((candidate_page, diagnostic, candidate_path))

            selected_page, selected_diagnostic, selected_path = candidate_records[0]

            oriented_path = oriented_root / f"page_{page_index:03d}.png"
            selected_image = cv2.imread(str(selected_path), cv2.IMREAD_COLOR)
            if selected_image is None or not cv2.imwrite(str(oriented_path), selected_image):
                raise OSError("Cannot write Phase 11 oriented page")
            provisional_pages.append(selected_page)
            oriented_paths.append(oriented_path)
            orientation_pages.append(
                {
                    "pageIndex": page_index,
                    "selectedRotationDegrees": int(selected_diagnostic["rotationDegrees"]),
                    "orientationPolicy": ORIENTATION_POLICY,
                    "supportedOrientations": list(SUPPORTED_ORIENTATIONS),
                    "selectionScore": selected_diagnostic["score"],
                    "identityLikely": is_identity_likely(selected_diagnostic),
                    "selectedIdentityLikely": is_identity_likely(selected_diagnostic),
                    "candidates": [record[1] for record in candidate_records],
                }
            )

        classification_text = "\n".join(
            text for page in provisional_pages for text in page.get("recognizedTexts", [])
        )
        document_type, route_confidence, route_evidence = classify_document(
            classification_text,
            result.get("source", {}).get("format", ""),
        )
        # Rejected 90/180/270-degree candidates can hallucinate a date label
        # beside a long number on a CV. They remain useful diagnostics but must
        # never route the selected document as an identity card.
        identity_likely = selected_orientations_are_identity(orientation_pages)
        if identity_likely:
            document_type = "IDENTITY_DOCUMENT"

        if document_type != "IDENTITY_DOCUMENT":
            result["phase11"] = {
                "version": OCR_HO_V2_VERSION,
                "status": "NOT_APPLICABLE",
                "recognizerVersion": OCR_HO_V2_VERSION,
                "orientationPolicy": ORIENTATION_POLICY,
                "evaluationScope": "DEVELOPMENT_ONLY",
                "documentRoute": {
                    "type": document_type,
                    "confidence": route_confidence,
                    "evidence": route_evidence,
                },
                "orientation": {
                    "strategy": ORIENTATION_POLICY,
                    "supportedOrientations": list(SUPPORTED_ORIENTATIONS),
                    "pages": orientation_pages,
                },
                "identityCard": None,
                "durationMs": round((time.perf_counter() - phase_started) * 1000),
            }
            return result

        canonical_root = session_dir / "phase11" / "canonical"
        selected_root = session_dir / "phase11" / "pages"
        visualization_root = session_dir / "phase11" / "visualization"
        canonical_root.mkdir(parents=True, exist_ok=True)
        selected_root.mkdir(parents=True, exist_ok=True)
        visualization_root.mkdir(parents=True, exist_ok=True)
        phase11_pages: list[dict[str, Any]] = []
        canonicalization: list[dict[str, Any]] = []
        selected_variants: list[str] = []
        all_scores: list[float] = []
        for page_index, oriented_path in enumerate(oriented_paths):
            canonical_path = canonical_root / f"page_{page_index:03d}.png"
            canonical_metadata = prepare_identity_card_page(
                oriented_path,
                canonical_path,
            )
            canonical_page = self.predict_page(canonical_path, None)
            canonical_page["pageIndex"] = page_index
            canonical_image = cv2.imread(str(canonical_path), cv2.IMREAD_COLOR)
            if canonical_image is None:
                raise ValueError("Cannot read canonical Phase 11 page")
            canonical_diagnostic = orientation_diagnostics(
                canonical_page,
                0,
                (canonical_image.shape[1], canonical_image.shape[0]),
            )
            oriented_page = provisional_pages[page_index]
            oriented_diagnostic = next(
                candidate
                for candidate in orientation_pages[page_index]["candidates"]
                if candidate["rotationDegrees"]
                == orientation_pages[page_index]["selectedRotationDegrees"]
            )
            use_canonical = bool(
                canonical_metadata["perspectiveCorrected"]
                and float(canonical_diagnostic["score"])
                >= float(oriented_diagnostic["score"]) - 0.10
            )
            if not canonical_metadata["perspectiveCorrected"]:
                use_canonical = (
                    float(canonical_diagnostic["score"])
                    >= float(oriented_diagnostic["score"]) + 0.05
                )
            selected_page = canonical_page if use_canonical else oriented_page
            selected_source = canonical_path if use_canonical else oriented_path
            selected_variant = "phase11_canonical" if use_canonical else "phase11_oriented"
            selected_variants.append(selected_variant)
            selected_path = selected_root / f"page_{page_index:03d}.png"
            selected_image = cv2.imread(str(selected_source), cv2.IMREAD_COLOR)
            if selected_image is None or not cv2.imwrite(str(selected_path), selected_image):
                raise OSError("Cannot write selected Phase 11 page")
            selected_boxes = selected_page.get("recognizedBoxes", [])
            visualization_path = visualization_root / f"page_{page_index:03d}.png"
            if selected_boxes:
                draw_ocr_boxes(selected_path, selected_boxes, visualization_path)
            selected_page["visualizationAvailable"] = bool(selected_boxes)
            ordered, strategy = reading_order(
                selected_page.get("recognizedTexts", []),
                selected_page.get("recognitionScores", []),
                selected_boxes,
                "IDENTITY_DOCUMENT",
                int(selected_image.shape[1]),
            )
            for output_index, line in enumerate(ordered):
                line["outputIndex"] = output_index
                line["correctedText"] = line["rawText"]
                line["correctionApplied"] = False
                line["correctionMethod"] = None
                line["warning"] = (
                    "LOW_CONFIDENCE"
                    if line.get("confidence") is not None and float(line["confidence"]) < 0.80
                    else None
                )
                line.pop("centerX", None)
                line.pop("centerY", None)
            page_scores = [
                float(line["confidence"]) for line in ordered if line.get("confidence") is not None
            ]
            all_scores.extend(page_scores)
            phase11_pages.append(
                {
                    "pageIndex": page_index,
                    "selectedVariant": selected_variant,
                    "readingOrderStrategy": strategy,
                    "recognizedTexts": [line["rawText"] for line in ordered],
                    "recognitionScores": [line.get("confidence") for line in ordered],
                    "recognizedBoxes": [line.get("box", []) for line in ordered],
                    "lines": ordered,
                    "rawText": "\n".join(line["rawText"] for line in ordered),
                }
            )
            canonicalization.append(
                {
                    "pageIndex": page_index,
                    **canonical_metadata,
                    "canonicalOcrScore": canonical_diagnostic["score"],
                    "orientedOcrScore": oriented_diagnostic["score"],
                    "selectedVariant": selected_variant,
                }
            )

        identity_card = extract_cccd_fields(
            phase11_pages,
            engine="PaddleOCR/PP-OCRv5",
        )
        result["schemaVersion"] = "3.0.0"
        result["document"]["documentType"] = "IDENTITY_DOCUMENT"
        result["document"]["recognizedText"] = "\n".join(page["rawText"] for page in phase11_pages)
        result["document"]["recognizedTextLineCount"] = sum(
            len(page["lines"]) for page in phase11_pages
        )
        result["document"]["avgConfidence"] = (
            round(sum(all_scores) / len(all_scores), 6) if all_scores else None
        )
        result["document"]["structuredFields"] = identity_card["fields"]
        result["phase11"] = {
            "version": OCR_HO_V2_VERSION,
            "status": "NEEDS_REVIEW",
            "recognizerVersion": OCR_HO_V2_VERSION,
            "orientationPolicy": ORIENTATION_POLICY,
            "evaluationScope": "DEVELOPMENT_ONLY",
            "documentRoute": {
                "type": "IDENTITY_DOCUMENT",
                "confidence": route_confidence,
                "evidence": route_evidence,
            },
            "orientation": {
                "strategy": ORIENTATION_POLICY,
                "supportedOrientations": list(SUPPORTED_ORIENTATIONS),
                "pages": orientation_pages,
            },
            "canonicalization": canonicalization,
            "selectedVariants": selected_variants,
            "pages": phase11_pages,
            "identityCard": identity_card,
            "durationMs": round((time.perf_counter() - phase_started) * 1000),
        }
        result["processing"]["phase11Version"] = OCR_HO_V2_VERSION
        result["processing"]["orientationPolicy"] = ORIENTATION_POLICY
        result["processing"]["phase11DurationMs"] = result["phase11"]["durationMs"]
        identity_output = {
            "schemaVersion": identity_card["schemaVersion"],
            "recognizerVersion": OCR_HO_V2_VERSION,
            "orientationPolicy": ORIENTATION_POLICY,
            "evaluationScope": "DEVELOPMENT_ONLY",
            "sessionId": result["sessionId"],
            "createdAt": utc_now(),
            "containsRealPII": True,
            **identity_card,
        }
        identity_path = session_dir / "phase11" / "identity_card.json"
        identity_path.write_text(
            json.dumps(identity_output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result

    def apply_phase15(
        self,
        result: dict[str, Any],
        input_path: Path,
        session_dir: Path,
        canonical_document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        phase_started = time.perf_counter()
        if canonical_document is None:
            ocr_pages = result.get("phase9", {}).get("rawOcr", {}).get("pages") or result.get(
                "document", {}
            ).get("pages", [])
            canonical_document = ingest_document(input_path, ocr_pages)
        existing_route = safe_existing_document_route(
            result.get("document", {}).get("documentType"),
            str(canonical_document.get("plainText") or ""),
        )
        classification = classify_phase15_document(
            canonical_document,
            existing_route,
        )
        extraction = extract_phase15_document(
            canonical_document,
            classification,
        )
        business_json = build_phase15_business_json(
            result["sessionId"],
            canonical_document,
            classification,
            extraction,
            contains_real_pii=True,
            result_reference="phase15/idp_result.json",
        )
        duration_ms = round((time.perf_counter() - phase_started) * 1000)
        phase15_dir = session_dir / "phase15"
        phase15_dir.mkdir(parents=True, exist_ok=True)
        canonical_path = phase15_dir / "canonical_document.json"
        business_path = phase15_dir / "business.json"
        idp_path = phase15_dir / "idp_result.json"
        canonical_path.write_text(
            json.dumps(
                {
                    "sessionId": result["sessionId"],
                    "createdAt": utc_now(),
                    "containsRealPII": True,
                    **canonical_document,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        business_path.write_text(
            json.dumps(business_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        idp_result = {
            "schemaVersion": "2.0.0",
            "sessionId": result["sessionId"],
            "createdAt": utc_now(),
            "containsRealPII": True,
            "classification": classification,
            "extraction": extraction,
            "ingestion": {
                "sourceFormat": canonical_document["sourceFormat"],
                "mode": canonical_document["ingestionMode"],
                "adapter": canonical_document["adapter"],
                "pageCount": canonical_document["pageCount"],
            },
            "businessJson": "phase15/business.json",
        }
        idp_path.write_text(
            json.dumps(idp_result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["schemaVersion"] = "5.0.0"
        result["document"]["documentType"] = classification["documentType"]
        result["document"]["documentFamily"] = classification["documentFamily"]
        result["document"]["recognizedText"] = canonical_document["plainText"]
        result["document"]["recognizedTextLineCount"] = sum(
            len(page.get("blocks", [])) for page in canonical_document.get("pages", [])
        )
        result["document"]["structuredFields"] = extraction["fields"]
        result["document"]["structuredTables"] = extraction["tables"]
        result.pop("phase12", None)
        result["phase15"] = {
            "version": "2.0.0",
            "status": business_json["idpStatus"],
            "ingestion": idp_result["ingestion"],
            "classification": classification,
            "extraction": extraction,
            "durationMs": duration_ms,
            "downloads": {
                "canonicalDocument": "phase15/canonical_document.json",
                "idpResult": "phase15/idp_result.json",
                "businessJson": "phase15/business.json",
            },
        }
        result["processing"].pop("phase12DurationMs", None)
        result["processing"]["phase15DurationMs"] = duration_ms
        return result

    def apply_phase14_8_recognition(
        self,
        result: dict[str, Any],
        input_path: Path,
        session_dir: Path,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Replace Paddle text with locked Seq2Seq output before Phase 15."""
        result_path = session_dir / "result.json"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        runtime_python = self.data_root / "runtime" / "easyocr_venv" / "Scripts" / "python.exe"
        script_path = Path(__file__).with_name("run_phase14_8_session.py")
        started = time.perf_counter()
        failure_type: str | None = None
        if runtime_python.is_file():
            try:
                subprocess.run(
                    [
                        str(runtime_python),
                        str(script_path),
                        "--data-root",
                        str(self.data_root),
                        "--session-id",
                        result["sessionId"],
                        "--overwrite",
                    ],
                    cwd=str(script_path.parent),
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    check=True,
                )
                payload = json.loads(
                    (session_dir / "phase14_8" / "recognition.json").read_text(encoding="utf-8")
                )
                canonical = ingest_document(
                    input_path,
                    payload["pages"],
                )
                result["phase14_8"] = {
                    "version": "1.0.0",
                    "status": payload["status"],
                    "policy": payload["policy"],
                    "summary": payload["summary"],
                    "durationMs": payload["durationMs"],
                    "download": "phase14_8/recognition.json",
                }
                result["processing"]["engine"] = "Paddle detector + VietOCR Seq2Seq/Transformer"
                result["processing"]["profile"] = "phase14.8-seq2seq-transformer-verifier"
                result["processing"]["models"] = {
                    "textDetection": "PP-OCRv5_mobile_det",
                    "textRecognitionPrimary": "VietOCR/vgg_seq2seq",
                    "textRecognitionVerifier": ("VietOCR/vgg_transformer"),
                    "paddleSelectionEligible": False,
                }
                result["processing"]["phase14_8DurationMs"] = round(
                    (time.perf_counter() - started) * 1000
                )
                return result, canonical
            except subprocess.TimeoutExpired:
                failure_type = "TIMEOUT"
            except (subprocess.CalledProcessError, OSError, ValueError):
                failure_type = "RUNTIME_FAILURE"
        else:
            failure_type = "RUNTIME_UNAVAILABLE"

        review_pages = []
        for page in result.get("document", {}).get("pages", []):
            review_pages.append(
                {
                    **page,
                    "recognitionScores": [0.0 for _ in page.get("recognizedTexts", [])],
                }
            )
        canonical = ingest_document(input_path, review_pages)
        result["phase14_8"] = {
            "version": "1.0.0",
            "status": failure_type,
            "policy": {
                "primaryProfile": "vietocr_vgg_seq2seq",
                "verifierProfile": "vietocr_vgg_transformer",
                "paddleSelectionEligible": False,
                "fallbackAction": ("Paddle evidence retained at zero acceptance confidence"),
            },
            "summary": {
                "pageCount": len(review_pages),
                "lineCount": sum(len(page.get("recognizedTexts", [])) for page in review_pages),
                "verifiedLineCount": 0,
                "needsReviewLineCount": sum(
                    len(page.get("recognizedTexts", [])) for page in review_pages
                ),
            },
            "durationMs": round((time.perf_counter() - started) * 1000),
        }
        result["processing"]["phase14_8DurationMs"] = result["phase14_8"]["durationMs"]
        return result, canonical

    def reprocess_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session_dir = self.session_dir(session_id)
            if session_dir is None:
                raise FileNotFoundError("Session not found")
            result_path = session_dir / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            locked_phase11_5_identity = (
                result.get("phase11", {}).get("identityCard")
                if result.get("phase11_5", {}).get("status") == "COMPLETE"
                else None
            )
            page_paths = sorted((session_dir / "pages").glob("page_*.png"))
            if not page_paths:
                raise FileNotFoundError("Rendered pages not found")
            input_paths = sorted((session_dir / "input").glob("document.*"))
            if not input_paths:
                raise FileNotFoundError("Original input not found")
            input_path = input_paths[0]
            canonical_document: dict[str, Any] | None = None
            if input_path.suffix.lower() in {".docx", ".xlsx"}:
                canonical_document = ingest_document(input_path)
                enriched = enrich_result(result)
            elif input_path.suffix.lower() == ".pdf":
                pdf_preflight = ingest_document(input_path)
                if pdf_preflight.get("ingestionMode") == "NATIVE":
                    canonical_document = pdf_preflight
                    enriched = enrich_result(result)
                else:
                    enriched = self.apply_phase9(
                        result,
                        page_paths,
                        session_dir,
                    )
            else:
                enriched = self.apply_phase9(
                    result,
                    page_paths,
                    session_dir,
                )
            if canonical_document is None:
                enriched = self.apply_phase11(
                    enriched,
                    page_paths,
                    session_dir,
                )
                if locked_phase11_5_identity:
                    enriched["phase11"]["version"] = "1.5.0"
                    enriched["phase11"]["status"] = "NEEDS_REVIEW"
                    enriched["phase11"]["identityCard"] = locked_phase11_5_identity
                    enriched["document"]["structuredFields"] = locked_phase11_5_identity["fields"]
                    (session_dir / "phase11" / "identity_card.json").write_text(
                        json.dumps(
                            locked_phase11_5_identity,
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
            else:
                enriched.pop("phase11", None)
                enriched.get("processing", {}).pop(
                    "phase11DurationMs",
                    None,
                )
            enriched.pop("phase11_3", None)
            enriched.pop("phase11_4", None)
            if canonical_document is None:
                enriched, canonical_document = self.apply_phase14_8_recognition(
                    enriched,
                    input_path,
                    session_dir,
                )
            else:
                enriched["phase14_8"] = {
                    "version": "1.0.0",
                    "status": "NOT_REQUIRED_NATIVE_INPUT",
                    "summary": {
                        "pageCount": canonical_document["pageCount"],
                        "lineCount": sum(
                            len(page.get("blocks", []))
                            for page in canonical_document.get("pages", [])
                        ),
                        "verifiedLineCount": 0,
                        "needsReviewLineCount": 0,
                    },
                    "durationMs": 0,
                }
            enriched = self.apply_phase15(
                enriched,
                input_path,
                session_dir,
                canonical_document,
            )
            result_path.write_text(
                json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return enriched

    def process_upload(
        self,
        session_id: str,
        original_filename: str,
        extension: str,
        content: bytes,
        declared_document_type: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            session_dir = self.sessions_root / session_id
            input_dir = session_dir / "input"
            pages_dir = session_dir / "pages"
            visualization_dir = session_dir / "visualization"
            input_dir.mkdir(parents=True, exist_ok=False)
            input_path = input_dir / f"document{extension}"
            input_path.write_bytes(content)

            total_started = time.perf_counter()
            canonical_document: dict[str, Any] | None = None
            page_results: list[dict[str, Any]]
            pdf_preflight = ingest_document(input_path) if extension == ".pdf" else None
            is_scan_input = extension in {".png", ".jpg", ".jpeg"} or bool(
                pdf_preflight and pdf_preflight.get("ingestionMode") != "NATIVE"
            )
            if is_scan_input and not ocr_allowed_for_document_type(declared_document_type):
                raise ValueError("OCR_DISABLED_BY_POLICY")
            if extension in {".docx", ".xlsx"}:
                canonical_document = ingest_document(input_path)
                page_paths, page_results = render_native_previews(
                    canonical_document,
                    pages_dir,
                    visualization_dir,
                )
            elif extension == ".pdf":
                assert pdf_preflight is not None
                if int(pdf_preflight.get("pageCount", 0)) > MAX_PDF_PAGES:
                    raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page limit")
                if pdf_preflight.get("ingestionMode") == "NATIVE":
                    canonical_document = pdf_preflight
                    page_paths, page_results = render_native_previews(
                        canonical_document,
                        pages_dir,
                        visualization_dir,
                    )
                else:
                    page_paths = self.render_pages(input_path, pages_dir)
                    page_results = []
                    for page_index, page_path in enumerate(page_paths):
                        page_result = self.predict_page(
                            page_path,
                            visualization_dir / f"page_{page_index:03d}.png",
                        )
                        page_result["pageIndex"] = page_index
                        page_results.append(page_result)
            else:
                page_paths = self.render_pages(input_path, pages_dir)
                page_results = []
                for page_index, page_path in enumerate(page_paths):
                    page_result = self.predict_page(
                        page_path,
                        visualization_dir / f"page_{page_index:03d}.png",
                    )
                    page_result["pageIndex"] = page_index
                    page_results.append(page_result)
            all_texts: list[str] = []
            all_scores: list[float] = []
            inference_duration_ms = 0
            for _page_index, page_result in enumerate(page_results):
                texts = page_result["recognizedTexts"]
                scores = page_result["recognitionScores"]
                inference_duration_ms += int(page_result["durationMs"])
                all_texts.extend(texts)
                all_scores.extend(scores)

            recognized_text = "\n".join(all_texts)
            total_duration_ms = round((time.perf_counter() - total_started) * 1000)
            result = {
                "schemaVersion": "1.0.0",
                "sessionId": session_id,
                "createdAt": utc_now(),
                "containsRealPII": True,
                "retention": "persistent_until_deleted",
                "source": {
                    "originalFileName": original_filename,
                    "format": extension.lstrip(".").upper(),
                    "sizeBytes": len(content),
                    "pageCount": len(page_paths),
                },
                "processing": {
                    "engine": (
                        ("NativeOOXML" if extension in {".docx", ".xlsx"} else "NativePDF")
                        if canonical_document is not None
                        else "PaddleOCR"
                    ),
                    "profile": ("phase12_native" if canonical_document else "v5_enhanced"),
                    "ocrVersion": ("not_required" if canonical_document else "PP-OCRv5"),
                    "language": "vi",
                    "device": "cpu",
                    "models": {
                        "textDetection": "PP-OCRv5_mobile_det",
                        "textRecognition": "latin_PP-OCRv5_mobile_rec",
                    },
                    "inferenceDurationMs": inference_duration_ms,
                    "totalDurationMs": total_duration_ms,
                    "ocrScope": ocr_scope_for(
                        SourceFormat.PDF_SCAN
                        if is_scan_input and extension == ".pdf"
                        else SourceFormat.IMAGE
                        if is_scan_input
                        else SourceFormat.PDF_TEXT,
                        declared_document_type,
                    ),
                },
                "document": {
                    "documentType": declared_document_type or "USER_UPLOAD",
                    "ocrSuccess": bool(all_texts),
                    "recognizedText": recognized_text,
                    "recognizedTextLineCount": len(all_texts),
                    "avgConfidence": (
                        round(sum(all_scores) / len(all_scores), 6) if all_scores else None
                    ),
                    "extractedCandidates": extract_candidates(recognized_text),
                    "pages": page_results,
                },
            }
            if canonical_document:
                result = enrich_result(result)
            else:
                result = self.apply_phase9(
                    result,
                    page_paths,
                    session_dir,
                )
            if canonical_document is None:
                result = self.apply_phase11(
                    result,
                    page_paths,
                    session_dir,
                )
                result, canonical_document = self.apply_phase14_8_recognition(
                    result,
                    input_path,
                    session_dir,
                )
            else:
                result["phase14_8"] = {
                    "version": "1.0.0",
                    "status": "NOT_REQUIRED_NATIVE_INPUT",
                    "summary": {
                        "pageCount": canonical_document["pageCount"],
                        "lineCount": sum(
                            len(page.get("blocks", []))
                            for page in canonical_document.get("pages", [])
                        ),
                        "verifiedLineCount": 0,
                        "needsReviewLineCount": 0,
                    },
                    "durationMs": 0,
                }
            result = self.apply_phase15(
                result,
                input_path,
                session_dir,
                canonical_document,
            )
            result["processing"]["totalDurationMs"] = round(
                (time.perf_counter() - total_started) * 1000
            )
            (session_dir / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return result

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for result_path in self.sessions_root.glob("*/result.json"):
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                ground_truth_path = result_path.parent / "phase10" / "ground_truth.json"
                reviewed = False
                if ground_truth_path.is_file():
                    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
                    assertions = ground_truth.get("verificationAssertions", {})
                    reviewed = bool(
                        assertions.get("comparedWithImage") and assertions.get("allTextChecked")
                    )
                phase15_reviewed = (result_path.parent / "phase15" / "review.json").is_file()
                processing = result.get("processing", {})
                phase11 = result.get("phase11", {})
                phase14_8 = result.get("phase14_8", {})
                sessions.append(
                    {
                        "sessionId": result["sessionId"],
                        "createdAt": result["createdAt"],
                        "originalFileName": result["source"]["originalFileName"],
                        "format": result["source"]["format"],
                        "pageCount": result["source"]["pageCount"],
                        "ocrSuccess": result["document"]["ocrSuccess"],
                        "recognizedTextLineCount": result["document"]["recognizedTextLineCount"],
                        "avgConfidence": result["document"]["avgConfidence"],
                        "totalDurationMs": result["processing"]["totalDurationMs"],
                        "documentType": result["document"].get("documentType", "USER_UPLOAD"),
                        "qualityGate": result.get("phase9", {})
                        .get("qualityGate", {})
                        .get("status"),
                        "processingProfile": processing.get("profile"),
                        "ocrVersion": processing.get("ocrVersion"),
                        "phase11Version": phase11.get("version"),
                        "phase14_8Status": phase14_8.get("status"),
                        "reviewed": reviewed,
                        "phase15Reviewed": phase15_reviewed,
                    }
                )
            except (OSError, KeyError, json.JSONDecodeError):
                continue
        return sorted(sessions, key=lambda row: row["createdAt"], reverse=True)

    def template_result(self, session_id: str) -> dict[str, Any] | None:
        session_dir = self.session_dir(session_id)
        if session_dir is None:
            return None
        result_path = session_dir / "template_first" / "result.json"
        if not result_path.is_file():
            return None
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload.get("templateId"), str) and payload.get(
            "documentType"
        ) not in {"LEAVE_REQUEST", "OVERTIME_REQUEST"}:
            return None
        payload = canonicalize_template_payload(payload)
        performance_path = session_dir / "template_first" / "performance.json"
        if performance_path.is_file():
            try:
                performance = json.loads(performance_path.read_text(encoding="utf-8"))
                timings = performance.get("timingsMs")
                processing = payload.get("processing")
                if isinstance(timings, dict) and isinstance(processing, dict):
                    processing["timingSchemaVersion"] = performance.get(
                        "schemaVersion"
                    )
                    processing["timingsMs"] = timings
            except (OSError, json.JSONDecodeError):
                pass
        return payload

    def template_source(self, session_id: str) -> Path | None:
        if self.template_result(session_id) is None:
            return None
        session_dir = self.session_dir(session_id)
        if session_dir is None:
            return None
        source_paths = sorted((session_dir / "input").glob("document.*"))
        if len(source_paths) != 1 or not source_paths[0].is_file():
            return None
        return source_paths[0]

    def template_comparison(self, session_id: str) -> dict[str, Any] | None:
        session_dir = self.session_dir(session_id)
        if session_dir is None or self.template_result(session_id) is None:
            return None
        comparison_path = session_dir / "template_first" / "comparison.json"
        if not comparison_path.is_file():
            return None
        try:
            payload = json.loads(comparison_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if payload.get("documentId") == session_id else None

    def save_template_comparison(
        self,
        session_id: str,
        comparison: dict[str, Any],
    ) -> None:
        session_dir = self.session_dir(session_id)
        if session_dir is None or self.template_result(session_id) is None:
            raise ValueError("Template session not found")
        (session_dir / "template_first" / "comparison.json").write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def template_preview(self, session_id: str) -> tuple[bytes, str] | None:
        source_path = self.template_source(session_id)
        if source_path is None:
            return None
        if source_path.suffix.lower() != ".pdf":
            if source_path.suffix.lower() in {".tif", ".tiff"}:
                output = BytesIO()
                with Image.open(source_path) as image:
                    image.convert("RGB").save(output, format="PNG", optimize=True)
                return output.getvalue(), "image/png"
            content_type = (
                mimetypes.guess_type(source_path.name)[0]
                or "application/octet-stream"
            )
            return source_path.read_bytes(), content_type
        if pdfium is None:
            raise RuntimeError("PDF preview rendering is unavailable.")

        document = pdfium.PdfDocument(source_path)
        try:
            if len(document) == 0:
                raise ValueError("PDF has no pages")
            page = document[0]
            try:
                bitmap = page.render(scale=1.6)
                try:
                    image = bitmap.to_pil().convert("RGB")
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            document.close()

        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue(), "image/png"

    def list_template_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for result_path in self.sessions_root.glob("*/template_first/result.json"):
            session_id = result_path.parents[1].name
            result = self.template_result(session_id)
            if result is None:
                continue
            data = result.get("data", {})
            quality = result.get("quality", {})
            processing = result.get("processing", {})
            try:
                created_at = datetime.fromtimestamp(
                    result_path.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat()
            except OSError:
                continue
            sessions.append(
                {
                    "documentId": session_id,
                    "createdAt": created_at,
                    "originalFileName": processing.get("originalFileName")
                    or data.get("sourceFile")
                    or "template-document.docx",
                    "documentType": result["documentType"],
                    "templateId": result["templateId"],
                    "templateVersion": result["templateVersion"],
                    "status": result["status"],
                    "recommendedAction": quality.get("recommendedAction"),
                    "confidence": quality.get("confidence"),
                    "sourceFormat": processing.get("sourceFormat", "DOCX"),
                    "usesOcr": processing.get("usesOcr", False),
                    "parserName": processing.get("parserName", "docx/ooxml"),
                }
            )
        return sorted(sessions, key=lambda row: row["createdAt"], reverse=True)


class DashboardHandler(BaseHTTPRequestHandler):
    data_root: Path
    benchmark_report: Path | None = None
    benchmark_manifest: Path | None = None
    cccd_heldout_root: Path | None
    ocr_ho_shadow_root: Path | None
    external_dataset_root: Path | None
    external_dataset_inventory: Path | None
    external_dataset_ground_truth: Path | None
    external_dataset_coverage_decision: Path | None
    external_dataset_typed_projection: Path | None
    external_dataset_typed_approval: Path | None
    external_dataset_typed_report: Path | None
    external_dataset_predictions: Path | None
    external_dataset_prediction_report: Path | None
    external_dataset_prediction_marker: Path | None
    external_dataset_predictions_data13: Path | None
    external_dataset_prediction_report_data13: Path | None
    external_dataset_prediction_marker_data13: Path | None
    native_indexes: dict[str, dict[str, Path]]
    user_ocr: UserOCRService
    template_processor: TemplateProcessingService
    mvp_demo: MvpDemoStore | None = None

    def _demo_store(self) -> MvpDemoStore:
        if self.mvp_demo is None:
            raise MvpDemoError("MVP demo store is unavailable", 503)
        return self.mvp_demo

    def _auth_token(self) -> str | None:
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[len("Bearer ") :].strip()
        if header.startswith("Token "):
            return header[len("Token ") :].strip()
        return None

    def _require_user(self, roles: set[str] | None = None) -> dict[str, Any]:
        user = self._demo_store().user_by_token(self._auth_token())
        if user is None:
            raise MvpDemoError("Chưa đăng nhập", HTTPStatus.UNAUTHORIZED)
        if roles is not None and user["role"] not in roles:
            raise MvpDemoError("Role không có quyền truy cập", HTTPStatus.FORBIDDEN)
        return user

    def _require_document_access(self, user: dict[str, Any], document_id: str) -> None:
        if not self._demo_store().can_access(user, document_id):
            raise MvpDemoError("Không có quyền truy cập hồ sơ", HTTPStatus.FORBIDDEN)

    def _handle_mvp_error(self, exc: MvpDemoError) -> None:
        status = exc.status if isinstance(exc.status, HTTPStatus) else HTTPStatus(exc.status)
        self.send_json({"error": str(exc), "errorCode": "MVP_DEMO_ERROR"}, status)

    def _apply_submission_corrections(
        self,
        document_id: str,
        stored: dict[str, Any],
        corrections: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist the fields the submitter fixed on the extracted document."""
        template_id = str(stored.get("templateId") or "")
        allowed_fields: frozenset[str] = frozenset()
        for item in self.template_processor.list_templates():
            if item.get("templateId") != template_id:
                continue
            required = item.get("requiredFields")
            optional = item.get("optionalFields")
            allowed_fields = frozenset(
                [
                    *(required if isinstance(required, list) else []),
                    *(optional if isinstance(optional, list) else []),
                ]
            )
            break
        scalar_corrections = {
            key: value
            for key, value in corrections.items()
            if key in allowed_fields
            and (isinstance(value, (str, int, float, bool)) or value is None)
        }
        if not scalar_corrections:
            return stored
        try:
            corrected = self.template_processor.apply_corrections(
                stored, scalar_corrections
            )
        except (TemplateUnsupportedError, TemplateTechnicalError) as exc:
            raise ValueError(f"Correction is not accepted: {exc}") from exc
        payload = corrected.public_dict()
        payload["processing"] = dict(stored.get("processing", {}))
        payload["processing"]["correctedAt"] = utc_now()
        result_path = (
            self.user_ocr.sessions_root / document_id / "template_first" / "result.json"
        )
        result_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload

    def _stream_events(self, query: dict[str, list[str]]) -> None:
        """Stream MVP demo events as SSE so the UI updates without polling.

        EventSource cannot set an Authorization header, so the session token is
        accepted from the query string; request logging is disabled for this
        server, so the token never reaches a log file.
        """
        token = query.get("token", [""])[0] or self._auth_token()
        try:
            store = self._demo_store()
        except MvpDemoError as exc:
            self._handle_mvp_error(exc)
            return
        user = store.user_by_token(token)
        if user is None:
            self.send_json(
                {"error": "Chưa đăng nhập", "errorCode": "MVP_DEMO_ERROR"},
                HTTPStatus.UNAUTHORIZED,
            )
            return
        cursor = _parse_cursor(query.get("cursor", ["0"])[0])
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.cors_headers()
        self.end_headers()
        deadline = time.monotonic() + SSE_MAX_STREAM_SECONDS
        try:
            self.wfile.write(f"retry: {SSE_RETRY_MS}\n".encode())
            self._write_sse("ready", {"cursor": cursor})
            while time.monotonic() < deadline:
                events, cursor = store.wait_for_events(
                    user, cursor, SSE_HEARTBEAT_SECONDS
                )
                if events:
                    for event in events:
                        self._write_sse("event", event)
                else:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _write_sse(self, name: str, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"event: {name}\ndata: {body}\n\n".encode())
        self.wfile.flush()

    def _announce_submission_to_hr(
        self,
        submitter: dict[str, Any],
        *,
        application_id: str,
        document_id: str,
        document_type: str,
    ) -> None:
        """Push the new case to every HR reviewer as soon as it is submitted."""
        store = self._demo_store()
        label = DOCUMENT_TYPE_LABELS.get(document_type, document_type)
        store.notify_roles(
            {ROLE_HR, ROLE_ADMIN},
            f"Đơn mới chờ duyệt: {label} - {submitter['displayName']}",
            kind="SUBMITTED",
            application_id=application_id,
            document_id=document_id,
        )
        store.publish(
            EVENT_QUEUE_CHANGED,
            target_roles=[ROLE_HR, ROLE_ADMIN],
            payload={"applicationId": application_id, "documentType": document_type},
        )
        store.record_event(
            application_id,
            "HR_NOTIFIED",
            f"HR nhan thong bao ho so {document_type}",
            "system",
        )

    def _submit_leave_application(
        self, actor: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        required = ["employeeName", "startDate", "endDate", "reason"]
        for field in required:
            if not str(payload.get(field, "")).strip():
                raise MvpDemoError(f"Thiếu trường bắt buộc: {field}")
        document_id = str(uuid.uuid4())
        session_dir = self.user_ocr.sessions_root / document_id
        result_dir = session_dir / "template_first"
        input_dir = session_dir / "input"
        result_dir.mkdir(parents=True, exist_ok=True)
        input_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "documentId": document_id,
            "documentType": "LEAVE_REQUEST",
            "templateId": "leave-request-v1",
            "templateVersion": "1.0",
            "documentTitle": "ĐƠN XIN NGHỈ PHÉP",
            "formNumber": str(payload.get("formNumber") or f"ST-{datetime.now(timezone.utc):%Y%m%d}"),
            "organization": str(payload.get("organization") or "CÔNG TY TNHH HCNS SAMPLE"),
            "employeeName": str(payload.get("employeeName") or ""),
            "employeeId": str(payload.get("employeeId") or actor["username"]),
            "jobTitle": str(payload.get("jobTitle") or ""),
            "department": str(payload.get("department") or ""),
            "address": str(payload.get("address") or ""),
            "phone": str(payload.get("phone") or ""),
            "requestDate": str(payload.get("requestDate") or datetime.now(timezone.utc).date().isoformat()),
            "leaveDays": payload.get("leaveDays"),
            "startDate": str(payload.get("startDate") or ""),
            "endDate": str(payload.get("endDate") or ""),
            "reason": str(payload.get("reason") or ""),
            "expectedReturnDate": str(payload.get("expectedReturnDate") or ""),
            "handoverTo": str(payload.get("handoverTo") or actor["displayName"]),
            "handoverDepartment": str(payload.get("handoverDepartment") or payload.get("department") or ""),
            "handoverTasks": str(payload.get("handoverTasks") or "Bàn giao toàn bộ công việc đang phụ trách"),
            "approverName": str(payload.get("approverName") or actor["displayName"]),
            "missingFields": [],
            "validationErrors": [],
            "confidence": 1.0,
            "recommendedAction": "AUTO_CONTINUE",
            "sourceFile": "leave-request.docx",
        }
        if data["leaveDays"] is None:
            try:
                from datetime import date as date_cls

                start = date_cls.fromisoformat(data["startDate"])
                end = date_cls.fromisoformat(data["endDate"])
                data["leaveDays"] = max((end - start).days + 1, 0)
            except ValueError:
                data["leaveDays"] = 1
        result_payload = {
            "status": "AUTO_CONTINUE",
            "documentType": "LEAVE_REQUEST",
            "templateId": "leave-request-v1",
            "templateVersion": "1.0",
            "schemaVersion": "2.0.0",
            "detection": {"definition": {"supportedFileTypes": [".docx", ".pdf"]}},
            "data": data,
            "quality": {
                "missingFields": [],
                "validationErrors": [],
                "confidence": 1.0,
                "recommendedAction": "AUTO_CONTINUE",
            },
            "processing": {
                "processedAt": utc_now(),
                "originalFileName": "leave-request.docx",
                "timingsMs": {"serviceTotal": 0.0},
            },
            "camundaVariables": {},
        }
        template_path = REPO_ROOT / "hcns format" / "01_don_xin_nghi_phep_v1.docx"
        try:
            docx_bytes = render_leave_docx(data, template_path)
        except (OSError, ValueError) as exc:
            raise MvpDemoError(f"Không render được DOCX: {exc}") from exc
        (input_dir / "document.docx").write_bytes(docx_bytes)
        (result_dir / "result.json").write_text(
            json.dumps(result_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        application_id = f"LOCAL-{uuid.uuid4()}"
        extracted_fields = extracted_fields_from_template_result(result_payload)
        store = self._demo_store()
        store.bind_document(actor, document_id, application_id)
        store.save_submission(
            application_id=application_id,
            document_id=document_id,
            owner=actor["username"],
            document_type="LEAVE_REQUEST",
            extracted_fields=extracted_fields,
            source_file="leave-request.docx",
        )
        store.open_archive(
            application_id=application_id,
            document_id=document_id,
            owner=actor["username"],
            document_type="LEAVE_REQUEST",
            extracted_fields=extracted_fields,
            source_file="leave-request.docx",
            source_path=input_dir / "document.docx",
            submitted_by_display=str(actor.get("displayName") or actor["username"]),
        )
        store.register_hr_pending(
            application_id=application_id,
            document_id=document_id,
            owner=actor["username"],
            document_type="LEAVE_REQUEST",
            extracted_fields=extracted_fields,
        )
        store.record_event(
            application_id, "SUBMITTED", "USER nộp đơn nghỉ phép", actor["username"]
        )
        engine_url = _local_camunda_url()
        fields_json = json.dumps(extracted_fields, ensure_ascii=False)
        variables = {
            "applicationId": {"value": application_id, "type": "String"},
            "documentReference": {"value": document_id, "type": "String"},
            "declaredDocumentType": {"value": "LEAVE_REQUEST", "type": "String"},
            "templateFieldsJson": {"value": fields_json, "type": "String"},
        }
        instance = _camunda_post(
            f"{engine_url}/process-definition/key/hr_document_agent_mvp_v2/start",
            {"variables": variables},
        )
        process_id = instance.get("id")
        if not isinstance(process_id, str):
            raise RuntimeError("Camunda did not return a process instance")
        tasks = _camunda_get(
            f"{engine_url}/task?processInstanceId={process_id}&taskDefinitionKey=Submit"
        )
        if not isinstance(tasks, list) or len(tasks) != 1:
            raise RuntimeError("Camunda submission task is unavailable")
        task_id = tasks[0].get("id")
        if not isinstance(task_id, str):
            raise RuntimeError("Camunda submission task is invalid")
        _camunda_post(f"{engine_url}/task/{task_id}/complete", {"variables": variables})
        self._demo_store().record_event(
            application_id,
            "CAMUNDA_STARTED",
            f"Camunda đã tạo process {process_id}",
            "system",
        )
        self._announce_submission_to_hr(
            actor,
            application_id=application_id,
            document_id=document_id,
            document_type="LEAVE_REQUEST",
        )
        return {
            "status": "SUBMITTED",
            "documentId": document_id,
            "applicationId": application_id,
            "documentType": "LEAVE_REQUEST",
            "documentTypeLabel": DOCUMENT_TYPE_LABELS["LEAVE_REQUEST"],
            "processInstanceId": process_id,
            "hrNotified": True,
            "extractedFields": extracted_fields,
            "tasklistUrl": os.getenv(
                "HCNS_CAMUNDA_PUBLIC_URL",
                "http://localhost:8080/camunda/app/tasklist/default/",
            ),
        }

    def log_message(self, format: str, *args: object) -> None:
        # Never log session IDs, filenames, paths, or raw OCR text.
        return

    def cors_headers(self) -> None:
        origin = (self.headers.get("Origin") or "").strip().rstrip("/")
        allowed = {
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        }
        extra_origins = {
            item.strip().rstrip("/")
            for item in os.getenv("HCNS_API_CORS_ORIGINS", "").split(",")
            if item.strip()
        }
        if origin:
            if origin in allowed or origin in extra_origins:
                allowed = {origin}
            else:
                for pattern in extra_origins:
                    scheme, separator, rest = pattern.partition("://")
                    if not separator or "*" not in rest:
                        continue
                    prefix, suffix = rest.split("*", 1)
                    host = origin.partition("://")[2]
                    if origin.startswith(scheme + "://" + prefix) and host.endswith(suffix):
                        allowed = {origin}
                        break
        if origin not in allowed:
            origin = "http://localhost:3000"
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Expose-Headers", "Content-Disposition")
        self.send_header("Cache-Control", "no-store")

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_file(
        self,
        path: Path,
        content_type: str,
        download_name: str | None = None,
    ) -> None:
        self.send_bytes(path.read_bytes(), content_type, download_name)

    def send_bytes(
        self,
        body: bytes,
        content_type: str,
        download_name: str | None = None,
        *,
        inline: bool = False,
    ) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if download_name:
            disposition = "inline" if inline else "attachment"
            self.send_header(
                "Content-Disposition",
                f'{disposition}; filename="{download_name}"',
            )
        self.cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        if not self._request_host_is_local():
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.cors_headers()
        self.end_headers()

    def do_POST(self) -> None:
        if not self._request_host_is_local():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/login":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                    raise ValueError("Login body is empty or exceeds 2 MB")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                session = self._demo_store().login(
                    str(payload.get("username", "")).strip(),
                    str(payload.get("password", "")),
                )
                self.send_json({"session": session})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                if isinstance(exc, MvpDemoError):
                    self._handle_mvp_error(exc)
                else:
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/auth/logout":
            try:
                self._demo_store().logout(self._auth_token())
                self.send_json({"status": "LOGGED_OUT"})
            except (ValueError, TypeError) as exc:
                if isinstance(exc, MvpDemoError):
                    self._handle_mvp_error(exc)
                else:
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/admin/users":
            try:
                actor = self._require_user({ROLE_ADMIN})
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                    raise ValueError("User body is empty or exceeds 2 MB")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                action = str(payload.get("action", "create"))
                if action == "toggle":
                    result = self._demo_store().set_user_active(
                        actor,
                        str(payload.get("username", "")),
                        bool(payload.get("active", False)),
                    )
                else:
                    result = self._demo_store().create_user(
                        actor,
                        str(payload.get("username", "")).strip(),
                        str(payload.get("password", "")),
                        str(payload.get("role", "")),
                        str(payload.get("displayName", "")),
                        managed_by=str(payload.get("managedBy", "")).strip() or None,
                    )
                self.send_json({"status": "OK", "user": result})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                if isinstance(exc, MvpDemoError):
                    self._handle_mvp_error(exc)
                else:
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/admin/assign":
            try:
                actor = self._require_user({ROLE_ADMIN})
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                    raise ValueError("Assign body is empty or exceeds 2 MB")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                result = self._demo_store().assign_user_to_hr(
                    actor,
                    str(payload.get("username", "")).strip(),
                    str(payload.get("hrUsername", "")).strip(),
                )
                self.send_json({"status": "OK", "assignment": result})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                if isinstance(exc, MvpDemoError):
                    self._handle_mvp_error(exc)
                else:
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/documents/leave":
            try:
                actor = self._require_user({ROLE_USER, ROLE_HR, ROLE_ADMIN})
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                    raise ValueError("Leave body is empty or exceeds 2 MB")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                result = self._submit_leave_application(actor, payload)
                self.send_json(result)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                if isinstance(exc, MvpDemoError):
                    self._handle_mvp_error(exc)
                else:
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (HTTPError, URLError, RuntimeError) as exc:
                self.send_json({"error": f"Camunda local is unavailable: {exc}"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path == "/api/notifications/read":
            try:
                user = self._require_user()
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                    raise ValueError("Notification body is empty or exceeds 2 MB")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                self._demo_store().mark_notification_read(
                    user["username"], str(payload.get("notificationId", ""))
                )
                self.send_json({"status": "OK"})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                if isinstance(exc, MvpDemoError):
                    self._handle_mvp_error(exc)
                else:
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/documents/compare":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                    raise ValueError("Comparison body is empty or exceeds 2 MB")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                document_id = str(payload.get("documentId", ""))
                uuid.UUID(document_id)
                ground_truth = payload.get("groundTruth")
                if not isinstance(ground_truth, dict):
                    raise ValueError("Ground Truth must be an object")
                result = self.user_ocr.template_result(document_id)
                if result is None:
                    raise ValueError("Template session not found")
                comparison = compare_template_result(result, ground_truth)
                self.user_ocr.save_template_comparison(document_id, comparison)
                self.send_json(comparison)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/camunda/review":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                    self.send_json(
                        {"error": "Request body is empty or exceeds 2 MB"},
                        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    )
                    return
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                task_id = str(payload.get("taskId", ""))
                role = str(payload.get("role", ""))
                decision = str(payload.get("decision", ""))
                note = str(payload.get("note", "")).strip()[:120]
                if not task_id:
                    raise ValueError("Camunda task is required")
                review_policy = {
                    "employee": ("UserReview", "local-employee", "userReviewDecision", {"CONFIRMED", "UNRESOLVED", "REQUEST_REUPLOAD"}),
                    "hr": ("HRReview", "local-hr", "hrReviewDecision", {"CONFIRMED", "REQUEST_REUPLOAD", "REJECTED"}),
                }.get(role)
                if review_policy is None or decision not in review_policy[3]:
                    raise ValueError("Decision is not allowed for this local demo role")
                if role == "hr":
                    reviewer = self._require_user({ROLE_HR, ROLE_ADMIN})
                else:
                    reviewer = self._require_user()
                # MVP fallback: HR can decide while Camunda Parse/OCR is still syncing.
                if role == "hr" and task_id.startswith("pending-"):
                    application_id = task_id[len("pending-") :]
                    store = self._demo_store()
                    pending = store.get_hr_pending(application_id)
                    submission = store.get_submission(application_id)
                    if pending is None and submission is None:
                        raise ValueError("Pending HR task is unavailable")
                    document_ref = str(
                        (pending or submission or {}).get("documentId") or ""
                    )
                    owner = str((pending or submission or {}).get("owner") or "")
                    if document_ref:
                        self._require_document_access(reviewer, document_ref)
                    _safe_record_event(
                        store,
                        application_id,
                        "HR_REVIEWED",
                        f"Quyết định: {decision}"
                        + (f" · Ghi chú: {note}" if note else "")
                        + " · (duyệt local trước khi Camunda sẵn sàng)",
                        reviewer["username"],
                    )
                    source_path = None
                    if decision == "CONFIRMED" and document_ref:
                        source_path = self.user_ocr.template_source(document_ref)
                    store.finalize_archive(
                        application_id=application_id,
                        decision=decision,
                        reviewed_by=reviewer["username"],
                        note=note,
                        source_path=source_path,
                    )
                    store.resolve_hr_pending(application_id)
                    if owner and decision in HR_DECISION_MESSAGES:
                        store.notify(
                            owner,
                            HR_DECISION_MESSAGES[decision],
                            application_id=application_id,
                        )
                    store.publish(
                        EVENT_QUEUE_CHANGED,
                        target_roles=[ROLE_HR, ROLE_ADMIN],
                        target_users=[owner] if owner else None,
                        payload={
                            "applicationId": application_id,
                            "decision": decision,
                        },
                    )
                    self.send_json(
                        {
                            "status": "COMPLETED",
                            "decision": decision,
                            "effectiveDecision": decision,
                            "pendingLocal": True,
                            "notifiedOwner": bool(owner),
                        }
                    )
                    return
                engine_url = _local_camunda_url()
                task = _camunda_get(f"{engine_url}/task/{task_id}")
                if not isinstance(task, dict):
                    raise ValueError("Task is unavailable for this role")
                task_key = task.get("taskDefinitionKey")
                process_instance_id = str(task.get("processInstanceId", ""))
                decision_to_complete = decision
                notify_decision: str | None = None
                if role == "hr" and task_key == "UserReview":
                    review_policy = (
                        "UserReview",
                        "local-employee",
                        "userReviewDecision",
                        {"CONFIRMED", "REQUEST_REUPLOAD", "REJECTED"},
                    )
                    if decision == "REJECTED":
                        decision_to_complete = "UNRESOLVED"
                if task_key != review_policy[0]:
                    raise ValueError("Task is unavailable for this role")
                variables = _camunda_get(f"{engine_url}/task/{task_id}/variables")
                document_ref = _camunda_value(variables, "documentReference")
                if role == "employee" and document_ref is not None:
                    self._require_document_access(reviewer, document_ref)
                _claim_and_complete_camunda_task(
                    engine_url,
                    task_id,
                    assignee=review_policy[1],
                    variable_name=review_policy[2],
                    decision=decision_to_complete,
                )
                if (
                    role == "hr"
                    and task_key == "UserReview"
                    and decision == "REJECTED"
                    and process_instance_id
                ):
                    hr_task = _wait_for_camunda_task(
                        engine_url, process_instance_id, "HRReview"
                    )
                    if hr_task is not None:
                        hr_task_id = hr_task.get("id")
                        if isinstance(hr_task_id, str):
                            _claim_and_complete_camunda_task(
                                engine_url,
                                hr_task_id,
                                assignee="local-hr",
                                variable_name="hrReviewDecision",
                                decision="REJECTED",
                            )
                            notify_decision = "REJECTED"
                            task_key = "HRReview"
                elif role == "hr" and task_key == "HRReview":
                    notify_decision = decision
                elif role == "hr" and task_key == "UserReview" and decision in {
                    "REQUEST_REUPLOAD",
                }:
                    notify_decision = decision
                application_id = (
                    _camunda_value(variables, "applicationId") or "LOCAL-demo"
                )
                store = self._demo_store()
                _safe_record_event(
                    store,
                    application_id,
                    "HR_REVIEWED" if role == "hr" else "USER_REVIEWED",
                    f"Quyết định: {decision}" + (f" · Ghi chú: {note}" if note else ""),
                    reviewer["username"],
                )
                notified_owner = None
                if (
                    notify_decision in HR_DECISION_MESSAGES
                    and document_ref is not None
                ):
                    owner = store.owner_of(document_ref)
                    if owner:
                        _notify_hr_decision(
                            store,
                            owner=owner,
                            decision=notify_decision,
                            application_id=application_id,
                            document_ref=document_ref,
                            note=note,
                        )
                        _safe_record_event(
                            store,
                            application_id,
                            "NOTIFIED",
                            f"USER nhan notification: {HR_DECISION_MESSAGES[notify_decision]}",
                            "system",
                        )
                        notified_owner = owner
                store.publish(
                    EVENT_QUEUE_CHANGED,
                    target_roles=[ROLE_HR, ROLE_ADMIN],
                    target_users=[notified_owner] if notified_owner else None,
                    payload={
                        "applicationId": application_id,
                        "decision": notify_decision or decision,
                    },
                )
                if role == "hr":
                    store.resolve_hr_pending(application_id)
                    if notify_decision in HR_DECISION_MESSAGES:
                        source_path = None
                        if (
                            notify_decision == "CONFIRMED"
                            and isinstance(document_ref, str)
                            and document_ref
                        ):
                            source_path = self.user_ocr.template_source(document_ref)
                        store.finalize_archive(
                            application_id=application_id,
                            decision=notify_decision,
                            reviewed_by=reviewer["username"],
                            note=note,
                            source_path=source_path,
                        )
                self.send_json(
                    {
                        "status": "COMPLETED",
                        "decision": decision,
                        "effectiveDecision": notify_decision or decision,
                        "notifiedOwner": notified_owner is not None,
                    }
                )
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (HTTPError, URLError, RuntimeError) as exc:
                self.send_json({"error": f"Camunda local is unavailable: {exc}"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path == "/api/camunda/start":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                    self.send_json(
                        {"error": "Request body is empty or exceeds 2 MB"},
                        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    )
                    return
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                user = self._require_user()
                document_id = str(payload.get("documentId", ""))
                uuid.UUID(document_id)
                self._require_document_access(user, document_id)
                result = self.user_ocr.template_result(document_id)
                if result is None:
                    raise ValueError("Template session not found")
                corrections = payload.get("corrections")
                if isinstance(corrections, dict) and corrections:
                    result = self._apply_submission_corrections(
                        document_id, result, corrections
                    )
                document_type = result.get("documentType")
                if document_type not in CAMUNDA_UPLOAD_DOCUMENT_TYPES:
                    raise ValueError("Document type is not available for Camunda local shadow")
                source = self.user_ocr.template_source(document_id)
                if source is None:
                    raise ValueError("Private document source not found")
                private_root = os.getenv("HCNS_CAMUNDA_PRIVATE_ROOT", "").strip()
                if not private_root:
                    private_root = str(self.data_root)
                if Path(private_root).resolve() != self.data_root.resolve():
                    raise ValueError(
                        "HCNS_CAMUNDA_PRIVATE_ROOT must match the dashboard data root"
                    )
                application_id = f"LOCAL-{uuid.uuid4()}"
                store = self._demo_store()
                extracted_fields = extracted_fields_from_template_result(result)
                source_name = ""
                processing = result.get("processing")
                if isinstance(processing, dict):
                    source_name = str(processing.get("originalFileName") or "")
                store.bind_document(user, document_id, application_id)
                store.save_submission(
                    application_id=application_id,
                    document_id=document_id,
                    owner=user["username"],
                    document_type=str(document_type),
                    extracted_fields=extracted_fields,
                    source_file=source_name,
                )
                store.open_archive(
                    application_id=application_id,
                    document_id=document_id,
                    owner=user["username"],
                    document_type=str(document_type),
                    extracted_fields=extracted_fields,
                    source_file=source_name or source.name,
                    source_path=source,
                    submitted_by_display=str(user.get("displayName") or user["username"]),
                )
                store.register_hr_pending(
                    application_id=application_id,
                    document_id=document_id,
                    owner=user["username"],
                    document_type=document_type,
                    extracted_fields=extracted_fields,
                )
                store.record_event(
                    application_id, "SUBMITTED", "USER nộp hồ sơ", user["username"]
                )
                fields_json = json.dumps(extracted_fields, ensure_ascii=False)
                variables = {
                    "applicationId": {"value": application_id, "type": "String"},
                    "documentReference": {"value": document_id, "type": "String"},
                    "declaredDocumentType": {"value": document_type, "type": "String"},
                    "templateFieldsJson": {"value": fields_json, "type": "String"},
                }
                engine_url = _local_camunda_url()
                camunda_started = time.perf_counter()
                instance = _camunda_post(
                    f"{engine_url}/process-definition/key/hr_document_agent_mvp_v2/start",
                    {"variables": variables},
                )
                process_id = instance.get("id")
                if not isinstance(process_id, str):
                    raise RuntimeError("Camunda did not return a process instance")
                tasks = _camunda_get(
                    f"{engine_url}/task?processInstanceId={process_id}&taskDefinitionKey=Submit"
                )
                if not isinstance(tasks, list) or len(tasks) != 1:
                    raise RuntimeError("Camunda submission task is unavailable")
                task_id = tasks[0].get("id")
                if not isinstance(task_id, str):
                    raise RuntimeError("Camunda submission task is invalid")
                _camunda_post(f"{engine_url}/task/{task_id}/complete", {"variables": variables})
                hr_task_ready = _demo_fast_forward_to_hr_review(engine_url, process_id)
                camunda_duration_ms = round(
                    (time.perf_counter() - camunda_started) * 1000,
                    3,
                )
                store.record_event(
                    application_id,
                    "CAMUNDA_STARTED",
                    f"Camunda đã tạo process {process_id}",
                    "system",
                )
                if hr_task_ready:
                    store.resolve_hr_pending(application_id)
                    store.record_event(
                        application_id,
                        "HR_QUEUE_READY",
                        "Đơn đã vào hàng đợi HR duyệt",
                        "system",
                    )
                self._announce_submission_to_hr(
                    user,
                    application_id=application_id,
                    document_id=document_id,
                    document_type=document_type,
                )
                if hr_task_ready:
                    store.publish(
                        EVENT_QUEUE_CHANGED,
                        target_roles=[ROLE_HR, ROLE_ADMIN],
                        payload={"applicationId": application_id, "ready": True},
                    )
                self.send_json({
                    "status": "SUBMITTED",
                    "documentId": document_id,
                    "applicationId": application_id,
                    "documentType": document_type,
                    "documentTypeLabel": DOCUMENT_TYPE_LABELS.get(document_type, document_type),
                    "processInstanceId": process_id,
                    "hrQueueReady": hr_task_ready,
                    "hrNotified": True,
                    "pendingVisible": not hr_task_ready,
                    "tasklistUrl": os.getenv("HCNS_CAMUNDA_PUBLIC_URL", "http://localhost:8080/camunda/app/tasklist/default/"),
                    "templateFields": extracted_fields,
                    "extractedFields": extracted_fields,
                    "performance": {
                        "schemaVersion": STAGE_TIMING_SCHEMA_VERSION,
                        "timingsMs": {"camunda": camunda_duration_ms},
                    },
                })
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (HTTPError, URLError, RuntimeError) as exc:
                self.send_json({"error": f"Camunda local is unavailable: {exc}"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path.startswith("/external-dataset/typed/"):
            self.send_json(
                {"error": "Typed canonical projection is read-only; use GET"},
                HTTPStatus.METHOD_NOT_ALLOWED,
            )
            return
        if parsed.path == "/api/documents/process":
            upload = self._read_template_upload()
            if upload is None:
                return
            filename, media_type, content = upload
            document_id = str(uuid.uuid4())
            result_reference = (
                f"user_uploads/sessions/{document_id}/template_first/result.json"
            )
            try:
                result = self.template_processor.process(
                    DocumentSource(
                        document_id=document_id,
                        filename=filename,
                        content=content,
                        declared_media_type=media_type,
                        source_reference=document_id,
                    ),
                    result_reference=result_reference,
                )
                extension = Path(filename).suffix.casefold().lstrip(".")
                if extension not in result.detection.definition.supported_file_types:
                    raise TemplateUnsupportedError(
                        "Template does not support this file type"
                    )
                payload = result.public_dict()
                payload["documentId"] = document_id
                payload["documentTypeLabel"] = DOCUMENT_TYPE_LABELS.get(
                    str(payload.get("documentType", "")),
                    str(payload.get("documentType", "")),
                )
                payload["camundaEligible"] = (
                    payload.get("documentType") in CAMUNDA_UPLOAD_DOCUMENT_TYPES
                )
                payload["processing"].update(
                    {
                        "processedAt": utc_now(),
                        "originalFileName": filename,
                    }
                )
                persistence_started = time.perf_counter()
                session_dir = self.user_ocr.sessions_root / document_id
                result_dir = session_dir / "template_first"
                input_dir = session_dir / "input"
                result_dir.mkdir(parents=True, exist_ok=True)
                input_dir.mkdir(parents=True, exist_ok=True)
                extension = Path(filename).suffix.casefold()
                (input_dir / f"document{extension}").write_bytes(content)
                result_path = result_dir / "result.json"
                result_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                persistence_duration_ms = round(
                    (time.perf_counter() - persistence_started) * 1000,
                    3,
                )
                timings = payload["processing"].get("timingsMs")
                if isinstance(timings, dict):
                    timings["persistence"] = persistence_duration_ms
                    service_total = timings.get("serviceTotal", 0.0)
                    if isinstance(service_total, (int, float)) and not isinstance(
                        service_total, bool
                    ):
                        timings["total"] = round(
                            float(service_total) + persistence_duration_ms,
                            3,
                        )
                    (result_dir / "performance.json").write_text(
                        json.dumps(
                            {
                                "schemaVersion": STAGE_TIMING_SCHEMA_VERSION,
                                "timingsMs": timings,
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                if self.mvp_demo is not None:
                    uploader = self.mvp_demo.user_by_token(self._auth_token())
                    if uploader is not None:
                        self.mvp_demo.claim_document(uploader, document_id)
                self.send_json(payload)
            except TemplateUnsupportedError as exc:
                self.send_json(
                    {
                        "status": "REJECT_UNSUPPORTED",
                        "recommendedAction": "REJECT_UNSUPPORTED",
                        "errorCode": exc.code,
                    },
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            except TemplateTechnicalError as exc:
                status = (
                    HTTPStatus.SERVICE_UNAVAILABLE
                    if exc.code == "OCR_RUNTIME_UNAVAILABLE"
                    else HTTPStatus.UNPROCESSABLE_ENTITY
                )
                self.send_json(
                    {
                        "status": "TECHNICAL_ERROR",
                        "recommendedAction": "TECHNICAL_ERROR",
                        "errorCode": exc.code,
                    },
                    status,
                )
            except OSError:
                shutil.rmtree(
                    self.user_ocr.sessions_root / document_id,
                    ignore_errors=True,
                )
                self.send_json(
                    {
                        "status": "TECHNICAL_ERROR",
                        "recommendedAction": "TECHNICAL_ERROR",
                        "errorCode": "RESULT_STORAGE_FAILED",
                    },
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            except Exception:
                self.send_json(
                    {
                        "status": "TECHNICAL_ERROR",
                        "recommendedAction": "TECHNICAL_ERROR",
                        "errorCode": "TEMPLATE_PROCESSING_FAILED",
                    },
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return
        if parsed.path == "/ocr-ho-v2/shadow/review":
            if self.ocr_ho_shadow_root is None:
                self.send_json(
                    {"error": "OCR-HO-V2 shadow UAT is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            document_id = parse_qs(parsed.query).get("id", [""])[0]
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                self.send_json(
                    {"error": "Shadow UAT payload is empty or too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Shadow UAT payload must be an object")
                self.send_json(
                    save_shadow_review(self.ocr_ho_shadow_root, document_id, payload)
                )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/ocr-ho-v2/diagnostic/review":
            if self.ocr_ho_shadow_root is None:
                self.send_json({"error": "OCR-HO-V2 diagnostic is not configured"}, HTTPStatus.NOT_FOUND)
                return
            document_id = parse_qs(parsed.query).get("id", [""])[0]
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                    raise ValueError("Diagnostic payload is empty or too large")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Diagnostic payload must be an object")
                self.send_json(save_ocr_ho_diagnostic(self.ocr_ho_shadow_root, document_id, payload))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/ocr-ho-v2/diagnostic/draft":
            if self.ocr_ho_shadow_root is None:
                self.send_json({"error": "OCR-HO-V2 diagnostic is not configured"}, HTTPStatus.NOT_FOUND)
                return
            document_id = parse_qs(parsed.query).get("id", [""])[0]
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                    raise ValueError("Diagnostic draft is empty or too large")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Diagnostic draft must be an object")
                payload["draft"] = True
                self.send_json(save_ocr_ho_diagnostic(self.ocr_ho_shadow_root, document_id, payload))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/cccd-heldout/review/save":
            if self.cccd_heldout_root is None:
                self.send_json(
                    {"error": "CCCD Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            document_id = parse_qs(parsed.query).get("id", [""])[0]
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                self.send_json(
                    {"error": "Review payload is empty or too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                self.send_json(
                    save_cccd_ground_truth_review(
                        self.cccd_heldout_root,
                        document_id,
                        payload,
                    )
                )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/data31/coverage/save":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "DATA-31 Ground Truth coverage is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            case_id = parse_qs(parsed.query).get("id", [""])[0]
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                self.send_json(
                    {"error": "Request body is too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                self.send_json(
                    save_data31_coverage_decision(
                        self.external_dataset_root,
                        case_id,
                        payload,
                        inventory_path=self.external_dataset_inventory,
                        ground_truth_path=self.external_dataset_ground_truth,
                        decision_path=self.external_dataset_coverage_decision,
                    )
                )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/external-dataset/review/save":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "External dataset Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            case_id = parse_qs(parsed.query).get("id", [""])[0]
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                self.send_json(
                    {"error": "Review payload is empty or too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                self.send_json(
                    save_external_review(
                        self.external_dataset_root,
                        case_id,
                        payload,
                        inventory_path=self.external_dataset_inventory,
                        ground_truth_path=self.external_dataset_ground_truth,
                    )
                )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/external-dataset/review/lock":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "External dataset Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                self.send_json(
                    {"error": "Lock confirmation payload is empty or too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                self.send_json(
                    lock_external_ground_truth(
                        self.external_dataset_root,
                        confirm=payload.get("confirm") is True,
                        inventory_path=self.external_dataset_inventory,
                        ground_truth_path=self.external_dataset_ground_truth,
                    )
                )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/cccd-heldout/review/disposition":
            if self.cccd_heldout_root is None:
                self.send_json(
                    {"error": "CCCD Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            document_id = parse_qs(parsed.query).get("id", [""])[0]
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                self.send_json(
                    {"error": "Disposition payload is empty or too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                self.send_json(
                    set_review_disposition(
                        self.cccd_heldout_root,
                        document_id,
                        str(payload.get("disposition", "")),
                        payload.get("reason"),
                    )
                )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/cccd-heldout/review/lock":
            if self.cccd_heldout_root is None:
                self.send_json(
                    {"error": "CCCD Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                self.send_json(
                    {"error": "Lock confirmation payload is empty or too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                self.send_json(
                    lock_ground_truth(
                        self.cccd_heldout_root,
                        confirm=payload.get("confirm") is True,
                    )
                )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/cccd-heldout/review/evaluate":
            if self.cccd_heldout_root is None:
                self.send_json(
                    {"error": "CCCD Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            try:
                result = evaluate_cccd_ground_truth_once(
                    self.cccd_heldout_root,
                    python_executable=sys.executable,
                    script_path=REPO_ROOT / "scripts" / "evaluate_cccd_heldout_once.py",
                )
                self.send_json(result)
            except FileExistsError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, RuntimeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/phase14/review":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                self.send_json(
                    {"error": "Review payload is empty or too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                case_id = str(payload.get("caseId", ""))
                ground_truth = str(payload.get("groundTruth", "")).strip()
                compared = payload.get("comparedWithCrop") is True
                checked = payload.get("allTextChecked") is True
                if not PHASE14_CASE_ID_RE.fullmatch(case_id):
                    raise ValueError("Invalid Phase 14 case id")
                if not ground_truth:
                    raise ValueError("Ground Truth must not be empty")
                if not (compared and checked):
                    raise ValueError("Both review assertions are required")
                phase14_root = self.data_root / "output" / "phase14"
                benchmark_path = phase14_root / "line_benchmark_private.json"
                review_root = phase14_root
                expansion_root = self.data_root / "output" / "phase14_4"
                expansion_path = expansion_root / "review_queue_private.json"
                benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
                if expansion_path.is_file():
                    expansion = json.loads(expansion_path.read_text(encoding="utf-8"))
                    if any(case.get("caseId") == case_id for case in expansion.get("cases", [])):
                        benchmark = expansion
                        review_root = expansion_root
                if not any(case.get("caseId") == case_id for case in benchmark.get("cases", [])):
                    raise ValueError("Phase 14 case not found")
                reviews_path = review_root / "line_reviews.json"
                reviews = save_line_review(
                    reviews_path,
                    case_id=case_id,
                    ground_truth=ground_truth,
                    reviewed_at=utc_now(),
                )
                self.send_json(
                    {
                        "saved": True,
                        "caseId": case_id,
                        "reviewedCount": len(reviews["reviews"]),
                    }
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/user/phase15-review":
            session_id = parse_qs(parsed.query).get("id", [""])[0]
            session_dir = self.user_ocr.session_dir(session_id)
            if session_dir is None:
                self.send_json({"error": "Session not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                self.send_json(
                    {"error": "Review payload is empty or too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                fields = payload.get("fields")
                assertions = payload.get("assertions")
                if not isinstance(fields, dict):
                    raise ValueError("fields must be an object")
                if not isinstance(assertions, dict) or not (
                    assertions.get("comparedWithSource") is True
                    and assertions.get("allFieldsChecked") is True
                ):
                    raise ValueError("Both Phase 15 review assertions are required")

                result_path = session_dir / "result.json"
                result = json.loads(result_path.read_text(encoding="utf-8"))
                phase15 = result.get("phase15")
                if not isinstance(phase15, dict):
                    raise ValueError("Phase 15 result is not available")
                reviewed_at = utc_now()
                reviewed_extraction, corrected_count = apply_phase15_field_review(
                    phase15.get("extraction", {}),
                    fields,
                    reviewed_at=reviewed_at,
                )
                canonical = json.loads(
                    (session_dir / "phase15" / "canonical_document.json").read_text(
                        encoding="utf-8"
                    )
                )
                classification = dict(phase15["classification"])
                business = build_phase15_business_json(
                    session_id,
                    canonical,
                    classification,
                    reviewed_extraction,
                    contains_real_pii=True,
                    result_reference="phase15/idp_result_reviewed.json",
                )
                review_record = {
                    "schemaVersion": "1.0.0",
                    "sessionId": session_id,
                    "reviewStatus": "USER_REVIEWED",
                    "reviewedAt": reviewed_at,
                    "containsRealPII": True,
                    "assertions": {
                        "comparedWithSource": True,
                        "allFieldsChecked": True,
                    },
                    "correctedFieldCount": corrected_count,
                    "automaticResultReference": "phase15/idp_result.json",
                    "reviewedResultReference": "phase15/idp_result_reviewed.json",
                    "reviewedBusinessReference": "phase15/business_reviewed.json",
                }
                reviewed_idp = {
                    "schemaVersion": "2.0.0",
                    "sessionId": session_id,
                    "createdAt": reviewed_at,
                    "containsRealPII": True,
                    "classification": classification,
                    "extraction": reviewed_extraction,
                    "ingestion": phase15["ingestion"],
                    "review": review_record,
                    "businessJson": "phase15/business_reviewed.json",
                }
                phase15_dir = session_dir / "phase15"
                (phase15_dir / "review.json").write_text(
                    json.dumps(review_record, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                (phase15_dir / "idp_result_reviewed.json").write_text(
                    json.dumps(reviewed_idp, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                (phase15_dir / "business_reviewed.json").write_text(
                    json.dumps(business, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                phase15["extraction"] = reviewed_extraction
                phase15["status"] = business["idpStatus"]
                phase15["review"] = review_record
                result["document"]["structuredFields"] = reviewed_extraction["fields"]
                result_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self.send_json(result)
            except (
                KeyError,
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/user/review":
            session_id = parse_qs(parsed.query).get("id", [""])[0]
            session_dir = self.user_ocr.session_dir(session_id)
            if session_dir is None:
                self.send_json({"error": "Session not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REVIEW_BYTES:
                self.send_json(
                    {"error": "Review payload is empty or too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                pages = payload.get("pages")
                assertions = payload.get("assertions")
                identity_fields = payload.get("identityFields")
                if not isinstance(pages, list):
                    raise ValueError("pages must be an array")
                if not isinstance(assertions, dict):
                    raise ValueError("verification assertions are required")
                result = json.loads((session_dir / "result.json").read_text(encoding="utf-8"))
                self.send_json(
                    save_review(
                        session_dir,
                        result,
                        pages,
                        assertions,
                        identity_fields=identity_fields,
                    )
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/user/easyocr":
            session_id = parse_qs(parsed.query).get("id", [""])[0]
            session_dir = self.user_ocr.session_dir(session_id)
            if session_dir is None:
                self.send_json({"error": "Session not found"}, HTTPStatus.NOT_FOUND)
                return
            easy_python = self.data_root / "runtime" / "easyocr_venv" / "Scripts" / "python.exe"
            script_path = Path(__file__).with_name("run_easyocr_phase10.py")
            if not easy_python.is_file():
                self.send_json(
                    {"error": "EasyOCR runtime is not installed"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            try:
                subprocess.run(
                    [
                        str(easy_python),
                        str(script_path),
                        "--data-root",
                        str(self.data_root),
                        "--session-id",
                        session_id,
                        "--overwrite",
                    ],
                    cwd=str(script_path.parent),
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=True,
                )
                result = json.loads((session_dir / "result.json").read_text(encoding="utf-8"))
                self.send_json(review_payload(session_dir, result))
            except subprocess.TimeoutExpired:
                self.send_json(
                    {"error": "EasyOCR timed out"},
                    HTTPStatus.GATEWAY_TIMEOUT,
                )
            except subprocess.CalledProcessError:
                self.send_json(
                    {"error": "EasyOCR challenger failed"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return
        if parsed.path == "/user/controlled-pilot":
            session_id = parse_qs(parsed.query).get("id", [""])[0]
            session_dir = self.user_ocr.session_dir(session_id)
            if session_dir is None:
                self.send_json({"error": "Session not found"}, HTTPStatus.NOT_FOUND)
                return
            pilot_python = self.data_root / "runtime" / "easyocr_venv" / "Scripts" / "python.exe"
            script_path = Path(__file__).with_name("run_controlled_pilot_phase14_2.py")
            if not pilot_python.is_file():
                self.send_json(
                    {"error": "VietOCR runtime is not installed"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            try:
                subprocess.run(
                    [
                        str(pilot_python),
                        str(script_path),
                        "--data-root",
                        str(self.data_root),
                        "--session-id",
                        session_id,
                        "--overwrite",
                    ],
                    cwd=str(script_path.parent),
                    capture_output=True,
                    text=True,
                    timeout=1200,
                    check=True,
                )
                result = json.loads((session_dir / "result.json").read_text(encoding="utf-8"))
                self.send_json(review_payload(session_dir, result))
            except subprocess.TimeoutExpired:
                self.send_json(
                    {"error": "Phase 14.2 controlled pilot timed out"},
                    HTTPStatus.GATEWAY_TIMEOUT,
                )
            except subprocess.CalledProcessError:
                self.send_json(
                    {"error": "Phase 14.2 controlled pilot failed"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return
        if parsed.path == "/user/hybrid-ocr":
            session_id = parse_qs(parsed.query).get("id", [""])[0]
            session_dir = self.user_ocr.session_dir(session_id)
            if session_dir is None:
                self.send_json({"error": "Session not found"}, HTTPStatus.NOT_FOUND)
                return
            hybrid_python = self.data_root / "runtime" / "easyocr_venv" / "Scripts" / "python.exe"
            script_path = Path(__file__).with_name("run_hybrid_phase13_3.py")
            if not hybrid_python.is_file():
                self.send_json(
                    {"error": "EasyOCR/VietOCR runtime is not installed"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            try:
                subprocess.run(
                    [
                        str(hybrid_python),
                        str(script_path),
                        "--data-root",
                        str(self.data_root),
                        "--session-id",
                        session_id,
                        "--overwrite",
                    ],
                    cwd=str(script_path.parent),
                    capture_output=True,
                    text=True,
                    timeout=1200,
                    check=True,
                )
                result = json.loads((session_dir / "result.json").read_text(encoding="utf-8"))
                self.send_json(review_payload(session_dir, result))
            except subprocess.TimeoutExpired:
                self.send_json(
                    {"error": "Phase 13.3 hybrid OCR timed out"},
                    HTTPStatus.GATEWAY_TIMEOUT,
                )
            except subprocess.CalledProcessError:
                self.send_json(
                    {"error": "Phase 13.3 hybrid OCR failed"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return
        if parsed.path == "/user/reprocess":
            session_id = parse_qs(parsed.query).get("id", [""])[0]
            try:
                result = self.user_ocr.reprocess_session(session_id)
                self.send_json(result)
            except FileNotFoundError:
                self.send_json({"error": "Session not found"}, HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self.send_json(
                    {
                        "error": "Phase 9 processing failed",
                        "errorType": type(exc).__name__,
                    },
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return
        if parsed.path != "/user/upload":
            self.send_json({"error": "Unknown endpoint"}, HTTPStatus.NOT_FOUND)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_UPLOAD_BYTES:
            self.send_json(
                {"error": "File is empty or exceeds 50 MB"},
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self.send_json({"error": "multipart/form-data required"}, HTTPStatus.BAD_REQUEST)
            return
        body = self.rfile.read(content_length)
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii") + body
        )
        file_part = next(
            (
                part
                for part in message.iter_parts()
                if part.get_content_disposition() == "form-data" and part.get_filename()
            ),
            None,
        )
        if file_part is None:
            self.send_json({"error": "No file part"}, HTTPStatus.BAD_REQUEST)
            return
        submitted_filename = str(file_part.get_filename())
        original_filename = Path(submitted_filename).name
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            self.send_json(
                {"error": ("Supported formats: PNG, JPG, JPEG, PDF, DOCX, XLSX")},
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
            return
        content = file_part.get_payload(decode=True) or b""
        if not content:
            self.send_json({"error": "Uploaded file is empty"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            validate_local_upload(
                submitted_filename,
                content,
                declared_media_type=file_part.get_content_type(),
            )
        except DocumentIntakeError as exc:
            self.send_json(
                {
                    "error": "Upload rejected by the local safety policy",
                    "code": exc.code.value,
                },
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return
        session_id = str(uuid.uuid4())
        try:
            declared_document_type = next(
                (
                    str(part.get_payload(decode=True) or b"", "utf-8").strip()
                    for part in message.iter_parts()
                    if part.get_filename() is None
                    and part.get_param("name", header="content-disposition") == "documentType"
                ),
                None,
            )
            result = self.user_ocr.process_upload(
                session_id,
                original_filename,
                extension,
                content,
                declared_document_type,
            )
            self.send_json(result, HTTPStatus.CREATED)
        except ValueError as exc:
            if str(exc) == "OCR_DISABLED_BY_POLICY":
                shutil.rmtree(self.user_ocr.sessions_root / session_id, ignore_errors=True)
                self.send_json(
                    {
                        "status": "REJECT_UNSUPPORTED",
                        "recommendedAction": "REJECT_UNSUPPORTED",
                        "errorCode": "OCR_DISABLED_BY_POLICY",
                        "message": (
                            "Ảnh/PDF scan chỉ nhận OCR cho CV, hợp đồng, phụ lục hợp đồng, "
                            "quyết định nhân sự, CCCD hoặc chứng chỉ."
                        ),
                    },
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )
                return
            raise
        except Exception as exc:
            failure_dir = self.user_ocr.sessions_root / session_id
            failure_dir.mkdir(parents=True, exist_ok=True)
            (failure_dir / "failure.json").write_text(
                json.dumps(
                    {
                        "sessionId": session_id,
                        "createdAt": utc_now(),
                        "errorType": type(exc).__name__,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            self.send_json(
                {"error": "Local OCR processing failed", "errorType": type(exc).__name__},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _read_template_upload(self) -> tuple[str, str | None, bytes] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_UPLOAD_BYTES:
            self.send_json(
                {
                    "status": "TECHNICAL_ERROR",
                    "recommendedAction": "TECHNICAL_ERROR",
                    "errorCode": "INVALID_UPLOAD_SIZE",
                },
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return None
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self.send_json(
                {
                    "status": "TECHNICAL_ERROR",
                    "recommendedAction": "TECHNICAL_ERROR",
                    "errorCode": "MULTIPART_REQUIRED",
                },
                HTTPStatus.BAD_REQUEST,
            )
            return None
        body = self.rfile.read(content_length)
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii")
            + body
        )
        file_part = next(
            (
                part
                for part in message.iter_parts()
                if part.get_content_disposition() == "form-data"
                and part.get_param("name", header="content-disposition") == "file"
                and part.get_filename()
            ),
            None,
        )
        if file_part is None:
            self.send_json(
                {
                    "status": "TECHNICAL_ERROR",
                    "recommendedAction": "TECHNICAL_ERROR",
                    "errorCode": "FILE_PART_REQUIRED",
                },
                HTTPStatus.BAD_REQUEST,
            )
            return None
        submitted_filename = str(file_part.get_filename())
        filename = Path(submitted_filename).name
        suffix = Path(filename).suffix.casefold()
        if suffix not in TEMPLATE_ALLOWED_EXTENSIONS:
            self.send_json(
                {
                    "status": "REJECT_UNSUPPORTED",
                    "recommendedAction": "REJECT_UNSUPPORTED",
                    "errorCode": "SUPPORTED_TEMPLATE_FORMAT_REQUIRED",
                },
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
            return None
        content = file_part.get_payload(decode=True) or b""
        if not content:
            self.send_json(
                {
                    "status": "TECHNICAL_ERROR",
                    "recommendedAction": "TECHNICAL_ERROR",
                    "errorCode": "EMPTY_FILE",
                },
                HTTPStatus.BAD_REQUEST,
            )
            return None
        return filename, file_part.get_content_type(), content

    def do_DELETE(self) -> None:
        if not self._request_host_is_local():
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/external-dataset/typed/"):
            self.send_json(
                {"error": "Typed canonical projection is read-only; use GET"},
                HTTPStatus.METHOD_NOT_ALLOWED,
            )
            return
        if parsed.path != "/user/session":
            self.send_json({"error": "Unknown endpoint"}, HTTPStatus.NOT_FOUND)
            return
        session_id = parse_qs(parsed.query).get("id", [""])[0]
        session_dir = self.user_ocr.session_dir(session_id)
        if session_dir is None:
            self.send_json({"error": "Session not found"}, HTTPStatus.NOT_FOUND)
            return
        shutil.rmtree(session_dir)
        self.send_json({"deleted": True})

    def do_GET(self) -> None:
        if not self._request_host_is_local():
            return
        try:
            self._do_GET()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            self.send_json(
                {
                    "error": "Local dashboard request failed",
                    "errorType": type(exc).__name__,
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _request_host_is_local(self) -> bool:
        try:
            require_local_host_header(self.headers.get("Host", ""))
        except ValueError:
            self.send_json(
                {"error": "Local dashboard Host header is required"},
                HTTPStatus.BAD_REQUEST,
            )
            return False
        return True

    def _do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/":
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", "http://localhost:3000")
            self.cors_headers()
            self.end_headers()
            return

        if parsed.path == "/api/camunda/queue":
            try:
                store = self._demo_store()
                user = self._require_user()
                engine_url = _local_camunda_url()
                tasks = _camunda_get(
                    f"{engine_url}/task?processDefinitionKey=hr_document_agent_mvp_v2"
                )
                queue: list[dict[str, Any]] = []
                owned_documents = store.owner_of_all()
                is_hr_or_admin = user["role"] in {ROLE_HR, ROLE_ADMIN}
                managed_users: set[str] | None = None
                if user["role"] == ROLE_HR:
                    managed = store.managed_usernames(user["username"])
                    managed_users = set(managed) if managed else None
                camunda_application_ids: set[str] = set()
                for task in tasks if isinstance(tasks, list) else []:
                    if not isinstance(task, dict):
                        continue
                    definition_key = task.get("taskDefinitionKey")
                    if definition_key not in {"UserReview", "HRReview"}:
                        continue
                    task_id = task.get("id")
                    if not isinstance(task_id, str):
                        continue
                    variables = _camunda_get(f"{engine_url}/task/{task_id}/variables")
                    document_id = _camunda_value(variables, "documentReference")
                    if document_id is None:
                        continue
                    if not is_hr_or_admin and (
                        document_id not in owned_documents
                        or owned_documents[document_id] != user["username"]
                    ):
                        continue
                    submitted_by = owned_documents.get(document_id, "")
                    if (
                        managed_users is not None
                        and submitted_by
                        and submitted_by not in managed_users
                    ):
                        continue
                    application_id = _camunda_value(variables, "applicationId") or ""
                    if application_id:
                        camunda_application_ids.add(application_id)
                        if is_hr_or_admin and definition_key == "HRReview":
                            store.resolve_hr_pending(application_id)
                    document_type = (
                        _camunda_value(variables, "documentType")
                        or _camunda_value(variables, "declaredDocumentType")
                        or "HR_DOCUMENT"
                    )
                    submission = (
                        store.get_submission(application_id)
                        if application_id
                        else None
                    )
                    if submission is None:
                        submission = store.get_submission_by_document(document_id)
                    extracted_fields: dict[str, Any] = {}
                    template_result = None
                    if isinstance(submission, dict) and isinstance(
                        submission.get("extractedFields"), dict
                    ):
                        extracted_fields = dict(submission["extractedFields"])
                    else:
                        template_result = self.user_ocr.template_result(document_id)
                        if template_result is not None:
                            extracted_fields = extracted_fields_from_template_result(
                                template_result
                            )
                    queue.append(
                        {
                            "taskId": task_id,
                            "role": "employee" if definition_key == "UserReview" else "hr",
                            "taskDefinitionKey": definition_key,
                            "actionable": definition_key == "HRReview" and is_hr_or_admin,
                            "statusLabel": _queue_status_label(
                                definition_key, viewer_is_hr=is_hr_or_admin
                            ),
                            "taskName": str(task.get("name", "Human review")),
                            "documentId": document_id,
                            "documentType": document_type,
                            "documentTypeLabel": DOCUMENT_TYPE_LABELS.get(
                                document_type, document_type
                            ),
                            "applicationId": application_id,
                            "submittedBy": owned_documents.get(document_id, ""),
                            "created": str(task.get("created", "")),
                            "inspectable": bool(extracted_fields) or template_result is not None,
                            "extractedFields": extracted_fields,
                            "sourceFile": (
                                str(submission.get("sourceFile", ""))
                                if isinstance(submission, dict)
                                else ""
                            ),
                        }
                    )
                if is_hr_or_admin:
                    for pending in store.list_hr_pending():
                        application_id = str(pending.get("applicationId", ""))
                        if not application_id or application_id in camunda_application_ids:
                            continue
                        document_id = str(pending.get("documentId", ""))
                        document_type = str(pending.get("documentType", "HR_DOCUMENT"))
                        pending_owner = str(pending.get("owner", ""))
                        if (
                            managed_users is not None
                            and pending_owner
                            and pending_owner not in managed_users
                        ):
                            continue
                        pending_fields = pending.get("extractedFields")
                        extracted_fields = (
                            dict(pending_fields)
                            if isinstance(pending_fields, dict)
                            else {}
                        )
                        if not extracted_fields:
                            submission = store.get_submission(application_id)
                            if isinstance(submission, dict) and isinstance(
                                submission.get("extractedFields"), dict
                            ):
                                extracted_fields = dict(submission["extractedFields"])
                        else:
                            submission = store.get_submission(application_id)
                        source_file = ""
                        if isinstance(submission, dict):
                            source_file = str(submission.get("sourceFile") or "")
                        if not source_file:
                            archive_entry = store.get_archive(application_id)
                            if isinstance(archive_entry, dict):
                                source_file = str(archive_entry.get("sourceFile") or "")
                        queue.insert(
                            0,
                            {
                                "taskId": f"pending-{application_id}",
                                "role": "hr",
                                "taskDefinitionKey": "PENDING",
                                "actionable": True,
                                "pending": True,
                                "statusLabel": "Chờ HR duyệt (local)",
                                "taskName": "Đơn mới — duyệt được ngay",
                                "documentId": document_id,
                                "documentType": document_type,
                                "documentTypeLabel": DOCUMENT_TYPE_LABELS.get(
                                    document_type, document_type
                                ),
                                "applicationId": application_id,
                                "submittedBy": pending_owner,
                                "created": str(pending.get("submittedAt", "")),
                                "inspectable": bool(extracted_fields)
                                or self.user_ocr.template_result(document_id)
                                is not None,
                                "extractedFields": extracted_fields,
                                "sourceFile": source_file,
                            },
                        )
                queue.sort(
                    key=lambda item: (
                        0
                        if item.get("taskDefinitionKey") == "HRReview"
                        else 1
                        if item.get("taskDefinitionKey") == "PENDING"
                        else 2,
                        str(item.get("created", "")),
                    ),
                )
                self.send_json({"queue": queue})
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            except (HTTPError, URLError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": f"Camunda local is unavailable: {exc}"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return

        if parsed.path == "/api/camunda/submission":
            try:
                user = self._require_user()
                application_id = query.get("applicationId", [""])[0]
                document_id = query.get("documentId", [""])[0]
                store = self._demo_store()
                submission = None
                if application_id:
                    submission = store.get_submission(application_id)
                if submission is None and document_id:
                    submission = store.get_submission_by_document(document_id)
                if submission is None and document_id:
                    self._require_document_access(user, document_id)
                    result = self.user_ocr.template_result(document_id)
                    if result is None:
                        self.send_json(
                            {"error": "Không tìm thấy thông tin nộp đơn"},
                            HTTPStatus.NOT_FOUND,
                        )
                        return
                    extracted = extracted_fields_from_template_result(result)
                    processing = result.get("processing")
                    source_file = (
                        str(processing.get("originalFileName", ""))
                        if isinstance(processing, dict)
                        else ""
                    )
                    self.send_json(
                        {
                            "applicationId": store.application_of(document_id),
                            "documentId": document_id,
                            "documentType": result.get("documentType"),
                            "documentTypeLabel": DOCUMENT_TYPE_LABELS.get(
                                str(result.get("documentType", "")),
                                str(result.get("documentType", "")),
                            ),
                            "owner": store.owner_of(document_id) or "",
                            "extractedFields": extracted,
                            "sourceFile": source_file,
                            "submittedAt": (
                                str(processing.get("correctedAt") or processing.get("processedAt") or "")
                                if isinstance(processing, dict)
                                else ""
                            ),
                        }
                    )
                    return
                if submission is None:
                    self.send_json(
                        {"error": "Không tìm thấy thông tin nộp đơn"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                document_ref = str(submission.get("documentId", ""))
                self._require_document_access(user, document_ref)
                document_type = str(submission.get("documentType", ""))
                self.send_json(
                    {
                        **submission,
                        "documentTypeLabel": DOCUMENT_TYPE_LABELS.get(
                            document_type, document_type
                        ),
                    }
                )
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            except (ValueError, TypeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/camunda/case":
            process_id = query.get("id", [""])[0]
            if CAMUNDA_PROCESS_ID_PATTERN.fullmatch(process_id) is None:
                self.send_json(
                    {"error": "Camunda process instance id is invalid"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            try:
                engine_url = _local_camunda_url()
                tasks = _camunda_get(
                    f"{engine_url}/task?processInstanceId={process_id}"
                )
                incidents = _camunda_get(
                    f"{engine_url}/incident?processInstanceId={process_id}"
                )
                history = _camunda_get(
                    f"{engine_url}/history/process-instance/{process_id}"
                )
                variables = _camunda_get(
                    f"{engine_url}/history/variable-instance?processInstanceId={process_id}"
                )
                user = self._require_user()
                document_ref = (
                    _camunda_history_value(variables, "documentReference")
                    or _camunda_history_value(variables, "documentId")
                )
                if document_ref is not None:
                    self._require_document_access(user, document_ref)
                elif user["role"] not in {ROLE_HR, ROLE_ADMIN}:
                    raise MvpDemoError("Không có quyền truy cập hồ sơ", HTTPStatus.FORBIDDEN)
                task = next(
                    (item for item in tasks if isinstance(item, dict)),
                    None,
                ) if isinstance(tasks, list) else None
                incident_count = len(incidents) if isinstance(incidents, list) else 0
                task_key = str(task.get("taskDefinitionKey", "")) if task else ""
                if incident_count:
                    state = "INCIDENT"
                elif task_key == "UserReview":
                    state = "AWAITING_USER_REVIEW"
                elif task_key in {"HRReview", "FinalHR"}:
                    state = "AWAITING_HR_REVIEW"
                elif task_key == "UploadAgain":
                    state = "REUPLOAD_REQUIRED"
                elif isinstance(history, dict) and history.get("state") == "COMPLETED":
                    rejected = (
                        _camunda_history_value(variables, "hrReviewDecision") == "REJECTED"
                        or _camunda_history_value(variables, "finalHrDecision") == "REJECTED"
                    )
                    state = "REJECTED" if rejected else "COMPLETED"
                else:
                    state = "PROCESSING"
                self.send_json(
                    {
                        "processInstanceId": process_id,
                        "applicationId": _camunda_history_value(variables, "applicationId"),
                        "documentType": (
                            _camunda_history_value(variables, "documentType")
                            or _camunda_history_value(variables, "declaredDocumentType")
                            or "HR_DOCUMENT"
                        ),
                        "state": state,
                        "taskId": task.get("id") if task else None,
                        "taskName": task.get("name") if task else None,
                        "incidentCount": incident_count,
                        "tasklistUrl": "http://localhost:8080/camunda/app/tasklist/default/",
                    }
                )
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            except HTTPError as exc:
                if exc.code == HTTPStatus.NOT_FOUND:
                    self.send_json({"error": "Camunda case not found"}, HTTPStatus.NOT_FOUND)
                else:
                    self.send_json(
                        {"error": f"Camunda local is unavailable: {exc}"},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
            except (URLError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                self.send_json(
                    {"error": f"Camunda local is unavailable: {exc}"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return

        if parsed.path == "/api/auth/me":
            try:
                user = self._require_user()
                session = build_public_user(user)
                session["token"] = self._auth_token()
                self.send_json({"user": session, "session": session})
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/admin/users":
            try:
                actor = self._require_user({ROLE_ADMIN})
                self.send_json({"users": self._demo_store().list_users(actor)})
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/admin/audit":
            try:
                actor = self._require_user({ROLE_ADMIN})
                self.send_json({"audit": self._demo_store().audit_log(actor)})
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/admin/org-tree":
            try:
                actor = self._require_user({ROLE_ADMIN})
                self.send_json({"tree": self._demo_store().org_tree(actor)})
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/archive":
            try:
                user = self._require_user({ROLE_USER, ROLE_HR})
                items = self._demo_store().list_archive_for(user)
                enriched = []
                for item in items:
                    document_type = str(item.get("documentType", ""))
                    download_ready = bool(item.get("downloadReady")) and str(
                        item.get("decision") or item.get("status") or ""
                    ) == "CONFIRMED"
                    source_format = str(item.get("sourceFormat") or "")
                    if not source_format and item.get("sourceFile"):
                        source_format = Path(str(item.get("sourceFile"))).suffix.lstrip(
                            "."
                        )
                    enriched.append(
                        {
                            **item,
                            "documentTypeLabel": DOCUMENT_TYPE_LABELS.get(
                                document_type, document_type
                            ),
                            "sourceFormat": source_format,
                            "canDownload": download_ready,
                        }
                    )
                self.send_json({"archive": enriched, "viewerRole": user["role"]})
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/archive/download":
            try:
                user = self._require_user({ROLE_USER, ROLE_HR, ROLE_ADMIN})
                application_id = query.get("applicationId", [""])[0]
                store = self._demo_store()
                if not store.can_access_archive(user, application_id):
                    raise MvpDemoError(
                        "Không có quyền tải bằng chứng này", HTTPStatus.FORBIDDEN
                    )
                entry = store.get_archive(application_id)
                if entry is None:
                    self.send_json(
                        {"error": "Không tìm thấy hồ sơ lưu"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                if str(entry.get("decision") or entry.get("status") or "") != "CONFIRMED":
                    self.send_json(
                        {
                            "error": "Chỉ tải được file sau khi HR chấp nhận đơn",
                            "errorCode": "DOWNLOAD_AFTER_ACCEPT_ONLY",
                        },
                        HTTPStatus.FORBIDDEN,
                    )
                    return
                if not entry.get("downloadReady"):
                    self.send_json(
                        {
                            "error": "File bằng chứng chưa sẵn sàng. HR cần chấp nhận lại đơn.",
                            "errorCode": "DOWNLOAD_NOT_READY",
                        },
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                source_path = store.archive_source_path(application_id)
                if source_path is None or not source_path.is_file():
                    self.send_json(
                        {
                            "error": "File gốc chưa được lưu local sau khi chấp nhận",
                            "errorCode": "ARCHIVE_FILE_MISSING",
                        },
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                download_name = str(entry.get("sourceFile") or source_path.name)
                content_type = (
                    mimetypes.guess_type(source_path.name)[0]
                    or "application/octet-stream"
                )
                self.send_file(source_path, content_type, download_name=download_name)
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/notifications":
            try:
                user = self._require_user()
                store = self._demo_store()
                _, cursor = store.events_since(user, 0)
                self.send_json(
                    {
                        "notifications": store.notifications_for(user["username"]),
                        "cursor": cursor,
                    }
                )
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/events":
            try:
                user = self._require_user()
                events, cursor = self._demo_store().events_since(
                    user, _parse_cursor(query.get("cursor", ["0"])[0])
                )
                self.send_json({"events": events, "cursor": cursor})
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/events/stream":
            self._stream_events(query)
            return

        if parsed.path == "/api/documents/timeline":
            application_id = query.get("applicationId", [""])[0]
            if APPLICATION_ID_RE.fullmatch(application_id) is None:
                self.send_json({"error": "Application id invalid"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                user = self._require_user()
                self.send_json(
                    {"timeline": self._demo_store().timeline(application_id)}
                )
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/documents/export":
            document_id = query.get("documentId", [""])[0]
            export_format = query.get("format", ["docx"])[0]
            try:
                user = self._require_user()
                self._require_document_access(user, document_id)
                result = self.user_ocr.template_result(document_id)
                if result is None or not isinstance(result.get("data"), dict):
                    self.send_json({"error": "Leave result not found"}, HTTPStatus.NOT_FOUND)
                    return
                data = result["data"]
                template_path = REPO_ROOT / "hcns format" / "01_don_xin_nghi_phep_v1.docx"
                if export_format == "pdf":
                    body = render_leave_pdf(data)
                    self.send_bytes(
                        body,
                        "application/pdf",
                        download_name=f"don-xin-nghi-phep-{document_id[:8]}.pdf",
                    )
                else:
                    body = render_leave_docx(data, template_path)
                    self.send_bytes(
                        body,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        download_name=f"don-xin-nghi-phep-{document_id[:8]}.docx",
                    )
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            except (OSError, ValueError, RuntimeError) as exc:
                self.send_json({"error": f"Export failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if parsed.path == "/api/documents/sessions":
            self.send_json({"sessions": self.user_ocr.list_template_sessions()})
            return

        if parsed.path == "/benchmark/summary":
            try:
                self.send_json(build_local_benchmark_summary(DashboardHandler))
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(
                    {"error": f"Local benchmark unavailable: {exc}"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/ocr-ho-v2/diagnostic/summary":
            if self.ocr_ho_shadow_root is None:
                self.send_json({"error": "OCR-HO-V2 diagnostic is not configured"}, HTTPStatus.NOT_FOUND)
                return
            try:
                self.send_json(load_ocr_ho_diagnostic_summary(self.ocr_ho_shadow_root))
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return

        if parsed.path == "/ocr-ho-v2/diagnostic/document":
            if self.ocr_ho_shadow_root is None:
                self.send_json({"error": "OCR-HO-V2 diagnostic is not configured"}, HTTPStatus.NOT_FOUND)
                return
            try:
                document_id = query.get("id", [""])[0]
                mode = query.get("mode", ["detail"])[0]
                if mode == "preview":
                    source = resolve_ocr_ho_diagnostic_preview(self.ocr_ho_shadow_root, document_id)
                    self.send_file(
                        source,
                        mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                    )
                elif mode == "detail":
                    self.send_json(load_ocr_ho_diagnostic_document(self.ocr_ho_shadow_root, document_id))
                else:
                    self.send_json({"error": "Invalid diagnostic document mode"}, HTTPStatus.BAD_REQUEST)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                self.send_json({"error": "OCR-HO-V2 diagnostic document is unavailable"}, HTTPStatus.NOT_FOUND)
            return

        if parsed.path == "/ocr-ho-v2/shadow/summary":
            if self.ocr_ho_shadow_root is None:
                self.send_json(
                    {"error": "OCR-HO-V2 shadow UAT is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            try:
                self.send_json(load_shadow_summary(self.ocr_ho_shadow_root))
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(
                    {"error": f"OCR-HO-V2 shadow UAT unavailable: {exc}"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/ocr-ho-v2/shadow/document":
            if self.ocr_ho_shadow_root is None:
                self.send_json(
                    {"error": "OCR-HO-V2 shadow UAT is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            document_id = query.get("id", [""])[0]
            mode = query.get("mode", ["detail"])[0]
            try:
                source = resolve_shadow_source(self.ocr_ho_shadow_root, document_id)
                if mode == "preview":
                    self.send_file(
                        source,
                        mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                    )
                elif mode == "source":
                    self.send_file(
                        source,
                        mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                        f"{document_id}{source.suffix.lower()}",
                    )
                elif mode == "detail":
                    self.send_json(load_shadow_document(self.ocr_ho_shadow_root, document_id))
                else:
                    self.send_json(
                        {"error": "Invalid shadow document mode"},
                        HTTPStatus.BAD_REQUEST,
                    )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (OSError, FileNotFoundError, KeyError, json.JSONDecodeError):
                self.send_json(
                    {"error": "OCR-HO-V2 shadow document is unavailable"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/api/documents/result":
            document_id = query.get("id", [""])[0]
            try:
                user = self._require_user()
                self._require_document_access(user, document_id)
                result = self.user_ocr.template_result(document_id)
                if result is None:
                    self.send_json(
                        {"error": "Template-first result not found"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_json(result)
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/documents/comparison":
            document_id = query.get("id", [""])[0]
            comparison = self.user_ocr.template_comparison(document_id)
            if comparison is None:
                self.send_json(
                    {"error": "Template comparison not found"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            self.send_json(comparison)
            return

        if parsed.path == "/api/documents/source":
            document_id = query.get("id", [""])[0]
            application_id = query.get("applicationId", [""])[0]
            try:
                user = self._require_user()
                source_path = None
                download_name = "document"
                if document_id:
                    try:
                        self._require_document_access(user, document_id)
                        source_path = self.user_ocr.template_source(document_id)
                        if source_path is not None:
                            download_name = source_path.name
                    except MvpDemoError:
                        source_path = None
                # Fallback: archived original after submit (HR/user evidence copy).
                if source_path is None and application_id:
                    store = self._demo_store()
                    if not store.can_access_archive(user, application_id):
                        raise MvpDemoError(
                            "Không có quyền xem tài liệu gốc", HTTPStatus.FORBIDDEN
                        )
                    entry = store.get_archive(application_id)
                    source_path = store.archive_source_path(application_id)
                    if entry is not None:
                        download_name = str(entry.get("sourceFile") or "document")
                        archived_doc = str(entry.get("documentId") or "")
                        if archived_doc and not document_id:
                            document_id = archived_doc
                if source_path is None or not source_path.is_file():
                    self.send_json(
                        {"error": "Không tìm thấy file gốc đã nộp"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                content_type = (
                    mimetypes.guess_type(source_path.name)[0]
                    or "application/octet-stream"
                )
                suffix = source_path.suffix.casefold()
                viewable = suffix in {
                    ".pdf",
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                    ".gif",
                }
                self.send_bytes(
                    source_path.read_bytes(),
                    content_type,
                    download_name if Path(download_name).suffix else source_path.name,
                    inline=viewable,
                )
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            return

        if parsed.path == "/api/documents/preview":
            document_id = query.get("id", [""])[0]
            application_id = query.get("applicationId", [""])[0]
            try:
                user = self._require_user()
                preview: tuple[bytes, str] | None = None
                preview_name = "preview.png"
                source_for_preview: Path | None = None

                def _preview_from_path(path: Path) -> tuple[bytes, str] | None:
                    suffix = path.suffix.casefold()
                    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                        content_type = (
                            mimetypes.guess_type(path.name)[0]
                            or "application/octet-stream"
                        )
                        return path.read_bytes(), content_type
                    if suffix == ".pdf" and pdfium is not None:
                        document = pdfium.PdfDocument(str(path))
                        try:
                            if len(document) == 0:
                                return None
                            page = document[0]
                            try:
                                bitmap = page.render(scale=1.6)
                                try:
                                    image = bitmap.to_pil().convert("RGB")
                                finally:
                                    bitmap.close()
                            finally:
                                page.close()
                        finally:
                            document.close()
                        output = BytesIO()
                        image.save(output, format="PNG", optimize=True)
                        return output.getvalue(), "image/png"
                    if suffix == ".docx":
                        # Browser cannot inline DOCX; force client to use /source download.
                        return None
                    return None

                if document_id:
                    try:
                        self._require_document_access(user, document_id)
                        source_for_preview = self.user_ocr.template_source(document_id)
                        try:
                            preview = self.user_ocr.template_preview(document_id)
                        except (OSError, RuntimeError, ValueError):
                            preview = None
                        # DOCX: template_preview returns raw bytes — reject for inline view.
                        if (
                            preview is not None
                            and source_for_preview is not None
                            and source_for_preview.suffix.casefold() == ".docx"
                        ):
                            preview = None
                    except MvpDemoError:
                        # Fall through to archive for HR evidence after submit.
                        preview = None
                if preview is None and application_id:
                    store = self._demo_store()
                    if not store.can_access_archive(user, application_id):
                        if document_id:
                            raise MvpDemoError(
                                "Không có quyền xem tài liệu gốc", HTTPStatus.FORBIDDEN
                            )
                        raise MvpDemoError(
                            "Không có quyền xem tài liệu gốc", HTTPStatus.FORBIDDEN
                        )
                    source_path = store.archive_source_path(application_id)
                    if source_path is not None and source_path.is_file():
                        source_for_preview = source_path
                        preview = _preview_from_path(source_path)
                        preview_name = source_path.name
                if preview is None:
                    # Hint client: DOCX should download via /source.
                    if (
                        source_for_preview is not None
                        and source_for_preview.suffix.casefold() == ".docx"
                    ):
                        self.send_json(
                            {
                                "error": "DOCX không xem trực tiếp trên trình duyệt — dùng tải file gốc",
                                "errorCode": "PREVIEW_DOCX_DOWNLOAD",
                                "downloadVia": "source",
                            },
                            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                        )
                        return
                    self.send_json(
                        {"error": "Không tạo được bản xem trước file gốc"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                body, content_type = preview
                self.send_bytes(
                    body,
                    content_type,
                    preview_name if content_type.startswith("image/") else None,
                    inline=True,
                )
            except MvpDemoError as exc:
                self._handle_mvp_error(exc)
            except (OSError, RuntimeError, ValueError) as exc:
                self.send_json(
                    {"error": f"Template-first preview unavailable: {exc}"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return

        if parsed.path == "/cccd-heldout/review/summary":
            if self.cccd_heldout_root is None:
                self.send_json(
                    {"error": "CCCD Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            try:
                self.send_json(load_review_summary(self.cccd_heldout_root))
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(
                    {"error": f"CCCD Ground Truth review unavailable: {exc}"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/data31/coverage/summary":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "DATA-31 Ground Truth coverage is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            try:
                self.send_json(
                    load_data31_coverage_summary(
                        self.external_dataset_root,
                        inventory_path=self.external_dataset_inventory,
                        ground_truth_path=self.external_dataset_ground_truth,
                        decision_path=self.external_dataset_coverage_decision,
                    )
                )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(
                    {"error": f"DATA-31 coverage unavailable: {exc}"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/external-dataset/review/summary":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "External dataset Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            try:
                self.send_json(
                    load_external_review_summary(
                        self.external_dataset_root,
                        inventory_path=self.external_dataset_inventory,
                        ground_truth_path=self.external_dataset_ground_truth,
                    )
                )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(
                    {"error": f"External dataset review unavailable: {exc}"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/external-dataset/typed/summary":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "Typed canonical projection is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            try:
                self.send_json(
                    load_typed_summary(
                        resolve_typed_paths(
                            self.external_dataset_root,
                            projection_path=self.external_dataset_typed_projection,
                            approval_path=self.external_dataset_typed_approval,
                            aggregate_report_path=self.external_dataset_typed_report,
                        )
                    )
                )
            except TypedDatasetError as exc:
                self.send_json(
                    {"error": f"Typed canonical projection unavailable: {exc}"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return

        if parsed.path == "/external-dataset/prediction/summary":
            if self.external_dataset_root is None:
                self.send_json({"error": "DATA-12 prediction artifact is not configured"}, HTTPStatus.NOT_FOUND)
                return
            try:
                self.send_json(
                    load_prediction_summary(
                        resolve_prediction_paths(
                            self.external_dataset_root,
                            prediction_path=self.external_dataset_predictions,
                            report_path=self.external_dataset_prediction_report,
                            evaluation_marker_path=self.external_dataset_prediction_marker,
                        )
                    )
                )
            except (OSError, PredictionArtifactError) as exc:
                self.send_json({"error": f"DATA-12 prediction unavailable: {exc}"}, HTTPStatus.NOT_FOUND)
            return

        if parsed.path == "/external-dataset/prediction/document":
            if self.external_dataset_root is None:
                self.send_json({"error": "DATA-12 prediction artifact is not configured"}, HTTPStatus.NOT_FOUND)
                return
            case_id = query.get("id", [""])[0]
            try:
                self.send_json(
                    load_prediction_document(
                        resolve_prediction_paths(
                            self.external_dataset_root,
                            prediction_path=self.external_dataset_predictions,
                            report_path=self.external_dataset_prediction_report,
                            evaluation_marker_path=self.external_dataset_prediction_marker,
                        ),
                        case_id,
                        self.external_dataset_ground_truth,
                    )
                )
            except FileNotFoundError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            except (OSError, PredictionArtifactError) as exc:
                self.send_json({"error": f"DATA-12 prediction unavailable: {exc}"}, HTTPStatus.NOT_FOUND)
            return

        if parsed.path in {
            "/external-dataset/prediction-v13/summary",
            "/external-dataset/prediction-v13/document",
        }:
            if self.external_dataset_root is None:
                self.send_json({"error": "DATA-13 prediction artifact is not configured"}, HTTPStatus.NOT_FOUND)
                return
            paths = resolve_prediction_paths(
                self.external_dataset_root,
                prediction_path=self.external_dataset_predictions_data13,
                report_path=self.external_dataset_prediction_report_data13,
                evaluation_marker_path=self.external_dataset_prediction_marker_data13,
                version="data13",
            )
            try:
                if parsed.path.endswith("/summary"):
                    self.send_json(load_prediction_summary(paths))
                else:
                    self.send_json(
                        load_prediction_document(
                            paths,
                            query.get("id", [""])[0],
                            self.external_dataset_ground_truth,
                        )
                    )
            except FileNotFoundError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            except (OSError, PredictionArtifactError) as exc:
                self.send_json({"error": f"DATA-13 prediction unavailable: {exc}"}, HTTPStatus.NOT_FOUND)
            return

        if parsed.path == "/external-dataset/typed/document":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "Typed canonical projection is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            case_id = query.get("id", [""])[0]
            include_source_value = query.get("includeSourceValue", ["false"])[0] == "true"
            try:
                self.send_json(
                    load_typed_document(
                        resolve_typed_paths(
                            self.external_dataset_root,
                            projection_path=self.external_dataset_typed_projection,
                            approval_path=self.external_dataset_typed_approval,
                            aggregate_report_path=self.external_dataset_typed_report,
                        ),
                        case_id,
                        include_source_value=include_source_value,
                    )
                )
            except FileNotFoundError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            except TypedDatasetError as exc:
                self.send_json(
                    {"error": f"Typed canonical document unavailable: {exc}"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return

        if parsed.path == "/external-dataset/typed/export":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "Typed canonical projection is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            format_name = query.get("format", ["json"])[0].casefold()
            try:
                body, content_type, download_name = build_typed_export(
                    resolve_typed_paths(
                        self.external_dataset_root,
                        projection_path=self.external_dataset_typed_projection,
                        approval_path=self.external_dataset_typed_approval,
                        aggregate_report_path=self.external_dataset_typed_report,
                    ),
                    format_name,
                )
                self.send_bytes(body, content_type, download_name)
            except TypedDatasetError as exc:
                status = (
                    HTTPStatus.BAD_REQUEST
                    if "format" in str(exc)
                    else HTTPStatus.SERVICE_UNAVAILABLE
                )
                self.send_json(
                    {"error": f"Typed canonical export unavailable: {exc}"},
                    status,
                )
            return

        if parsed.path == "/data31/coverage/document":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "DATA-31 Ground Truth coverage is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            case_id = query.get("id", [""])[0]
            mode = query.get("mode", ["detail"])[0]
            try:
                source = resolve_external_review_source(
                    self.external_dataset_root,
                    case_id,
                    inventory_path=self.external_dataset_inventory,
                    ground_truth_path=self.external_dataset_ground_truth,
                )
                if mode == "detail":
                    self.send_json(
                        load_data31_coverage_document(
                            self.external_dataset_root,
                            case_id,
                            inventory_path=self.external_dataset_inventory,
                            ground_truth_path=self.external_dataset_ground_truth,
                            decision_path=self.external_dataset_coverage_decision,
                        )
                    )
                elif mode == "source":
                    self.send_file(
                        source,
                        mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                        f"{case_id}{source.suffix.lower()}",
                    )
                elif mode == "preview":
                    if source.suffix.casefold() in {".txt", ".docx", ".pptx"}:
                        self.send_json(
                            {
                                "kind": "text",
                                "sourceFile": source.name,
                                "text": load_external_text_preview(source),
                            }
                        )
                    else:
                        self.send_file(
                            source,
                            mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                        )
                else:
                    self.send_json(
                        {"error": "Invalid DATA-31 coverage document mode"},
                        HTTPStatus.BAD_REQUEST,
                    )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (OSError, FileNotFoundError, KeyError, json.JSONDecodeError):
                self.send_json(
                    {"error": "DATA-31 coverage document is unavailable"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/external-dataset/review/document":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "External dataset Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            case_id = query.get("id", [""])[0]
            mode = query.get("mode", ["detail"])[0]
            try:
                source = resolve_external_review_source(
                    self.external_dataset_root,
                    case_id,
                    inventory_path=self.external_dataset_inventory,
                    ground_truth_path=self.external_dataset_ground_truth,
                )
                if mode == "detail":
                    self.send_json(
                        load_external_review_document(
                            self.external_dataset_root,
                            case_id,
                            inventory_path=self.external_dataset_inventory,
                            ground_truth_path=self.external_dataset_ground_truth,
                        )
                    )
                elif mode == "source":
                    self.send_file(
                        source,
                        mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                        f"{case_id}{source.suffix.lower()}",
                    )
                elif mode == "preview":
                    if source.suffix.casefold() in {".txt", ".docx", ".pptx"}:
                        self.send_json(
                            {
                                "kind": "text",
                                "sourceFile": source.name,
                                "text": load_external_text_preview(source),
                            }
                        )
                    else:
                        self.send_file(
                            source,
                            mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                        )
                else:
                    self.send_json(
                        {"error": "Invalid review document mode"}, HTTPStatus.BAD_REQUEST
                    )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (OSError, FileNotFoundError, KeyError, json.JSONDecodeError):
                self.send_json(
                    {"error": "External dataset review document is unavailable"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/cccd-heldout/review/document":
            if self.cccd_heldout_root is None:
                self.send_json(
                    {"error": "CCCD Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            document_id = query.get("id", [""])[0]
            mode = query.get("mode", ["detail"])[0]
            try:
                if mode == "preview":
                    source = resolve_review_source(self.cccd_heldout_root, document_id)
                    self.send_file(
                        source,
                        mimetypes.guess_type(source.name)[0] or "image/jpeg",
                    )
                elif mode == "detail":
                    self.send_json(load_review_document(self.cccd_heldout_root, document_id))
                else:
                    self.send_json(
                        {"error": "Invalid review document mode"},
                        HTTPStatus.BAD_REQUEST,
                    )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (OSError, FileNotFoundError, KeyError, json.JSONDecodeError):
                self.send_json(
                    {"error": "CCCD review document is unavailable"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/cccd-heldout/review/evaluation":
            if self.cccd_heldout_root is None:
                self.send_json(
                    {"error": "CCCD Ground Truth review is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            document_id = query.get("id", [""])[0]
            try:
                self.send_json(
                    load_evaluation_document(self.cccd_heldout_root, document_id)
                )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (OSError, FileNotFoundError, KeyError, json.JSONDecodeError):
                self.send_json(
                    {"error": "CCCD evaluation output is unavailable"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/phase14/benchmark":
            phase14_root = self.data_root / "output" / "phase14"
            benchmark_path = phase14_root / "line_benchmark_private.json"
            if not benchmark_path.is_file():
                self.send_json(
                    {"error": "Phase 14 benchmark not available"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
            reviews_path = phase14_root / "line_reviews.json"
            reviews = (
                json.loads(reviews_path.read_text(encoding="utf-8")).get("reviews", {})
                if reviews_path.is_file()
                else {}
            )
            benchmark["lineReviews"] = reviews
            benchmark["reviewedLineCount"] = len(reviews)
            reviewed_path = phase14_root / "PHASE14_REVIEWED_EVALUATION.json"
            if reviewed_path.is_file():
                reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
                reviewed_selection = reviewed.get("selection", {})
                selection = dict(benchmark.get("selection", {}))
                for key in (
                    "bestEasyProfile",
                    "bestEasyCropProfile",
                    "vietocrCropProfile",
                    "recommendedPrimary",
                    "promotionDecision",
                    "productionDecision",
                    "verifierPolicy",
                    "qualityGate",
                ):
                    if key in reviewed_selection:
                        selection[key] = reviewed_selection[key]
                recommended_agreement = reviewed_selection.get("recommendedPrimaryAgreement", {})
                selection["recommendedPrimaryAgreementCount"] = recommended_agreement.get(
                    "count", 0
                )
                selection["recommendedPrimaryAgreementCoverage"] = recommended_agreement.get(
                    "coverage", 0.0
                )
                selection["recommendedPrimaryAgreementPrecision"] = recommended_agreement.get(
                    "precision", 0.0
                )
                benchmark["alignmentStatus"] = reviewed.get(
                    "groundTruthStatus", benchmark.get("alignmentStatus")
                )
                benchmark["reviewedLineCount"] = reviewed.get("reviewedLineCount", len(reviews))
                benchmark["profiles"] = reviewed.get("profiles", benchmark.get("profiles", {}))
                benchmark["selection"] = selection
                benchmark["recommendedConfiguration"] = reviewed.get("recommendedConfiguration", {})
            pilot_summary_path = (
                self.data_root / "output" / "phase14_2" / "CONTROLLED_PILOT_SUMMARY.json"
            )
            if pilot_summary_path.is_file():
                benchmark["controlledPilot"] = json.loads(
                    pilot_summary_path.read_text(encoding="utf-8")
                )
            phase14_3_path = self.data_root / "output" / "phase14_3" / "PHASE14_3_EVALUATION.json"
            if phase14_3_path.is_file():
                phase14_3 = json.loads(phase14_3_path.read_text(encoding="utf-8"))
                benchmark["phase14_3"] = phase14_3
                benchmark["profiles"].update(phase14_3.get("profiles", {}))
                selected = phase14_3.get("selected", {})
                benchmark["selection"].update(
                    {
                        "recommendedPrimary": selected.get("selectedPrimaryProfile"),
                        "bestCropProfile": selected.get(
                            "selectedCropProfile",
                            benchmark["selection"].get("bestCropProfile"),
                        ),
                        "fallbackRecognizer": selected.get("fallbackRecognizer"),
                        "autoAcceptVerifier": selected.get("autoAcceptVerifier"),
                        "productionDecision": selected.get("productionDecision"),
                        "verifierPolicy": "EASY_EXACT_AGREEMENT_ONLY",
                    }
                )
            expansion_root = self.data_root / "output" / "phase14_4"
            expansion_path = expansion_root / "review_queue_private.json"
            expansion_reviews_path = expansion_root / "line_reviews.json"
            if expansion_path.is_file():
                expansion = json.loads(expansion_path.read_text(encoding="utf-8"))
                expansion_reviews = (
                    json.loads(expansion_reviews_path.read_text(encoding="utf-8")).get(
                        "reviews", {}
                    )
                    if expansion_reviews_path.is_file()
                    else {}
                )
                benchmark["evaluationDocumentCount"] = benchmark.get("documentCount", 0)
                benchmark["evaluationLineCount"] = benchmark.get("lineCount", 0)
                benchmark["documentCount"] = expansion.get("documentCount", 0)
                benchmark["lineCount"] = expansion.get("lineCount", 0)
                benchmark["cases"] = expansion.get("cases", [])
                benchmark["lineReviews"] = expansion_reviews
                benchmark["reviewedLineCount"] = len(expansion_reviews)
                benchmark["groundTruthExpansion"] = {
                    "status": expansion.get("groundTruthStatus"),
                    "documentCount": expansion.get("documentCount", 0),
                    "lineCount": expansion.get("lineCount", 0),
                    "reviewedLineCount": len(expansion_reviews),
                    "pendingReviewLineCount": max(
                        0,
                        int(expansion.get("lineCount", 0)) - len(expansion_reviews),
                    ),
                    "cropProfile": expansion.get("cropProfile"),
                    "queueDigest": expansion.get("queueDigest"),
                }
                transformer_weight = (
                    self.data_root / "runtime" / "vietocr_models" / "vgg_transformer.pth"
                )
                benchmark["secondRecognizer"] = {
                    "config": "vgg_transformer",
                    "weightAvailable": transformer_weight.is_file(),
                    "weightBytes": (
                        transformer_weight.stat().st_size if transformer_weight.is_file() else 0
                    ),
                    "benchmarkReady": (
                        transformer_weight.is_file()
                        and len(expansion_reviews) == int(expansion.get("lineCount", 0))
                    ),
                    "blockedByPendingReviewCount": max(
                        0,
                        int(expansion.get("lineCount", 0)) - len(expansion_reviews),
                    ),
                }
                blinded_status_path = expansion_root / "BLINDED_PRECOMPUTE_STATUS.json"
                if blinded_status_path.is_file():
                    blinded_status = json.loads(blinded_status_path.read_text(encoding="utf-8"))
                    benchmark["blindedPrecompute"] = {
                        "status": blinded_status.get("status"),
                        "lineCount": blinded_status.get("lineCount", 0),
                        "predictionsHiddenDuringReview": blinded_status.get(
                            "predictionsHiddenDuringReview", False
                        ),
                        "queueDigestMatches": (
                            blinded_status.get("queueDigest") == expansion.get("queueDigest")
                        ),
                        "privateArtifactSha256": blinded_status.get("privateArtifactSha256"),
                        "runtime": blinded_status.get("runtime", {}),
                        "totalDurationMs": blinded_status.get("totalDurationMs", 0.0),
                    }
                second_benchmark_path = (
                    expansion_root / "benchmark" / "SECOND_RECOGNIZER_EVALUATION.json"
                )
                if second_benchmark_path.is_file():
                    second_benchmark = json.loads(second_benchmark_path.read_text(encoding="utf-8"))
                    benchmark["secondRecognizerBenchmark"] = second_benchmark
                    benchmark["selection"].update(
                        {
                            "recommendedPrimary": second_benchmark.get("decision", {}).get(
                                "selectedPrimary"
                            ),
                            "promotionDecision": second_benchmark.get("decision", {}).get(
                                "challengerDecision"
                            ),
                            "productionDecision": second_benchmark.get("decision", {}).get(
                                "productionDecision"
                            ),
                        }
                    )
            self.send_json(benchmark)
            return

        if parsed.path == "/phase14/crop":
            case_id = query.get("caseId", [""])[0]
            profile = query.get("profile", [""])[0]
            if not (
                PHASE14_CASE_ID_RE.fullmatch(case_id) and PHASE14_PROFILE_RE.fullmatch(profile)
            ):
                self.send_json(
                    {"error": "Invalid Phase 14 crop request"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            phase14_root = self.data_root / "output" / "phase14"
            benchmark_path = phase14_root / "line_benchmark_private.json"
            if not benchmark_path.is_file():
                self.send_json(
                    {"error": "Phase 14 benchmark not available"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            case = None
            crop_root = phase14_root
            sources = [
                (
                    self.data_root / "output" / "phase14_4",
                    self.data_root / "output" / "phase14_4" / "review_queue_private.json",
                ),
                (phase14_root, benchmark_path),
            ]
            for candidate_root, candidate_manifest in sources:
                if not candidate_manifest.is_file():
                    continue
                candidate_payload = json.loads(candidate_manifest.read_text(encoding="utf-8"))
                case = next(
                    (
                        item
                        for item in candidate_payload.get("cases", [])
                        if item.get("caseId") == case_id
                    ),
                    None,
                )
                if case is not None:
                    crop_root = candidate_root
                    break
            crop_info = case.get("crops", {}).get(profile) if case else None
            if not crop_info:
                self.send_json(
                    {"error": "Phase 14 crop not found"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            relative_path = Path(str(crop_info.get("path", "")))
            if relative_path.is_absolute() or ".." in relative_path.parts:
                self.send_json(
                    {"error": "Unsafe crop path"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            crop_path = (crop_root / relative_path).resolve()
            if crop_root.resolve() not in crop_path.parents or not crop_path.is_file():
                self.send_json(
                    {"error": "Phase 14 crop not found"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            self.send_file(crop_path, "image/png")
            return

        if parsed.path == "/api/templates":
            self.send_json({"templates": list(self.template_processor.list_templates())})
            return

        if parsed.path == "/api/ocr/warmup":
            try:
                self.template_processor.warm_up_ocr()
                # Legacy user OCR path also used for some image uploads.
                if PaddleOCR is not None:
                    try:
                        self.user_ocr.get_ocr()
                    except RuntimeError:
                        pass
                self.send_json(
                    {
                        "status": "ready",
                        "templateOcrBackend": self.template_processor.ocr_backend,
                        "templateOcrProfile": self.template_processor.ocr_profile,
                        "backendAvailable": self.template_processor.ocr_backend_available,
                        "templateOcrModelLoaded": self.template_processor.ocr_model_loaded,
                        "paddleOcrAvailable": PaddleOCR is not None,
                        "userOcrModelLoaded": self.user_ocr.model_loaded,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - surface OCR boot failures
                self.send_json(
                    {
                        "status": "error",
                        "error": str(exc),
                        "backendAvailable": self.template_processor.ocr_backend_available,
                        "templateOcrBackend": self.template_processor.ocr_backend,
                    },
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return

        if parsed.path == "/health":
            template_pipelines = [
                {
                    "documentType": row["documentType"],
                    "templateId": row["templateId"],
                    "templateVersion": row["version"],
                    "parserId": row["parserId"],
                    "parserVersion": row["parserVersion"],
                    "supportedFileTypes": row["supportedFileTypes"],
                    "lifecycle": row["lifecycle"],
                }
                for row in self.template_processor.list_templates()
            ]
            self.send_json(
                {
                    "status": "ok",
                    "profiles": {name: len(index) for name, index in self.native_indexes.items()},
                    "userUpload": {
                        "enabled": True,
                        "templateFirstEnabled": True,
                        "phase9Enabled": True,
                        "phase10ReviewEnabled": True,
                        "phase11CccdEnabled": True,
                        "phase11_4EvidenceEnabled": True,
                        "phase12IdpEnabled": True,
                        "phase15UnifiedIdpEnabled": True,
                        "phase13_3HybridEnabled": True,
                        "phase14_8VerifierEnabled": True,
                        "phase14LineReviewEnabled": True,
                        "paddleOcrAvailable": PaddleOCR is not None,
                        "runtimeProfile": LOCAL_TEMPLATE_RUNTIME_PROFILE,
                        "templateOcrBackend": self.template_processor.ocr_backend,
                        "templateOcrProfile": self.template_processor.ocr_profile,
                        "backendAvailable": (
                            self.template_processor.ocr_backend_available
                        ),
                        "pipelines": template_pipelines,
                        "modelLoaded": self.user_ocr.model_loaded,
                        "templateOcrModelLoaded": (
                            self.template_processor.ocr_model_loaded
                        ),
                        "sessionCount": len(self.user_ocr.list_sessions()),
                        "formats": sorted(ALLOWED_EXTENSIONS),
                        "templateFormats": sorted(TEMPLATE_ALLOWED_EXTENSIONS),
                        "maxUploadBytes": MAX_UPLOAD_BYTES,
                    },
                }
            )
            return

        if parsed.path == "/user/sessions":
            self.send_json({"sessions": self.user_ocr.list_sessions()})
            return

        if parsed.path.startswith("/user/"):
            session_id = query.get("id", [""])[0]
            session_dir = self.user_ocr.session_dir(session_id)
            if session_dir is None:
                self.send_json({"error": "Session not found"}, HTTPStatus.NOT_FOUND)
                return
            result_path = session_dir / "result.json"
            if not result_path.is_file():
                self.send_json({"error": "Result not available"}, HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/user/session":
                self.send_json(json.loads(result_path.read_text(encoding="utf-8")))
                return
            if parsed.path == "/user/review":
                result = json.loads(result_path.read_text(encoding="utf-8"))
                self.send_json(review_payload(session_dir, result))
                return
            if parsed.path == "/user/download":
                self.send_file(
                    result_path,
                    "application/json; charset=utf-8",
                    f"ocr-result-{session_id}.json",
                )
                return
            if parsed.path == "/user/source":
                source_paths = sorted((session_dir / "input").glob("document.*"))
                if not source_paths:
                    self.send_json(
                        {"error": "Original session source not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                source_path = source_paths[0]
                content_type = (
                    mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
                )
                self.send_file(source_path, content_type)
                return
            if parsed.path == "/user/phase11-5-crop":
                field_name = query.get("field", [""])[0]
                variant_name = query.get("variant", [""])[0]
                allowed_fields = {
                    "identityNumber",
                    "fullName",
                    "dateOfBirth",
                    "sex",
                    "nationality",
                    "placeOfOrigin",
                    "placeOfResidence",
                    "dateOfExpiry",
                }
                allowed_variants = {
                    "color_original",
                    "grayscale_clahe",
                    "lanczos_upscale",
                    "balanced_padding",
                }
                if field_name not in allowed_fields or variant_name not in allowed_variants:
                    self.send_json(
                        {"error": "Invalid Phase 11.5 crop selector"},
                        HTTPStatus.BAD_REQUEST,
                    )
                    return
                try:
                    crop_path = resolve_phase11_5_crop(
                        self.data_root,
                        session_dir,
                        field_name,
                        variant_name,
                    )
                    crop_body = crop_path.read_bytes() if crop_path is not None else None
                except (OSError, ValueError) as exc:
                    self.send_json(
                        {
                            "error": "Phase 11.5 crop could not be read",
                            "errorType": type(exc).__name__,
                        },
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                if crop_path is None:
                    self.send_json(
                        {"error": "Phase 11.5 crop not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                if crop_body is None:
                    self.send_json(
                        {"error": "Phase 11.5 crop not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_bytes(crop_body, "image/png")
                return
            phase10_downloads = {
                "/user/ground-truth": (
                    session_dir / "phase10" / "ground_truth.json",
                    f"ground-truth-{session_id}.json",
                ),
                "/user/evaluation": (
                    session_dir / "phase10" / "evaluation.json",
                    f"evaluation-{session_id}.json",
                ),
                "/user/business": (
                    session_dir / "phase10" / "business.json",
                    f"business-{session_id}.json",
                ),
            }
            phase11_download = (
                session_dir / "phase11" / "identity_card.json",
                f"identity-card-{session_id}.json",
            )
            phase14_8_download = (
                session_dir / "phase14_8" / "recognition.json",
                f"phase14-8-recognition-{session_id}.json",
            )
            phase12_downloads = {
                "/user/phase12-canonical": (
                    session_dir / "phase12" / "canonical_document.json",
                    f"canonical-document-{session_id}.json",
                ),
                "/user/phase12-result": (
                    session_dir / "phase12" / "idp_result.json",
                    f"idp-result-{session_id}.json",
                ),
                "/user/phase12-business": (
                    session_dir / "phase12" / "business.json",
                    f"camunda-business-{session_id}.json",
                ),
            }
            phase15_downloads = {
                "/user/phase15-canonical": (
                    session_dir / "phase15" / "canonical_document.json",
                    f"canonical-document-{session_id}.json",
                ),
                "/user/phase15-result": (
                    session_dir / "phase15" / "idp_result.json",
                    f"idp-result-{session_id}.json",
                ),
                "/user/phase15-business": (
                    session_dir / "phase15" / "business.json",
                    f"camunda-business-{session_id}.json",
                ),
                "/user/phase15-reviewed-result": (
                    session_dir / "phase15" / "idp_result_reviewed.json",
                    f"idp-result-reviewed-{session_id}.json",
                ),
                "/user/phase15-reviewed-business": (
                    session_dir / "phase15" / "business_reviewed.json",
                    f"camunda-business-reviewed-{session_id}.json",
                ),
            }
            if parsed.path == "/user/phase13-3-result":
                download_path = session_dir / "phase13_3" / "hybrid_ocr.json"
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Phase 13.3 hybrid result not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    f"hybrid-ocr-{session_id}.json",
                )
                return
            if parsed.path == "/user/phase14-2-result":
                download_path = session_dir / "phase14_2" / "controlled_pilot.json"
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Phase 14.2 pilot result not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    f"controlled-pilot-{session_id}.json",
                )
                return
            if parsed.path == "/user/identity-card":
                download_path, download_name = phase11_download
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Structured CCCD JSON not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    download_name,
                )
                return
            if parsed.path == "/user/phase14-8-recognition":
                download_path, download_name = phase14_8_download
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Phase 14.8 recognition JSON not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    download_name,
                )
                return
            if parsed.path == "/user/phase11-3-evidence":
                download_path = session_dir / "phase11_3" / "paddle_recognition.json"
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Phase 11.3 evidence JSON not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    f"phase11-3-evidence-{session_id}.json",
                )
                return
            if parsed.path == "/user/phase11-4-evidence":
                download_path = session_dir / "phase11_4" / "field_consensus.json"
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Phase 11.4 evidence JSON not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    f"phase11-4-evidence-{session_id}.json",
                )
                return
            if parsed.path == "/user/phase11-5-evidence":
                download_path = session_dir / "phase11_5" / "field_consensus.json"
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Phase 11.5 evidence JSON not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    f"phase11-5-evidence-{session_id}.json",
                )
                return
            if parsed.path == "/user/phase11-5-business":
                download_path = session_dir / "phase11_5" / "business.json"
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Phase 11.5 business JSON not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    f"phase11-5-business-{session_id}.json",
                )
                return
            if parsed.path in phase12_downloads:
                download_path, download_name = phase12_downloads[parsed.path]
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Phase 12 IDP JSON not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    download_name,
                )
                return
            if parsed.path in phase15_downloads:
                download_path, download_name = phase15_downloads[parsed.path]
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Phase 15 unified IDP JSON not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    download_name,
                )
                return
            if parsed.path in phase10_downloads:
                download_path, download_name = phase10_downloads[parsed.path]
                if not download_path.is_file():
                    self.send_json(
                        {"error": "Phase 10 review not available"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                self.send_file(
                    download_path,
                    "application/json; charset=utf-8",
                    download_name,
                )
                return
            if parsed.path == "/user/visualization":
                try:
                    page_index = int(query.get("page", ["0"])[0])
                except ValueError:
                    page_index = -1
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if result.get("phase11", {}).get("status") in {
                    "PASS",
                    "NEEDS_REVIEW",
                }:
                    visualization = (
                        session_dir / "phase11" / "visualization" / f"page_{page_index:03d}.png"
                    )
                elif result.get("phase9", {}).get("selectedVariant") == "phase9_routed":
                    visualization = (
                        session_dir / "phase9" / "visualization" / f"page_{page_index:03d}.png"
                    )
                else:
                    visualization = session_dir / "visualization" / f"page_{page_index:03d}.png"
                if not visualization.is_file():
                    self.send_json({"error": "Visualization not available"}, HTTPStatus.NOT_FOUND)
                    return
                self.send_file(visualization, "image/png")
                return
            self.send_json({"error": "Unknown endpoint"}, HTTPStatus.NOT_FOUND)
            return

        sample_id = query.get("id", [""])[0]
        profile = query.get("profile", ["phase7"])[0]
        native_path = self.native_indexes.get(profile, {}).get(sample_id)
        if native_path is None:
            self.send_json({"error": "Sample not found"}, HTTPStatus.NOT_FOUND)
            return

        if parsed.path == "/detail":
            native = json.loads(native_path.read_text(encoding="utf-8"))
            texts = [
                str(text)
                for page in native.get("pages", [])
                for text in page.get("recognizedTexts", [])
            ]
            scores = [
                float(score)
                for page in native.get("pages", [])
                for score in page.get("recognitionScores", [])
            ]
            self.send_json(
                {
                    "sampleId": native.get("sampleId"),
                    "documentId": native.get("documentId"),
                    "sourceRelativePath": native.get("sourceRelativePath"),
                    "variant": native.get("variant"),
                    "processing": native.get("processing"),
                    "recognizedTexts": texts,
                    "recognitionScores": scores,
                    "hasVisualization": bool(texts),
                }
            )
            return

        if parsed.path == "/visualization":
            native = json.loads(native_path.read_text(encoding="utf-8"))
            relative = Path(native["sourceRelativePath"])
            visualization = (
                self.data_root / "output" / "visualization"
                if profile == "baseline"
                else self.data_root / "output" / "phase7" / "v5_enhanced" / "visualization"
            ) / relative.with_name(f"{relative.stem}_vis.png")
            if not visualization.is_file():
                self.send_json({"error": "Visualization not available"}, HTTPStatus.NOT_FOUND)
                return
            self.send_file(
                visualization,
                mimetypes.guess_type(visualization)[0] or "image/png",
            )
            return

        self.send_json({"error": "Unknown endpoint"}, HTTPStatus.NOT_FOUND)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the HR OCR dashboard API")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "--cccd-heldout-root",
        type=Path,
        help="Authorized local CCCD Phase 11.6 Ground Truth review root.",
    )
    parser.add_argument(
        "--benchmark-report",
        type=Path,
        help="Latest aggregate prediction report used by the per-document-type benchmark.",
    )
    parser.add_argument(
        "--benchmark-manifest",
        type=Path,
        help="Inventory for the latest aggregate prediction report.",
    )
    parser.add_argument(
        "--ocr-ho-shadow-root",
        type=Path,
        help=(
            "Private local development archive for the OCR-HO-V2-014 shadow UAT. "
            "Defaults to --data-root."
        ),
    )
    parser.add_argument(
        "--external-dataset-root",
        type=Path,
        help="Private local staging root for an authorized dataset review UI.",
    )
    parser.add_argument(
        "--external-dataset-inventory",
        type=Path,
        help="Public inventory JSON for the external dataset (optional sibling inference).",
    )
    parser.add_argument(
        "--external-dataset-ground-truth",
        type=Path,
        help="Private local Ground Truth draft JSON for the external dataset.",
    )
    parser.add_argument(
        "--external-dataset-coverage-decision",
        type=Path,
        help="Private DATA-31 missing-field coverage decision JSON.",
    )
    parser.add_argument(
        "--external-dataset-typed-projection",
        type=Path,
        help="Private DATA-09 typed canonical projection JSON.",
    )
    parser.add_argument(
        "--external-dataset-typed-approval",
        type=Path,
        help="Private DATA-10 typed projection approval marker JSON.",
    )
    parser.add_argument(
        "--external-dataset-typed-report",
        type=Path,
        help="Private DATA-09 aggregate-only report JSON.",
    )
    parser.add_argument(
        "--external-dataset-predictions",
        type=Path,
        help="Private DATA-12 prediction artifact JSON.",
    )
    parser.add_argument(
        "--external-dataset-prediction-report",
        type=Path,
        help="Private DATA-12 aggregate report JSON.",
    )
    parser.add_argument(
        "--external-dataset-prediction-marker",
        type=Path,
        help="Private DATA-12 evaluate-once marker JSON.",
    )
    parser.add_argument(
        "--external-dataset-predictions-data13",
        type=Path,
        help="Private DATA-13 prediction artifact JSON.",
    )
    parser.add_argument(
        "--external-dataset-prediction-report-data13",
        type=Path,
        help="Private DATA-13 aggregate report JSON.",
    )
    parser.add_argument(
        "--external-dataset-prediction-marker-data13",
        type=Path,
        help="Private DATA-13 evaluate-once marker JSON.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        args.host = require_loopback_host(args.host)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    indexes = {
        "baseline": build_index(args.data_root / "output" / "native_json"),
        "phase7": build_index(args.data_root / "output" / "phase7" / "v5_enhanced" / "native_json"),
    }
    DashboardHandler.data_root = args.data_root
    DashboardHandler.benchmark_report = (
        args.benchmark_report.expanduser().resolve()
        if args.benchmark_report is not None
        else None
    )
    DashboardHandler.benchmark_manifest = (
        args.benchmark_manifest.expanduser().resolve()
        if args.benchmark_manifest is not None
        else None
    )
    DashboardHandler.cccd_heldout_root = (
        args.cccd_heldout_root.expanduser().resolve()
        if args.cccd_heldout_root is not None
        else None
    )
    shadow_root = args.ocr_ho_shadow_root or args.data_root
    DashboardHandler.ocr_ho_shadow_root = shadow_root.expanduser().resolve()
    DashboardHandler.external_dataset_root = (
        args.external_dataset_root.expanduser().resolve()
        if args.external_dataset_root is not None
        else None
    )
    DashboardHandler.external_dataset_inventory = (
        args.external_dataset_inventory.expanduser().resolve()
        if args.external_dataset_inventory is not None
        else None
    )
    DashboardHandler.external_dataset_ground_truth = (
        args.external_dataset_ground_truth.expanduser().resolve()
        if args.external_dataset_ground_truth is not None
        else None
    )
    DashboardHandler.external_dataset_coverage_decision = (
        args.external_dataset_coverage_decision.expanduser().resolve()
        if args.external_dataset_coverage_decision is not None
        else None
    )
    DashboardHandler.external_dataset_typed_projection = (
        args.external_dataset_typed_projection.expanduser().resolve()
        if args.external_dataset_typed_projection is not None
        else None
    )
    DashboardHandler.external_dataset_typed_approval = (
        args.external_dataset_typed_approval.expanduser().resolve()
        if args.external_dataset_typed_approval is not None
        else None
    )
    DashboardHandler.external_dataset_typed_report = (
        args.external_dataset_typed_report.expanduser().resolve()
        if args.external_dataset_typed_report is not None
        else None
    )
    DashboardHandler.external_dataset_predictions = (
        args.external_dataset_predictions.expanduser().resolve()
        if args.external_dataset_predictions is not None
        else None
    )
    DashboardHandler.external_dataset_prediction_report = (
        args.external_dataset_prediction_report.expanduser().resolve()
        if args.external_dataset_prediction_report is not None
        else None
    )
    DashboardHandler.external_dataset_prediction_marker = (
        args.external_dataset_prediction_marker.expanduser().resolve()
        if args.external_dataset_prediction_marker is not None
        else None
    )
    DashboardHandler.external_dataset_predictions_data13 = (
        args.external_dataset_predictions_data13.expanduser().resolve()
        if args.external_dataset_predictions_data13 is not None
        else None
    )
    DashboardHandler.external_dataset_prediction_report_data13 = (
        args.external_dataset_prediction_report_data13.expanduser().resolve()
        if args.external_dataset_prediction_report_data13 is not None
        else None
    )
    DashboardHandler.external_dataset_prediction_marker_data13 = (
        args.external_dataset_prediction_marker_data13.expanduser().resolve()
        if args.external_dataset_prediction_marker_data13 is not None
        else None
    )
    DashboardHandler.native_indexes = indexes
    DashboardHandler.user_ocr = UserOCRService(args.data_root)
    DashboardHandler.template_processor = build_local_template_processing_service()
    DashboardHandler.mvp_demo = MvpDemoStore(args.data_root)
    resolved_ocr = resolve_template_ocr_backend()
    print(
        f"Template OCR backend resolved: {resolved_ocr} "
        f"(available={DashboardHandler.template_processor.ocr_backend_available})",
        flush=True,
    )
    if os.getenv("HCNS_TEMPLATE_OCR_WARMUP", "1").strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
    }:

        def _warm_ocr() -> None:
            try:
                DashboardHandler.template_processor.warm_up_ocr()
                print(
                    "Template OCR warm-up complete: "
                    f"backend={DashboardHandler.template_processor.ocr_backend} "
                    f"loaded={DashboardHandler.template_processor.ocr_model_loaded}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"Template OCR warm-up failed: {exc}", flush=True)

        threading.Thread(target=_warm_ocr, name="ocr-warmup", daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(
        f"Local dashboard API ready: http://{args.host}:{args.port} "
        f"(baseline={len(indexes['baseline'])}, phase7={len(indexes['phase7'])}, "
        f"ocr-ho-shadow={'on' if DashboardHandler.ocr_ho_shadow_root else 'off'}, "
        f"external-review={'on' if DashboardHandler.external_dataset_root else 'off'})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
