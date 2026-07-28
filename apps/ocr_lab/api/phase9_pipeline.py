#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 9 document routing, conservative text restoration, and quality gates."""

from __future__ import annotations

import copy
import difflib
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np


LOW_CONFIDENCE = 0.80
CRITICAL_CONFIDENCE = 0.90

SAFE_PHRASE_CORRECTIONS = {
    "cong hoa xa hoi chu nghia viet nam": "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "doc lap tu do hanh phuc": "Độc lập - Tự do - Hạnh phúc",
    "can cuoc cong dan": "CĂN CƯỚC CÔNG DÂN",
    "ho va ten full name": "Họ và tên / Full name",
    "ngay sinh date of birth": "Ngày sinh / Date of birth",
    "gioi tinh sex": "Giới tính / Sex",
    "quoc tich nationality": "Quốc tịch / Nationality",
    "que quan place of origin": "Quê quán / Place of origin",
    "noi thuong tru place of residence": "Nơi thường trú / Place of residence",
    "co gia tri den": "Có giá trị đến",
    "lien lac": "Liên lạc",
    "dien thoai": "Điện thoại",
    "dia chi": "Địa chỉ",
    "muc tieu nghe nghiep": "Mục tiêu nghề nghiệp",
    "kinh nghiem lam viec": "Kinh nghiệm làm việc",
    "ky nang": "Kỹ năng",
    "ten cong ty": "Tên công ty",
    "quan ly du an": "Quản lý dự án",
    "giao tiep tot": "Giao tiếp tốt",
    "ky nang thuyet phuc": "Kỹ năng thuyết phục",
    "quan ly thoi gian": "Quản lý thời gian",
    "ky nang dam phan": "Kỹ năng đàm phán",
}


def accent_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    plain = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def classify_document(text: str, source_format: str) -> tuple[str, float, list[str]]:
    key = accent_key(text)
    evidence: list[str] = []
    identity_terms = (
        "can cuoc cong dan",
        "citizen identity card",
        "place of origin",
        "noi thuong tru",
        "nationality",
    )
    cv_terms = (
        "kinh nghiem lam viec",
        "kinh nghim lam vic",
        "muc tieu nghe nghiep",
        "muc tieu ngh nghip",
        "ky nang",
        "k nang",
        "curriculum vitae",
        "email",
    )
    identity_hits = [term for term in identity_terms if term in key]
    cv_hits = [term for term in cv_terms if term in key]
    if identity_hits:
        evidence.extend(identity_hits[:3])
        return "IDENTITY_DOCUMENT", min(0.98, 0.72 + 0.08 * len(identity_hits)), evidence
    if len(cv_hits) >= 2 or ("email" in key and "kinh nghiem" in key):
        evidence.extend(cv_hits[:3])
        return "CV", min(0.96, 0.68 + 0.07 * len(cv_hits)), evidence
    evidence.append(f"format:{source_format.lower()}")
    return "GENERIC_DOCUMENT", 0.55, evidence


def _order_points(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(diffs)]
    ordered[3] = points[np.argmax(diffs)]
    return ordered


