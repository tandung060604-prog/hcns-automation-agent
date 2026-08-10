#!/usr/bin/env python3
"""Serve baseline results and local-only OCR sessions for the dashboard."""

from __future__ import annotations

import argparse
import json
import mimetypes
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
from urllib.parse import parse_qs, urlparse

import cv2

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import pypdfium2 as pdfium
except ImportError:  # Evidence-only mode can run without PDF rendering.
    pdfium = None
from cccd_heldout_review import (
    evaluate_once as evaluate_cccd_ground_truth_once,
    load_evaluation_document,
    load_review_document,
    load_review_summary,
    lock_ground_truth,
    resolve_review_source,
    save_review as save_cccd_ground_truth_review,
    set_review_disposition,
)
from external_dataset_review import (
    load_review_document as load_external_review_document,
    load_review_summary as load_external_review_summary,
    load_text_preview as load_external_text_preview,
    lock_ground_truth as lock_external_ground_truth,
    resolve_review_source as resolve_external_review_source,
    save_review as save_external_review,
)
from external_dataset_typed import (
    TypedDatasetError,
    build_typed_export,
    load_typed_document,
    load_typed_summary,
    resolve_typed_paths,
)
from external_dataset_prediction import (
    PredictionArtifactError,
    load_prediction_document,
    load_prediction_summary,
    resolve_prediction_paths,
    resolve_prediction_source,
)
from document_route_safety import (
    safe_existing_document_route,
    selected_orientations_are_identity,
)
from local_server_security import require_loopback_host

try:
    from paddleocr import PaddleOCR
except ImportError:  # Evidence-only mode can run while OCR env is repaired.
    PaddleOCR = None
