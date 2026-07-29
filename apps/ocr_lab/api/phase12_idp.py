#!/usr/bin/env python3
"""Phase 12 HR document classification, extraction, and business mapping."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from typing import Any

HR_DOCUMENT_TYPES = (
    "CV",
    "DEGREE_CERTIFICATE",
    "EMPLOYMENT_CONTRACT",
    "HR_DECISION",
    "LEAVE_REQUEST",
    "EMPLOYEE_INFORMATION_FORM",
    "TIMESHEET",
    "GENERIC_DOCUMENT",
)

TYPE_RULES: dict[str, tuple[tuple[str, float], ...]] = {
    "CV": (
        ("curriculum vitae", 5.0),
        ("kinh nghiem lam viec", 3.0),
        ("muc tieu nghe nghiep", 3.0),
        ("hoc van", 1.5),
        ("ky nang", 1.0),
    ),
    "DEGREE_CERTIFICATE": (
        ("bang tot nghiep", 5.0),
        ("bang cu nhan", 5.0),
        ("bang ky su", 5.0),
        ("bang thac si", 5.0),
        ("chung chi", 5.0),
        ("certificate", 3.0),
        ("so hieu van bang", 2.0),
        ("nganh dao tao", 1.5),
        ("xep loai", 1.5),
        ("hieu truong", 1.5),
    ),
    "EMPLOYMENT_CONTRACT": (
        ("hop dong lao dong", 6.0),
        ("ben su dung lao dong", 2.5),
        ("nguoi lao dong", 2.0),
        ("muc luong", 2.0),
        ("dieu khoan", 1.5),
    ),
    "HR_DECISION": (
        ("quyet dinh nhan su", 6.0),
        ("giam doc cong ty quyet dinh", 3.0),
        ("bo nhiem", 1.5),
        ("dieu chuyen", 1.5),
        ("hieu luc tu ngay", 1.5),
    ),
    "LEAVE_REQUEST": (
        ("don xin nghi phep", 6.0),
        ("thoi gian nghi", 2.5),
        ("so ngay nghi", 2.0),
        ("nguoi lam don", 1.5),
        ("ly do", 1.0),
    ),
    "EMPLOYEE_INFORMATION_FORM": (
        ("phieu thong tin nhan vien", 6.0),
        ("dia chi lien he", 2.0),
        ("ma nhan vien", 1.0),
        ("phong ban", 1.0),
        ("ngay sinh", 1.0),
    ),
    "TIMESHEET": (
        ("bang cham cong", 6.0),
        ("ky cham cong", 2.5),
        ("ngay cong", 2.0),
        ("gio tang ca", 2.0),
        ("nghi phep", 1.0),
    ),
}

FIELD_SCHEMAS: dict[str, tuple[str, ...]] = {
    "LEAVE_REQUEST": (
        "employeeName",
        "employeeId",
        "department",
        "leaveStartDate",
        "leaveEndDate",
        "leaveDays",
        "leaveReason",
    ),
    "EMPLOYMENT_CONTRACT": (
        "contractNumber",
        "employeeName",
        "employeeId",
        "jobTitle",
        "salary",
        "startDate",
    ),
    "HR_DECISION": (
        "decisionNumber",
        "employeeName",
        "employeeId",
        "action",
        "newJobTitle",
        "effectiveDate",
    ),
    "EMPLOYEE_INFORMATION_FORM": (
        "employeeName",
        "employeeId",
        "dateOfBirth",
        "gender",
        "department",
        "email",
        "phoneNumber",
        "address",
    ),
    "TIMESHEET": (
        "timesheetPeriod",
        "totalEmployees",
        "companyName",
    ),
}

CAMUNDA_PROCESS_KEYS = {
    "CV": "hr-cv-review",
    "DEGREE_CERTIFICATE": "hr-qualification-review",
    "EMPLOYMENT_CONTRACT": "hr-contract-review",
    "HR_DECISION": "hr-decision-review",
    "LEAVE_REQUEST": "hr-leave-request",
    "EMPLOYEE_INFORMATION_FORM": "hr-employee-onboarding",
    "TIMESHEET": "hr-timesheet-review",
    "GENERIC_DOCUMENT": "hr-document-review",
}


def accent_key(value: Any) -> str:
    text = " ".join(str(value or "").casefold().replace("đ", "d").split())
    decomposed = unicodedata.normalize("NFD", text)
    plain = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def classify_hr_document(
    canonical: dict[str, Any],
    existing_route: str | None = None,
) -> dict[str, Any]:
    if existing_route == "IDENTITY_DOCUMENT":
        return {
            "documentType": "IDENTITY_DOCUMENT",
            "confidence": 1.0,
            "status": "accepted",
            "evidence": ["phase9:identity_document"],
            "supportedHrTypes": list(HR_DOCUMENT_TYPES),
        }
    text = accent_key(canonical.get("plainText", ""))
    leading_blocks = [
        accent_key(block.get("text"))
        for block in _blocks(canonical)[:6]
    ]
    if any(
        term in text
        for term in (
            "the dinh danh cong dan",
            "can cuoc cong dan",
            "citizen identity card",
        )
    ):
        return {
            "documentType": "IDENTITY_DOCUMENT",
            "confidence": 0.98,
            "status": "accepted",
            "evidence": ["identity_document_title"],
            "supportedHrTypes": list(HR_DOCUMENT_TYPES),
        }
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    for document_type, rules in TYPE_RULES.items():
        matched = []
        for term, weight in rules:
            if term not in text:
                continue
            title_match = any(
                block_key == term or block_key.startswith(f"{term} ")
                for block_key in leading_blocks
            )
            effective_weight = (
                weight
                if weight < 5.0 or title_match
                else weight * 0.2
            )
            matched.append((term, effective_weight))
        scores[document_type] = sum(weight for _, weight in matched)
        evidence[document_type] = [term for term, _ in matched]
    employee_form_title = any(
        block_key == "phieu thong tin nhan vien"
        or block_key.startswith("phieu thong tin nhan vien ")
        for block_key in leading_blocks
    )
    if not employee_form_title:
        scores["EMPLOYEE_INFORMATION_FORM"] = min(
            scores.get("EMPLOYEE_INFORMATION_FORM", 0.0),
            2.4,
        )
    if canonical.get("sourceFormat") == "XLSX":
        scores["TIMESHEET"] = scores.get("TIMESHEET", 0.0) + 2.5
        evidence.setdefault("TIMESHEET", []).append("format:xlsx")
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    selected, best_score = ranked[0] if ranked else ("GENERIC_DOCUMENT", 0.0)
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if best_score < 2.5:
        selected = "GENERIC_DOCUMENT"
    if selected == "GENERIC_DOCUMENT":
        confidence = 0.55
        selected_evidence = [
            f"format:{str(canonical.get('sourceFormat', '')).lower()}"
        ]
    else:
        margin = max(0.0, best_score - second_score)
        confidence = min(0.99, 0.60 + best_score * 0.035 + margin * 0.025)
        selected_evidence = evidence[selected]
    return {
        "documentType": selected,
        "confidence": round(confidence, 6),
        "status": (
            "accepted"
            if confidence >= 0.80
            else "needs_review"
        ),
        "evidence": selected_evidence[:6],
        "scores": {
            document_type: round(score, 3)
            for document_type, score in scores.items()
        },
        "supportedHrTypes": list(HR_DOCUMENT_TYPES),
    }


def _blocks(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for page in canonical.get("pages", [])
        for block in page.get("blocks", [])
        if block.get("text")
    ]


def _normalized_date(value: str) -> str | None:
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", value)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day).strftime("%d/%m/%Y")
    except ValueError:
        return None


def _field(
    value: Any,
    block: dict[str, Any] | None,
    *,
    data_type: str = "string",
    normalized_value: Any = None,
    valid: bool = True,
    method: str = "label_value",
) -> dict[str, Any]:
    if value is None or str(value).strip() == "":
        return {
            "value": None,
            "normalizedValue": None,
            "dataType": data_type,
            "confidence": None,
            "status": "not_found",
            "validation": {
                "valid": False,
                "method": method,
            },
            "evidence": None,
        }
    confidence = float(block.get("confidence", 0.0)) if block else 0.0
    source_kind = block.get("sourceKind", "") if block else ""
    accepted = bool(valid and source_kind != "ocr")
    if source_kind == "ocr":
        accepted = bool(valid and confidence >= 0.94)
    return {
        "value": value,
        "normalizedValue": (
            value if normalized_value is None else normalized_value
        ),
        "dataType": data_type,
        "confidence": round(confidence, 6),
        "status": "accepted" if accepted else "needs_review",
        "validation": {
            "valid": bool(valid),
            "method": method,
        },
        "evidence": {
            "sourceKind": source_kind,
            **(block.get("evidence") or {}),
        }
        if block
        else None,
    }


def _next_value(
    blocks: list[dict[str, Any]],
    index: int,
) -> tuple[str | None, dict[str, Any] | None]:
    if index + 1 >= len(blocks):
        return None, None
    candidate = blocks[index + 1]
    text = candidate["text"].strip(" :|-")
    if not text or len(text) > 300:
        return None, None
    if re.match(r"^[^:]{1,45}:\s*", text):
        return None, None
    return text, candidate


def _labeled(
    canonical: dict[str, Any],
    labels: tuple[str, ...],
    *,
    data_type: str = "string",
    normalizer: Callable[[str], Any] | None = None,
    validator: Callable[[Any], bool] | None = None,
) -> dict[str, Any]:
    blocks = _blocks(canonical)
    label_pattern = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(
        rf"^(?:{label_pattern})\s*(?:[:\-]\s*)?(.*)$",
        re.IGNORECASE,
    )
    for index, block in enumerate(blocks):
        match = pattern.search(block["text"])
        if not match:
            continue
        value = match.group(1).strip(" :|-")
        evidence_block = block
        if not value:
            value, evidence_block = _next_value(blocks, index)
        if not value:
            continue
        normalized = normalizer(value) if normalizer else value
        valid = (
            validator(normalized)
            if validator
            else normalized is not None and str(normalized).strip() != ""
        )
        return _field(
            value,
            evidence_block,
            data_type=data_type,
            normalized_value=normalized,
            valid=valid,
        )
    return _field(None, None, data_type=data_type)


def _regex_field(
    canonical: dict[str, Any],
    patterns: tuple[str, ...],
    *,
    group: int | str = 1,
    data_type: str = "string",
    normalizer: Callable[[str], Any] | None = None,
    validator: Callable[[Any], bool] | None = None,
    method: str = "anchored_pattern",
) -> dict[str, Any]:
    for block in _blocks(canonical):
        for pattern in patterns:
            match = re.search(pattern, block["text"], re.IGNORECASE)
            if not match:
                continue
            value = match.group(group).strip(" .,:;-")
            normalized = normalizer(value) if normalizer else value
            valid = validator(normalized) if validator else bool(normalized)
            return _field(
                value,
                block,
                data_type=data_type,
                normalized_value=normalized,
                valid=valid,
                method=method,
            )
    return _field(None, None, data_type=data_type, method=method)


def _employee_id(value: Any) -> bool:
    return bool(
        re.fullmatch(
            r"(?=.*\d)[A-ZÀ-ỸĐ][A-ZÀ-ỸĐ0-9]{2,}"
            r"(?:[-/][A-ZÀ-ỸĐ0-9]+)*",
            str(value).strip(),
            re.I,
        )
    )


def _email(value: Any) -> bool:
    return bool(
        re.fullmatch(
            r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
            str(value),
            re.I,
        )
    )


def _phone(value: Any) -> bool:
    digits = re.sub(r"\D", "", str(value))
    return 9 <= len(digits) <= 12


def _schema_output(
    document_type: str,
    fields: dict[str, dict[str, Any]],
    tables: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    statuses = [field["status"] for field in fields.values()]
    present = sum(field["value"] is not None for field in fields.values())
    accepted = statuses.count("accepted")
    expected = len(fields)
    return {
        "schemaVersion": "1.0.0",
        "documentType": document_type,
        "fields": fields,
        "tables": tables or [],
        "summary": {
            "expectedFieldCount": expected,
            "presentFieldCount": present,
            "acceptedFieldCount": accepted,
            "needsReviewFieldCount": statuses.count("needs_review"),
            "notFoundFieldCount": statuses.count("not_found"),
            "documentCompleteness": round(present / max(1, expected), 6),
            "acceptedCoverage": round(accepted / max(1, expected), 6),
            "readyForAutomaticUse": (
                expected > 0 and accepted == expected
            ),
        },
    }


def parse_leave_request(canonical: dict[str, Any]) -> dict[str, Any]:
    dates = _regex_field(
        canonical,
        (
            r"(?:Thời gian nghỉ\s*:\s*)?[Tt]ừ\s+"
            r"(?P<start>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"
            r"\s+đến\s+"
            r"(?P<end>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        ),
        group="start",
        data_type="date",
        normalizer=_normalized_date,
    )
    end_date = _regex_field(
        canonical,
        (
            r"(?:Thời gian nghỉ\s*:\s*)?[Tt]ừ\s+"
            r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
            r"\s+đến\s+"
            r"(?P<end>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        ),
        group="end",
        data_type="date",
        normalizer=_normalized_date,
    )
    fields = {
        "employeeName": _labeled(canonical, ("Họ và tên", "Họ tên")),
        "employeeId": _labeled(
            canonical,
            ("Mã nhân viên", "Mã NV"),
            validator=_employee_id,
        ),
        "department": _labeled(
            canonical,
            ("Bộ phận", "Phòng ban"),
        ),
        "leaveStartDate": dates,
        "leaveEndDate": end_date,
        "leaveDays": _labeled(
            canonical,
            ("Số ngày nghỉ",),
            data_type="integer",
            normalizer=lambda value: (
                int(re.search(r"\d+", value).group(0))
                if re.search(r"\d+", value)
                else None
            ),
            validator=lambda value: isinstance(value, int) and value > 0,
        ),
        "leaveReason": _labeled(canonical, ("Lý do",)),
    }
    return _schema_output("LEAVE_REQUEST", fields)


def parse_employment_contract(
    canonical: dict[str, Any],
) -> dict[str, Any]:
    fields = {
        "contractNumber": _regex_field(
            canonical,
            (
                r"(?:Số(?: hợp đồng)?\s*:\s*)"
                r"([A-ZÀ-Ỹ0-9Đ./-]{4,})",
            ),
        ),
        "employeeName": _labeled(
            canonical,
            ("Người lao động", "Họ và tên"),
        ),
        "employeeId": _labeled(
            canonical,
            ("Mã nhân viên", "Mã NV"),
            validator=_employee_id,
        ),
        "jobTitle": _labeled(
            canonical,
            ("Chức danh", "Vị trí công việc"),
        ),
        "salary": _labeled(
            canonical,
            ("Mức lương cơ bản", "Lương cơ bản", "Mức lương"),
        ),
        "startDate": _labeled(
            canonical,
            ("Ngày bắt đầu", "Ngày hiệu lực"),
            data_type="date",
            normalizer=_normalized_date,
        ),
    }
    return _schema_output("EMPLOYMENT_CONTRACT", fields)


def parse_hr_decision(canonical: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "decisionNumber": _regex_field(
            canonical,
            (
                r"(?:Số\s*:\s*)([A-ZÀ-Ỹ0-9Đ./-]{4,})",
            ),
        ),
        "employeeName": _regex_field(
            canonical,
            (
                r"(?:Bổ nhiệm|Điều chuyển|Nâng bậc lương)"
                r"\s+Ông/Bà\s+(.+?),\s*mã nhân viên",
            ),
        ),
        "employeeId": _regex_field(
            canonical,
            (r"mã nhân viên\s+([A-Z0-9/-]+)",),
            validator=_employee_id,
        ),
        "action": _regex_field(
            canonical,
            (
                r"Về việc\s*:\s*(bổ nhiệm|điều chuyển|nâng bậc lương)",
                r"Điều 1\.\s*(Bổ nhiệm|Điều chuyển|Nâng bậc lương)",
            ),
            normalizer=lambda value: value[:1].upper() + value[1:].lower(),
        ),
        "newJobTitle": _regex_field(
            canonical,
            (
                r"Chức danh\s*:\s*(.+?)(?:,\s*hiệu lực|$)",
            ),
        ),
        "effectiveDate": _regex_field(
            canonical,
            (
                r"hiệu lực từ ngày\s+"
                r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            ),
            data_type="date",
            normalizer=_normalized_date,
        ),
    }
    return _schema_output("HR_DECISION", fields)


def parse_employee_information_form(
    canonical: dict[str, Any],
) -> dict[str, Any]:
    fields = {
        "employeeName": _labeled(
            canonical,
            ("Họ và tên", "Họ tên"),
        ),
        "employeeId": _labeled(
            canonical,
            ("Mã nhân viên", "Mã NV"),
            validator=_employee_id,
        ),
        "dateOfBirth": _regex_field(
            canonical,
            (
                r"Ngày sinh(?:\s*/\s*Giới tính)?\s*(?:[:|]\s*)?"
                r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            ),
            data_type="date",
            normalizer=_normalized_date,
        ),
        "gender": _employee_form_gender(canonical),
        "department": _labeled(
            canonical,
            ("Phòng ban", "Bộ phận"),
        ),
        "email": _labeled(
            canonical,
            ("Email", "Thư điện tử"),
            validator=_email,
        ),
        "phoneNumber": _labeled(
            canonical,
            ("Điện thoại", "Số điện thoại"),
            validator=_phone,
        ),
        "address": _labeled(
            canonical,
            ("Địa chỉ liên hệ", "Địa chỉ"),
        ),
    }
    return _schema_output("EMPLOYEE_INFORMATION_FORM", fields)


def _employee_form_gender(
    canonical: dict[str, Any],
) -> dict[str, Any]:
    blocks = _blocks(canonical)
    pattern = re.compile(
        r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*/\s*(Nam|Nữ)",
        re.IGNORECASE,
    )
    for index, block in enumerate(blocks):
        key = accent_key(block["text"])
        if "ngay sinh" not in key or "gioi tinh" not in key:
            continue
        next_block = blocks[index + 1] if index + 1 < len(blocks) else block
        combined = f"{block['text']} {next_block['text']}"
        match = pattern.search(combined)
        if match:
            normalized = (
                "Nữ"
                if accent_key(match.group(1)).startswith("nu")
                else "Nam"
            )
            return _field(
                normalized,
                next_block,
                normalized_value=normalized,
                valid=True,
                method="combined_date_gender_row",
            )
    return _regex_field(
        canonical,
        (r"Giới tính\s*:\s*(Nam|Nữ)",),
        normalizer=lambda value: (
            "Nữ"
            if accent_key(value).startswith("nu")
            else "Nam"
            if accent_key(value).startswith("nam")
            else None
        ),
        validator=lambda value: value in {"Nam", "Nữ"},
    )


TIMESHEET_HEADERS = {
    "employeeId": ("ma nv", "ma nhan vien"),
    "employeeName": ("ho va ten", "ho ten"),
    "department": ("phong ban", "bo phan", "chuc vu bo phan", "chuc vu"),
    "workDays": (
        "ngay cong",
        "so ngay cong",
        "tong cong ngay cong",
        "tong ngay cong",
    ),
    "leaveDays": ("nghi phep", "ngay nghi"),
    "overtimeHours": ("gio tang ca", "tang ca"),
    "status": ("trang thai",),
}


def _header_mapping(columns: list[dict[str, Any]]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for column in columns:
        key = accent_key(column.get("name"))
        for field_name, labels in TIMESHEET_HEADERS.items():
            if any(label == key or label in key for label in labels):
                mapping[field_name] = int(column["columnIndex"])
    return mapping


def _box_bounds(box: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(box, list) or len(box) < 2:
        return None
    try:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
    except (TypeError, ValueError, IndexError):
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _ocr_table(canonical: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [
        block
        for page in canonical.get("pages", [])
        for block in page.get("ocrBlocks", [])
        if _box_bounds((block.get("evidence") or {}).get("bbox"))
    ]
    if not candidates:
        return None
    heights = [
        bounds[3] - bounds[1]
        for block in candidates
        for bounds in [_box_bounds((block.get("evidence") or {}).get("bbox"))]
        if bounds
    ]
    tolerance = max(8.0, sorted(heights)[len(heights) // 2] * 0.65)
    rows: list[list[dict[str, Any]]] = []
    for block in sorted(
        candidates,
        key=lambda item: (
            _box_bounds((item.get("evidence") or {}).get("bbox"))[1],
            _box_bounds((item.get("evidence") or {}).get("bbox"))[0],
        ),
    ):
        bounds = _box_bounds((block.get("evidence") or {}).get("bbox"))
        center_y = (bounds[1] + bounds[3]) / 2
        target = None
        for row in rows:
            row_bounds = _box_bounds(
                (row[0].get("evidence") or {}).get("bbox")
            )
            row_y = (row_bounds[1] + row_bounds[3]) / 2
            if abs(center_y - row_y) <= tolerance:
                target = row
                break
        if target is None:
            target = []
            rows.append(target)
        target.append(block)
    ordered_rows = [
        sorted(
            row,
            key=lambda item: _box_bounds(
                (item.get("evidence") or {}).get("bbox")
            )[0],
        )
        for row in rows
    ]
    header_index = -1
    header_mapping: dict[str, int] = {}
    header_centers: list[float] = []
    for index, row in enumerate(ordered_rows):
        columns = [
            {"columnIndex": column, "name": block["text"]}
            for column, block in enumerate(row)
        ]
        mapping = _header_mapping(columns)
        if len(mapping) >= 4:
            header_index = index
            header_mapping = mapping
            header_centers = [
                sum(_box_bounds((block.get("evidence") or {}).get("bbox"))[::2])
                / 2
                for block in row
            ]
            break
    if header_index < 0:
        return None
    table_rows: list[dict[str, Any]] = []
    for source_row in ordered_rows[header_index + 1 :]:
        if any("tong cong" in accent_key(block["text"]) for block in source_row):
            break
        values = [""] * len(header_centers)
        cells: list[dict[str, Any]] = [
            {
                "columnIndex": index,
                "value": "",
                "status": "not_found",
                "evidence": None,
            }
            for index in range(len(header_centers))
        ]
        for block in source_row:
            bounds = _box_bounds((block.get("evidence") or {}).get("bbox"))
            center = (bounds[0] + bounds[2]) / 2
            column = min(
                range(len(header_centers)),
                key=lambda item: abs(header_centers[item] - center),
            )
            values[column] = block["text"]
            cells[column] = {
                "columnIndex": column,
                "value": block["text"],
                "status": (
                    "accepted"
                    if float(block.get("confidence", 0)) >= 0.94
                    else "needs_review"
                ),
                "evidence": block.get("evidence"),
            }
        table_rows.append(
            {
                "rowIndex": len(table_rows),
                "values": values,
                "cells": cells,
            }
        )
    columns = [
        {
            "columnIndex": index,
            "name": ordered_rows[header_index][index]["text"],
        }
        for index in range(len(ordered_rows[header_index]))
    ]
    return {
        "tableIndex": 0,
        "pageIndex": 0,
        "sourceKind": "ocr_coordinate_table",
        "columns": columns,
        "rows": table_rows,
        "headerMapping": header_mapping,
    }


def parse_timesheet(canonical: dict[str, Any]) -> dict[str, Any]:
    table_candidates = list(canonical.get("tables", []))
    coordinate_table = _ocr_table(canonical)
    if coordinate_table:
        table_candidates.append(coordinate_table)
    selected: dict[str, Any] | None = None
    mapping: dict[str, int] = {}
    for candidate in table_candidates:
        current = _header_mapping(candidate.get("columns", []))
        if len(current) > len(mapping):
            selected = candidate
            mapping = current
    normalized_rows: list[dict[str, Any]] = []
    if selected and len(mapping) >= 4:
        id_column = mapping.get("employeeId")
        for row in selected.get("rows", []):
            values = row.get("values", [])
            if id_column is None or id_column >= len(values):
                continue
            employee_id = str(values[id_column] or "").strip()
            if not _employee_id(employee_id):
                continue
            fields: dict[str, Any] = {}
            for field_name, column_index in mapping.items():
                cell = (
                    row.get("cells", [])[column_index]
                    if column_index < len(row.get("cells", []))
                    else None
                )
                value = (
                    values[column_index]
                    if column_index < len(values)
                    else None
                )
                normalized = value
                if field_name in {
                    "workDays",
                    "leaveDays",
                    "overtimeHours",
                }:
                    try:
                        normalized = int(float(value))
                    except (TypeError, ValueError):
                        normalized = None
                source_kind = selected.get("sourceKind", "")
                evidence_block = {
                    "sourceKind": source_kind,
                    "confidence": (
                        1.0
                        if source_kind in {"xlsx_cells", "docx_table"}
                        else 0.0
                    ),
                    "evidence": (cell or {}).get("evidence"),
                }
                fields[field_name] = _field(
                    value,
                    evidence_block,
                    data_type=(
                        "integer"
                        if field_name
                        in {"workDays", "leaveDays", "overtimeHours"}
                        else "string"
                    ),
                    normalized_value=normalized,
                    valid=normalized is not None and str(normalized) != "",
                    method="table_header_coordinate",
                )
            normalized_rows.append(
                {
                    "rowIndex": len(normalized_rows),
                    "values": list(values[id_column:]),
                    "fields": fields,
                    "status": (
                        "accepted"
                        if fields
                        and all(
                            field["status"] == "accepted"
                            for field in fields.values()
                        )
                        else "needs_review"
                    ),
                }
            )
    period = _labeled(
        canonical,
        ("Kỳ chấm công", "Tháng chấm công"),
    )
    if period["value"] is None:
        period = _regex_field(
            canonical,
            (
                r"bảng\s+chấm\s+công\s+tháng\s+"
                r"(\d{1,2}[/-]\d{4})",
            ),
            method="timesheet_title_period",
        )
    company = _regex_field(
        canonical,
        (
            r"((?:CÔNG TY|Công ty)\s+.+)$",
        ),
    )
    table_evidence = None
    if selected:
        table_evidence = {
            "sourceKind": selected.get("sourceKind"),
            "confidence": (
                1.0 if selected.get("sourceKind") == "xlsx_cells" else 0.0
            ),
            "evidence": {
                "pageIndex": selected.get("pageIndex"),
                "sheetName": selected.get("sheetName"),
                "tableIndex": selected.get("tableIndex"),
            },
        }
    total_employees = _field(
        len(normalized_rows) if normalized_rows else None,
        table_evidence,
        data_type="integer",
        valid=bool(normalized_rows),
        method="table_row_count",
    )
    fields = {
        "timesheetPeriod": period,
        "totalEmployees": total_employees,
        "companyName": company,
    }
    output_table = {
        "tableIndex": 0,
        "tableType": "TIMESHEET_EMPLOYEES",
        "sourceKind": selected.get("sourceKind") if selected else None,
        "columnMapping": mapping,
        "columns": (
            list(selected.get("columns", []))[id_column:]
            if selected and id_column is not None
            else []
        ),
        "rows": normalized_rows,
        "summary": {
            "rowCount": len(normalized_rows),
            "acceptedRowCount": sum(
                row["status"] == "accepted" for row in normalized_rows
            ),
            "columnCount": len(mapping),
        },
    }
    return _schema_output("TIMESHEET", fields, [output_table])


PARSERS = {
    "LEAVE_REQUEST": parse_leave_request,
    "EMPLOYMENT_CONTRACT": parse_employment_contract,
    "HR_DECISION": parse_hr_decision,
    "EMPLOYEE_INFORMATION_FORM": parse_employee_information_form,
    "TIMESHEET": parse_timesheet,
}


def extract_hr_document(
    canonical: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    document_type = classification["documentType"]
    parser = PARSERS.get(document_type)
    if parser:
        return parser(canonical)
    return _schema_output(document_type, {})


def build_business_json(
    document_id: str,
    canonical: dict[str, Any],
    classification: dict[str, Any],
    extraction: dict[str, Any],
    *,
    contains_real_pii: bool = True,
) -> dict[str, Any]:
    document_type = classification["documentType"]
    fields = extraction.get("fields", {})
    tables = extraction.get("tables", [])
    review_required = (
        classification.get("status") != "accepted"
        or extraction.get("summary", {}).get("expectedFieldCount", 0) == 0
        or bool(canonical.get("metadata", {}).get("requiresImageOcr"))
        or any(
            field.get("status") != "accepted"
            for field in fields.values()
        )
        or any(
            row.get("status") != "accepted"
            for table in tables
            for row in table.get("rows", [])
        )
    )
    idp_status = "NEEDS_REVIEW" if review_required else "READY"
    payload = {
        "documentId": document_id,
        "documentType": document_type,
        "classification": {
            "confidence": classification.get("confidence"),
            "status": classification.get("status"),
            "evidence": classification.get("evidence", []),
        },
        "ingestion": {
            "sourceFormat": canonical.get("sourceFormat"),
            "mode": canonical.get("ingestionMode"),
            "adapter": canonical.get("adapter"),
            "pageCount": canonical.get("pageCount"),
        },
        "fields": fields,
        "tables": tables,
        "summary": extraction.get("summary", {}),
    }
    business_json = {
        "schemaVersion": "1.0.0",
        "documentId": document_id,
        "documentType": document_type,
        "idpStatus": idp_status,
        "containsRealPII": bool(contains_real_pii),
        "processingPolicy": {
            "evidenceRequired": True,
            "unverifiedValuesMayBeAccepted": False,
            "localOnly": True,
        },
        "payload": payload,
        "camunda": {
            "businessKey": document_id,
            "processDefinitionKey": CAMUNDA_PROCESS_KEYS.get(
                document_type,
                "hr-document-review",
            ),
            "variables": {
                "documentId": {
                    "type": "String",
                    "value": document_id,
                },
                "documentType": {
                    "type": "String",
                    "value": document_type,
                },
                "idpStatus": {
                    "type": "String",
                    "value": idp_status,
                },
                "requiresHumanReview": {
                    "type": "Boolean",
                    "value": review_required,
                },
                "idpPayload": {
                    "type": "Json",
                    "value": payload,
                },
            },
        },
    }
    validate_business_json(business_json)
    return business_json


def validate_business_json(payload: dict[str, Any]) -> None:
    required = {
        "schemaVersion",
        "documentId",
        "documentType",
        "idpStatus",
        "payload",
        "camunda",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"Business JSON is missing keys: {sorted(missing)}")
    if payload["idpStatus"] not in {"READY", "NEEDS_REVIEW"}:
        raise ValueError("Invalid IDP status")
    for field_name, field in (
        payload.get("payload", {}).get("fields", {}).items()
    ):
        if field.get("value") is not None and not field.get("evidence"):
            raise ValueError(
                f"Field {field_name} has a value without evidence"
            )
        if (
            field.get("status") == "accepted"
            and not field.get("validation", {}).get("valid")
        ):
            raise ValueError(
                f"Field {field_name} is accepted without validation"
            )
    variables = payload.get("camunda", {}).get("variables", {})
    for required_variable in (
        "documentId",
        "documentType",
        "idpStatus",
        "requiresHumanReview",
        "idpPayload",
    ):
        if required_variable not in variables:
            raise ValueError(
                f"Missing Camunda variable: {required_variable}"
            )


def sanitized_summary(
    classification: dict[str, Any],
    extraction: dict[str, Any],
    duration_ms: int,
) -> dict[str, Any]:
    summary = extraction.get("summary", {})
    return {
        "documentType": classification.get("documentType"),
        "classificationStatus": classification.get("status"),
        "classificationConfidence": classification.get("confidence"),
        "expectedFieldCount": summary.get("expectedFieldCount", 0),
        "presentFieldCount": summary.get("presentFieldCount", 0),
        "acceptedFieldCount": summary.get("acceptedFieldCount", 0),
        "needsReviewFieldCount": summary.get("needsReviewFieldCount", 0),
        "notFoundFieldCount": summary.get("notFoundFieldCount", 0),
        "documentCompleteness": summary.get("documentCompleteness", 0.0),
        "acceptedCoverage": summary.get("acceptedCoverage", 0.0),
        "tableCount": len(extraction.get("tables", [])),
        "tableRowCount": sum(
            len(table.get("rows", []))
            for table in extraction.get("tables", [])
        ),
        "durationMs": int(duration_ms),
    }


def business_json_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:local:hr-idp:business-json:1.0.0",
        "title": "Vietnamese HR IDP Business JSON",
        "type": "object",
        "required": [
            "schemaVersion",
            "documentId",
            "documentType",
            "idpStatus",
            "processingPolicy",
            "payload",
            "camunda",
        ],
        "properties": {
            "schemaVersion": {"const": "1.0.0"},
            "documentId": {"type": "string", "minLength": 1},
            "documentType": {
                "enum": [*HR_DOCUMENT_TYPES, "IDENTITY_DOCUMENT"]
            },
            "idpStatus": {"enum": ["READY", "NEEDS_REVIEW"]},
            "containsRealPII": {"type": "boolean"},
            "processingPolicy": {"type": "object"},
            "payload": {"type": "object"},
            "camunda": {
                "type": "object",
                "required": [
                    "businessKey",
                    "processDefinitionKey",
                    "variables",
                ],
            },
        },
    }