def _warp_largest_card(image: np.ndarray) -> tuple[np.ndarray, bool]:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 45, 135)
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
    )
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[float, np.ndarray]] = []
    page_area = float(height * width)
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < page_area * 0.20 or area > page_area * 0.97:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(polygon) == 4:
            candidates.append((area, polygon.reshape(4, 2).astype(np.float32)))
    if not candidates:
        return image, False
    points = _order_points(max(candidates, key=lambda item: item[0])[1])
    tl, tr, br, bl = points
    output_width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    output_height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if output_width < 300 or output_height < 180:
        return image, False
    destination = np.array(
        [[0, 0], [output_width - 1, 0], [output_width - 1, output_height - 1], [0, output_height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(points, destination)
    return cv2.warpPerspective(image, matrix, (output_width, output_height)), True


def _enhance_luminance(image: np.ndarray, target_width: int) -> tuple[np.ndarray, float]:
    scale = max(1.0, target_width / image.shape[1])
    if scale > 1.0:
        image = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    luminance, a_channel, b_channel = cv2.split(lab)
    luminance = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(luminance)
    enhanced = cv2.cvtColor(
        cv2.merge((luminance, a_channel, b_channel)), cv2.COLOR_LAB2BGR
    )
    blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
    enhanced = cv2.addWeighted(enhanced, 1.35, blurred, -0.35, 0)
    return enhanced, round(scale, 3)


def prepare_routed_page(
    source_path: Path,
    document_type: str,
    output_path: Path,
) -> dict[str, Any] | None:
    if document_type not in {"IDENTITY_DOCUMENT", "CV"}:
        return None
    image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    original_size = [int(image.shape[1]), int(image.shape[0])]
    perspective_corrected = False
    if document_type == "IDENTITY_DOCUMENT":
        image, perspective_corrected = _warp_largest_card(image)
        target_width = 1600
    else:
        target_width = 1400
    image, scale = _enhance_luminance(image, target_width)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image):
        return None
    return {
        "route": document_type,
        "perspectiveCorrected": perspective_corrected,
        "originalSize": original_size,
        "routedSize": [int(image.shape[1]), int(image.shape[0])],
        "upscale": scale,
        "claheClipLimit": 1.6,
        "unsharp": True,
    }


def _box_center(box: list[Any]) -> tuple[float, float]:
    xs = [float(point[0]) for point in box]
    ys = [float(point[1]) for point in box]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def reading_order(
    texts: list[str],
    scores: list[float],
    boxes: list[Any],
    document_type: str,
    page_width: int,
) -> tuple[list[dict[str, Any]], str]:
    rows = []
    for index, text in enumerate(texts):
        box = boxes[index] if index < len(boxes) else []
        center_x, center_y = _box_center(box) if box else (0.0, float(index))
        rows.append(
            {
                "sourceIndex": index,
                "rawText": text,
                "confidence": scores[index] if index < len(scores) else None,
                "box": box,
                "centerX": center_x,
                "centerY": center_y,
            }
        )
    strategy = "top_to_bottom"
    if document_type == "CV" and len(rows) >= 6 and page_width > 0:
        centers = sorted(row["centerX"] for row in rows)
        gaps = [(centers[i + 1] - centers[i], i) for i in range(len(centers) - 1)]
        largest_gap, gap_index = max(gaps, default=(0.0, 0))
        if largest_gap >= page_width * 0.12:
            split_x = (centers[gap_index] + centers[gap_index + 1]) / 2
            left = [row for row in rows if row["centerX"] <= split_x]
            right = [row for row in rows if row["centerX"] > split_x]
            if len(left) >= 2 and len(right) >= 2:
                rows = sorted(left, key=lambda row: (row["centerY"], row["centerX"])) + sorted(
                    right, key=lambda row: (row["centerY"], row["centerX"])
                )
                strategy = "columns_left_to_right"
    if strategy == "top_to_bottom":
        rows.sort(key=lambda row: (row["centerY"], row["centerX"]))
    return rows, strategy


def conservative_correction(text: str, confidence: float | None) -> tuple[str, str | None]:
    key = accent_key(text)
    if not key or any(ch.isdigit() for ch in text) or "@" in text:
        return text, None
    corrected = SAFE_PHRASE_CORRECTIONS.get(key)
    method = "safe_phrase_dictionary"
    if corrected is None and len(key) >= 6:
        ranked = sorted(
            (
                (difflib.SequenceMatcher(None, key, candidate).ratio(), candidate)
                for candidate in SAFE_PHRASE_CORRECTIONS
            ),
            reverse=True,
        )
        best_score, best_key = ranked[0]
        next_score = ranked[1][0] if len(ranked) > 1 else 0.0
        if best_score >= 0.84 and best_score - next_score >= 0.08:
            corrected = SAFE_PHRASE_CORRECTIONS[best_key]
            method = "safe_phrase_fuzzy"
    if corrected is None:
        return text, None
    if text.isupper():
        corrected = corrected.upper()
    elif text[:1].islower():
        corrected = corrected[:1].lower() + corrected[1:]
    return corrected, method


def _valid_date(value: str) -> bool:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            continue
    return False


def quality_gate(
    pages: list[dict[str, Any]],
    document_type: str,
    corrected_lines: list[dict[str, Any]],
) -> dict[str, Any]:
    scores = [
        float(line["confidence"])
        for line in corrected_lines
        if line.get("confidence") is not None
    ]
    low_count = sum(score < LOW_CONFIDENCE for score in scores)
    critical_count = sum(score < 0.50 for score in scores)
    correction_count = sum(line.get("correctionApplied", False) for line in corrected_lines)
    low_ratio = low_count / len(scores) if scores else 1.0
    all_text = "\n".join(line["rawText"] for line in corrected_lines)
    dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", all_text)
    identity_numbers = re.findall(r"(?<!\d)\d{12}(?!\d)", all_text)
    warnings: list[str] = []
    if low_count:
        warnings.append(f"{low_count} line(s) below {LOW_CONFIDENCE:.0%} confidence")
    if critical_count:
        warnings.append(f"{critical_count} line(s) below 50% confidence")
    if correction_count:
        warnings.append(
            f"{correction_count} safe label correction(s); raw OCR remains authoritative"
        )
    if any(not _valid_date(value) for value in dates):
        warnings.append("At least one date candidate is invalid")
    if document_type == "IDENTITY_DOCUMENT" and not identity_numbers:
        warnings.append("No reliable 12-digit identity number candidate")
    if document_type == "IDENTITY_DOCUMENT" and low_ratio > 0.10:
        status = "FAIL"
    elif low_ratio > 0.20 or critical_count or correction_count >= 3:
        status = "REVIEW"
    else:
        status = "PASS"
    return {
        "status": status,
        "requiresHumanReview": status != "PASS",
        "thresholds": {
            "lineConfidence": LOW_CONFIDENCE,
            "criticalFieldConfidence": CRITICAL_CONFIDENCE,
        },
        "lineCount": len(scores),
        "lowConfidenceLineCount": low_count,
        "lowConfidenceRatio": round(low_ratio, 6),
        "criticalLowConfidenceLineCount": critical_count,
        "safeCorrectionCount": correction_count,
        "warnings": warnings,
        "validation": {
            "dateCandidateCount": len(dates),
            "validDateCandidateCount": sum(_valid_date(value) for value in dates),
            "identityNumberCandidateCount": len(identity_numbers),
        },
    }


def candidate_score(pages: list[dict[str, Any]], document_type: str) -> float:
    scores = [
        float(score)
        for page in pages
        for score in page.get("recognitionScores", [])
    ]
    if not scores:
        return 0.0
    mean = sum(scores) / len(scores)
    low_ratio = sum(score < LOW_CONFIDENCE for score in scores) / len(scores)
    text = "\n".join(
        text for page in pages for text in page.get("recognizedTexts", [])
    )
    bonus = 0.0
    if document_type == "IDENTITY_DOCUMENT":
        bonus += 0.04 if re.search(r"(?<!\d)\d{12}(?!\d)", text) else 0.0
        bonus += 0.02 if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b", text) else 0.0
    return round(mean - 0.20 * low_ratio + bonus, 6)


def enrich_result(
    result: dict[str, Any],
    routed_pages: list[dict[str, Any]] | None = None,
    preprocessing: list[dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    enriched = copy.deepcopy(result)
    previous_phase9 = enriched.get("phase9", {})
    raw_pages = copy.deepcopy(
        previous_phase9.get("rawOcr", {}).get("pages")
        or enriched["document"].get("pages", [])
    )
    raw_text = "\n".join(
        text for page in raw_pages for text in page.get("recognizedTexts", [])
    )
    document_type, route_confidence, evidence = classify_document(
        raw_text, enriched["source"].get("format", "")
    )
    selected_pages = raw_pages
    selected_variant = "phase8_raw"
    raw_score = candidate_score(raw_pages, document_type)
    routed_score = candidate_score(routed_pages or [], document_type)
    if routed_pages and routed_score > raw_score + 0.005:
        selected_pages = copy.deepcopy(routed_pages)
        selected_variant = "phase9_routed"

    phase9_pages: list[dict[str, Any]] = []
    all_lines: list[dict[str, Any]] = []
    for page_index, page in enumerate(selected_pages):
        size = page.get("preprocessing", {}).get("originalSize", [0, 0])
        page_width = int(size[0]) if size else 0
        ordered, strategy = reading_order(
            page.get("recognizedTexts", []),
            page.get("recognitionScores", []),
            page.get("recognizedBoxes", []),
            document_type,
            page_width,
        )
        for output_index, line in enumerate(ordered):
            corrected, method = conservative_correction(
                line["rawText"], line.get("confidence")
            )
            line["outputIndex"] = output_index
            line["correctedText"] = corrected
            line["correctionApplied"] = method is not None
            line["correctionMethod"] = method
            line["warning"] = (
                "LOW_CONFIDENCE"
                if line.get("confidence") is not None
                and line["confidence"] < LOW_CONFIDENCE
                else None
            )
            line.pop("centerX", None)
            line.pop("centerY", None)
        phase9_pages.append(
            {
                "pageIndex": page_index,
                "readingOrderStrategy": strategy,
                "lines": ordered,
                "rawText": "\n".join(line["rawText"] for line in ordered),
                "correctedText": "\n".join(line["correctedText"] for line in ordered),
            }
        )
        all_lines.extend(ordered)

    gate = quality_gate(selected_pages, document_type, all_lines)
    enriched["schemaVersion"] = "2.0.0"
    enriched["document"]["documentType"] = document_type
    enriched["document"]["rawRecognizedText"] = raw_text
    enriched["document"]["recognizedText"] = "\n".join(
        line["rawText"] for line in all_lines
    )
    enriched["document"]["correctedText"] = "\n".join(
        line["correctedText"] for line in all_lines
    )
    enriched["document"]["recognizedTextLineCount"] = len(all_lines)
    enriched["document"]["avgConfidence"] = (
        round(
            sum(float(line["confidence"]) for line in all_lines if line.get("confidence") is not None)
            / sum(line.get("confidence") is not None for line in all_lines),
            6,
        )
        if any(line.get("confidence") is not None for line in all_lines)
        else None
    )
    enriched["document"]["extractedCandidates"] = _safe_candidates(
        enriched["document"]["recognizedText"]
    )
    enriched["phase9"] = {
        "version": "1.0.0",
        "documentRoute": {
            "type": document_type,
            "confidence": route_confidence,
            "evidence": evidence,
        },
        "rawOcr": {"preserved": True, "score": raw_score, "pages": raw_pages},
        "routedOcr": {
            "available": bool(routed_pages),
            "score": routed_score if routed_pages else None,
            "preprocessing": preprocessing or [],
        },
        "selectedVariant": selected_variant,
        "correctionPolicy": {
            "mode": "conservative",
            "rawTextPreserved": True,
            "protectedFields": [
                "personName",
                "identityNumber",
                "date",
                "phoneNumber",
                "email",
            ],
        },
        "pages": phase9_pages,
        "qualityGate": gate,
    }
    return enriched


def _safe_candidates(text: str) -> dict[str, list[str]]:
    def unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(" ".join(value.split()) for value in values))

    return {
        "emails": unique(
            re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
        ),
        "phoneNumbers": unique(
            re.findall(r"(?<!\d)(?:\+?84|0)(?:[\s.\-]?\d){8,10}(?!\d)", text)
        ),
        "dates": unique(
            re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
        ),
        "identityNumberCandidates": unique(
            re.findall(r"(?<!\d)\d{12}(?!\d)", text)
        ),
        "employeeCodeCandidates": unique(
            re.findall(r"\b(?:NV|EMP|MSNV)[\s\-:]?[A-Z0-9]{3,12}\b", text, re.I)
        ),
    }