from phase9_pipeline import (
    classify_document,
    enrich_result,
    prepare_routed_page,
    reading_order,
)
from phase10_review import review_payload, save_review
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
from phase11_8_shadow_uat import (
    load_shadow_document,
    load_shadow_summary,
    resolve_shadow_source,
    save_shadow_review,
)
from ocr_ho_v2_diagnostic import (
    document as load_ocr_ho_diagnostic_document,
    preview as resolve_ocr_ho_diagnostic_preview,
    save as save_ocr_ho_diagnostic,
    summary as load_ocr_ho_diagnostic_summary,
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

from hcns_agent.domain.errors import DocumentIntakeError
from hcns_agent.domain.documents import SourceFormat
from hcns_agent.application.ocr_scope import (
    ocr_allowed_for_document_type,
    ocr_scope_for,
)
from hcns_agent.adapters.camunda7.local_shadow_review import load_shadow_review_report
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.templates.service import (
    TemplateProcessingService,
    TemplateTechnicalError,
    TemplateUnsupportedError,
    build_local_template_processing_service,
)


def _read_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _template_benchmark_row(
    key: str,
    label: str,
    runtime_types: set[str],
    runtime_counts: Counter[str],
) -> dict[str, Any]:
    if key in {"leave", "overtime"}:
        field_count = 49 if key == "leave" else 77
        note = (
            "7 mẫu native, 49/49 required field khớp đúng. "
            "OCR ảnh và PDF scan được đánh giá riêng theo benchmark gộp."
            if key == "leave"
            else "7 mẫu native, 77/77 required field khớp đúng. "
            "7 field department không có trong nguồn được giữ null."
        )
        return {
            "key": key,
            "label": label,
            "benchmarkDocumentCount": 7,
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

    return {
        "schemaVersion": "local-document-benchmark/1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
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
TEMPLATE_ALLOWED_EXTENSIONS = {
    ".docx",
    ".pdf",
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
                    "originalFileName": data.get("sourceFile") or "template-document.docx",
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
    external_dataset_data23_manifest: Path | None
    external_dataset_data23_prediction_lock: Path | None
    external_dataset_data23_ground_truth_lock: Path | None
    external_dataset_typed_projection: Path | None
    external_dataset_typed_approval: Path | None
    external_dataset_typed_report: Path | None
    external_dataset_predictions: Path | None
    external_dataset_prediction_report: Path | None
    external_dataset_prediction_marker: Path | None
    external_dataset_predictions_data13: Path | None
    external_dataset_prediction_report_data13: Path | None
    external_dataset_prediction_marker_data13: Path | None
    external_dataset_policy_v2_report: Path | None
    external_dataset_policy_v2_marker: Path | None
    m5_local_shadow_report: Path | None = None
    native_indexes: dict[str, dict[str, Path]]
    user_ocr: UserOCRService
    template_processor: TemplateProcessingService

    def log_message(self, format: str, *args: object) -> None:
        # Never log session IDs, filenames, paths, or raw OCR text.
        return

    def cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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
    ) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.cors_headers()
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
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
                payload = result.public_dict()
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
                        data23_manifest_path=self.external_dataset_data23_manifest,
                        data23_prediction_lock_path=self.external_dataset_data23_prediction_lock,
                        data23_ground_truth_lock_path=self.external_dataset_data23_ground_truth_lock,
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
                        "message": "Ảnh/PDF scan chỉ nhận OCR cho CCCD hoặc chứng chỉ.",
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
            error_code = (
                "OCR_DISABLED_BY_POLICY"
                if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
                else "SUPPORTED_TEMPLATE_FORMAT_REQUIRED"
            )
            self.send_json(
                {
                    "status": "REJECT_UNSUPPORTED",
                    "recommendedAction": "REJECT_UNSUPPORTED",
                    "errorCode": error_code,
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

    def _do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/":
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", "http://localhost:3000")
            self.cors_headers()
            self.end_headers()
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

        if parsed.path == "/m5/local-shadow-review/summary":
            if self.m5_local_shadow_report is None:
                self.send_json(
                    {"error": "M5-CAM-001D local shadow report is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            try:
                self.send_json(load_shadow_review_report(str(self.m5_local_shadow_report)))
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(
                    {"error": f"M5 local shadow report unavailable: {exc}"},
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
            result = self.user_ocr.template_result(document_id)
            if result is None:
                self.send_json(
                    {"error": "Template-first result not found"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            self.send_json(result)
            return

        if parsed.path == "/api/documents/source":
            document_id = query.get("id", [""])[0]
            source_path = self.user_ocr.template_source(document_id)
            if source_path is None:
                self.send_json(
                    {"error": "Template-first source not found"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            content_type = (
                mimetypes.guess_type(source_path.name)[0]
                or "application/octet-stream"
            )
            self.send_file(source_path, content_type)
            return

        if parsed.path == "/api/documents/preview":
            document_id = query.get("id", [""])[0]
            try:
                preview = self.user_ocr.template_preview(document_id)
            except (OSError, RuntimeError, ValueError):
                self.send_json(
                    {"error": "Template-first preview unavailable"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            if preview is None:
                self.send_json(
                    {"error": "Template-first preview not found"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            body, content_type = preview
            self.send_bytes(body, content_type)
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

        if parsed.path == "/external-dataset/prediction/source":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "DATA-12 prediction source is not configured"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            case_id = query.get("id", [""])[0]
            mode = query.get("mode", ["preview"])[0]
            try:
                source = resolve_prediction_source(
                    self.external_dataset_root,
                    self.external_dataset_inventory,
                    case_id,
                )
                if mode == "source":
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
                        {"error": "Invalid prediction source mode"},
                        HTTPStatus.BAD_REQUEST,
                    )
            except PermissionError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except (OSError, FileNotFoundError, KeyError, json.JSONDecodeError):
                self.send_json(
                    {"error": "Prediction-only source is unavailable"},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/external-dataset/policy-v2/summary":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "DATA-25 policy audit is not configured"}, HTTPStatus.NOT_FOUND
                )
                return
            try:
                self.send_json(
                    load_prediction_summary(
                        resolve_prediction_paths(
                            self.external_dataset_root,
                            prediction_path=self.external_dataset_predictions,
                            report_path=self.external_dataset_policy_v2_report,
                            evaluation_marker_path=self.external_dataset_policy_v2_marker,
                        )
                    )
                )
            except (OSError, PredictionArtifactError) as exc:
                self.send_json(
                    {"error": f"DATA-25 policy audit unavailable: {exc}"}, HTTPStatus.NOT_FOUND
                )
            return

        if parsed.path == "/external-dataset/policy-v2/document":
            if self.external_dataset_root is None:
                self.send_json(
                    {"error": "DATA-25 policy audit is not configured"}, HTTPStatus.NOT_FOUND
                )
                return
            try:
                self.send_json(
                    load_prediction_document(
                        resolve_prediction_paths(
                            self.external_dataset_root,
                            prediction_path=self.external_dataset_predictions,
                            report_path=self.external_dataset_policy_v2_report,
                            evaluation_marker_path=self.external_dataset_policy_v2_marker,
                        ),
                        query.get("id", [""])[0],
                        self.external_dataset_ground_truth,
                        policy_version="2.0.0",
                    )
                )
            except FileNotFoundError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            except (OSError, PredictionArtifactError) as exc:
                self.send_json(
                    {"error": f"DATA-25 policy audit unavailable: {exc}"}, HTTPStatus.NOT_FOUND
                )
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

        if parsed.path == "/health":
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
        help="Local staging root for the synthetic external dataset review UI.",
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
        "--external-dataset-data23-manifest",
        type=Path,
        help="Private DATA-23 held-out manifest used when sealing the review UI.",
    )
    parser.add_argument(
        "--external-dataset-data23-prediction-lock",
        type=Path,
        help="Private DATA-23 prediction lock used when sealing the review UI.",
    )
    parser.add_argument(
        "--external-dataset-data23-ground-truth-lock",
        type=Path,
        help="Private DATA-23 GroundTruth lock to create after blind review.",
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
    parser.add_argument(
        "--external-dataset-policy-v2-report",
        type=Path,
        help="Private DATA-25 post-hoc policy v2 report JSON.",
    )
    parser.add_argument(
        "--external-dataset-policy-v2-marker",
        type=Path,
        help="Private DATA-25 post-hoc policy v2 marker JSON.",
    )
    parser.add_argument(
        "--m5-local-shadow-report",
        type=Path,
        help="Private aggregate-only M5-CAM-001D local shadow report JSON.",
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
    DashboardHandler.external_dataset_data23_manifest = (
        args.external_dataset_data23_manifest.expanduser().resolve()
        if args.external_dataset_data23_manifest is not None
        else None
    )
    DashboardHandler.external_dataset_data23_prediction_lock = (
        args.external_dataset_data23_prediction_lock.expanduser().resolve()
        if args.external_dataset_data23_prediction_lock is not None
        else None
    )
    DashboardHandler.external_dataset_data23_ground_truth_lock = (
        args.external_dataset_data23_ground_truth_lock.expanduser().resolve()
        if args.external_dataset_data23_ground_truth_lock is not None
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
    DashboardHandler.external_dataset_policy_v2_report = (
        args.external_dataset_policy_v2_report.expanduser().resolve()
        if args.external_dataset_policy_v2_report is not None
        else None
    )
    DashboardHandler.external_dataset_policy_v2_marker = (
        args.external_dataset_policy_v2_marker.expanduser().resolve()
        if args.external_dataset_policy_v2_marker is not None
        else None
    )
    DashboardHandler.m5_local_shadow_report = (
        args.m5_local_shadow_report.expanduser().resolve()
        if args.m5_local_shadow_report is not None
        else None
    )
    DashboardHandler.native_indexes = indexes
    DashboardHandler.user_ocr = UserOCRService(args.data_root)
    DashboardHandler.template_processor = build_local_template_processing_service()
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
