"""Parser for the approved Vietnamese leave-request DOCX template."""

from __future__ import annotations

import re

from hcns_agent.domain.canonical import CanonicalDocument, Table
from hcns_agent.domain.documents import SourceFormat
from hcns_agent.templates.common import (
    document_text,
    extract_unique,
    iso_date,
    named_dates,
    normalize_for_match,
    number_value,
    ocr_line_value,
    ocr_lines,
    ocr_roi_evidence,
    repair_template_ocr_value,
    strip_terminal,
    trim_ocr_commitment,
)
from hcns_agent.templates.model import ParsedTemplate, TemplateDetection


class LeaveRequestParser:
    def parse(
        self,
        document: CanonicalDocument,
        detection: TemplateDetection,
    ) -> ParsedTemplate:
        text = document_text(document)
        conflicts: set[str] = set()

        def field(name: str, pattern: str) -> str | None:
            value, conflicting = extract_unique(text, pattern)
            if conflicting:
                conflicts.add(name)
            return strip_terminal(value)

        leave_period = re.search(
            r"trong\s+thời\s+gian\s+(\d+(?:[.,]\d+)?)\s+ngày.*?"
            r"kể\s+từ\s+ngày\s+(\d{1,2}/\d{1,2}/\d{4}).*?"
            r"đến\s+hết\s+ngày\s+(\d{1,2}/\d{1,2}/\d{4})",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        reason_return = re.search(
            r"Lý\s+do\s+xin\s+nghỉ\s+phép\s*:\s*(.+?)\.\s*"
            r"Tôi\s+dự\s+kiến\s+trở\s+lại\s+làm\s+việc\s+vào\s+ngày\s+"
            r"(\d{1,2}/\d{1,2}/\d{4})",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        request_dates = named_dates(text)
        handover = re.search(
            r"Tôi\s+đã\s+bàn\s+giao\s+công\s+việc\s+cho\s*:\s*(.+?)\s*-\s*"
            r"Bộ\s+phận\s*:\s*(.+?)(?:\.|\n)",
            text,
            flags=re.IGNORECASE,
        )
        if document.source_format in {SourceFormat.IMAGE, SourceFormat.PDF_SCAN}:
            leave_period = leave_period or re.search(
                r"gian\s+(\d+(?:[.,]\d+)?)\s+ngày.*?"
                r"(\d{1,2}/\d{1,2}/\d{4}).*?"
                r"(\d{1,2}/\d{1,2}/\d{4})",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            reason_return = reason_return or re.search(
                r"Lý\s+do\s+xin\s+nghi\s+phép\s*:\s*(.+?)\.\s*"
                r"Tôi\s+d\s+ki.n.*?ngày\s+(\d{1,2}/\d{1,2}/\d{4})",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )

        data: dict[str, object] = {
            "documentId": document.document_id,
            "documentType": detection.definition.document_type.value,
            "templateId": detection.definition.template_id,
            "templateVersion": detection.definition.version,
            "documentTitle": "ĐƠN XIN NGHỈ PHÉP",
            "formNumber": None,
            "organization": field(
                "organization",
                r"Kính\s+gửi\s*:\s*(?:-\s*)?Ban\s+Giám\s+đốc\s+([^\n]+)",
            ),
            "employeeName": field("employeeName", r"Tôi\s+tên\s+là\s*:\s*([^\n]+)"),
            "employeeId": None,
            "jobTitle": field("jobTitle", r"Chức\s+vụ\s*:\s*([^\n]+)"),
            "department": field(
                "department",
                r"(?m)^Bộ\s+phận\s*:\s*([^\n.]+)$",
            ),
            "address": field("address", r"Địa\s+chỉ\s*:\s*([^\n]+)"),
            "phone": field("phone", r"Điện\s+thoại\s*:\s*([^\n]+)"),
            "requestDate": request_dates[-1] if request_dates else None,
            "leaveDays": (
                number_value(leave_period.group(1)) if leave_period is not None else None
            ),
            "startDate": iso_date(leave_period.group(2)) if leave_period is not None else None,
            "endDate": iso_date(leave_period.group(3)) if leave_period is not None else None,
            "reason": strip_terminal(reason_return.group(1)) if reason_return else None,
            "expectedReturnDate": (
                iso_date(reason_return.group(2)) if reason_return is not None else None
            ),
            "handoverTo": strip_terminal(handover.group(1)) if handover else None,
            "handoverDepartment": strip_terminal(handover.group(2)) if handover else None,
            "handoverTasks": field(
                "handoverTasks",
                r"Các\s+công\s+việc\s+được\s+bàn\s+giao\s*:\s*([^\n]+)",
            ),
            "approverName": _approver_name(document),
            "sourceFile": document.source.filename,
        }
        if reason_return is None:
            data["reason"] = field(
                "reason",
                r"Lý\s+do\s+xin\s+nghỉ\s+phép\s*:\s*([^\n]+)",
            )
        if document.source_format in {SourceFormat.IMAGE, SourceFormat.PDF_SCAN}:
            _fill_ocr_line_fields(data, text)
            _fill_ocr_geometry_fields(data, document)
            _fill_roi_fields(data, document)
            data["jobTitle"] = repair_template_ocr_value(data.get("jobTitle"), "jobTitle")
            data["department"] = repair_template_ocr_value(
                data.get("department"), "department"
            )
            slash_dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", text)
            if data["startDate"] is None and len(slash_dates) >= 2:
                data["startDate"] = iso_date(slash_dates[0])
                data["endDate"] = iso_date(slash_dates[1])
            if data["expectedReturnDate"] is None and len(slash_dates) >= 3:
                data["expectedReturnDate"] = iso_date(slash_dates[2])
        return ParsedTemplate(data=data, conflicting_fields=tuple(sorted(conflicts)))


def _approver_name(document: CanonicalDocument) -> str | None:
    for block in document.content.blocks:
        if not isinstance(block, Table) or len(block.rows) < 3:
            continue
        header = block.rows[0].cells
        value_row = block.rows[2].cells
        if not header or not value_row:
            continue
        if "trưởng bộ phận" not in normalize_for_match(header[0].text):
            continue
        value = strip_terminal(value_row[0].text)
        if value and "ký" not in normalize_for_match(value):
            return value
    return None


def _fill_ocr_line_fields(data: dict[str, object], text: str) -> None:
    label_patterns = {
        "employeeName": r"^Tôi\s+tên\s+là\s*:?\s*(.+)$",
        "jobTitle": r"^Ch.c\s+v.\s*:?\s*(.+)$",
        "department": r"^B.\s+ph.n\s*:?\s*(.+)$",
    }
    for line in text.splitlines():
        for field_name, pattern in label_patterns.items():
            if data.get(field_name) is not None:
                continue
            match = re.match(pattern, line.strip(), flags=re.IGNORECASE)
            if match:
                data[field_name] = strip_terminal(match.group(1))


def _fill_ocr_geometry_fields(
    data: dict[str, object],
    document: CanonicalDocument,
) -> None:
    lines = ocr_lines(document)
    boxes = [
        observation.source.bounding_box
        for observation in lines
        if observation.source.bounding_box is not None
    ]
    page_height = max((box.y1 for box in boxes), default=0.0)
    if page_height <= 0.0:
        return

    field_specs = {
        "employeeName": (("Tôi tên là", "TÃ´i tÃªn lÃ "), (0.16, 0.22)),
        "jobTitle": (("Chức vụ", "Ch.c v."), (0.19, 0.26)),
        "department": (("Bộ phận", "B. ph.n"), (0.21, 0.30)),
        "address": (("Địa chỉ", "Äá»‹a chá»‰"), (0.23, 0.31)),
        "phone": (("Điện thoại", "Äiá»‡n thoáº¡i"), (0.25, 0.34)),
    }
    for field_name, (labels, (lower, upper)) in field_specs.items():
        if data.get(field_name) is not None:
            continue
        candidates: list[tuple[float, str]] = []
        for observation in lines:
            box = observation.source.bounding_box
            if box is None or not lower <= ((box.y0 + box.y1) / 2) / page_height <= upper:
                continue
            value = ocr_line_value(observation.text, labels)
            if value:
                candidates.append((float(box.y0), value))
        if candidates:
            data[field_name] = candidates[0][1]

    for field_name, labels, (lower, upper) in (
        ("reason", ("Lý do xin nghỉ phép", "LÃ½ do xin nghá»‰ phÃ©p"), (0.30, 0.40)),
        (
            "handoverTasks",
            ("Các công việc được bàn giao", "CÃ¡c cÃ´ng viá»‡c Ä‘Æ°á»£c bÃ n giao"),
            (0.39, 0.49),
        ),
    ):
        if data.get(field_name) is not None and field_name != "reason":
            continue
        values: list[str] = []
        for observation in lines:
            box = observation.source.bounding_box
            if box is None or not lower <= ((box.y0 + box.y1) / 2) / page_height <= upper:
                continue
            value = ocr_line_value(observation.text, labels)
            if value:
                values.append(value)
        if values:
            candidate = strip_terminal(" ".join(values))
            if candidate and field_name == "reason":
                candidate = _extract_leave_reason(candidate)
            if candidate:
                # The geometry-labelled line is more specific than the broad
                # full-page fallback which can swallow the surrounding sentence.
                data[field_name] = candidate


def _extract_leave_reason(value: str | None) -> str | None:
    """Keep the reason clause after the fixed ``trong thời gian`` label."""
    if value is None:
        return None
    # Camera OCR may emit ``trong thi`` or ``trong thoi gian``. The suffix is
    # free text, therefore only the fixed sentence boundary is normalized.
    match = re.search(
        r"\btrong\s+th\S{0,8}(?:\s+gian)?\s+(.+)$",
        value,
        flags=re.IGNORECASE,
    )
    if match:
        value = match.group(1)
    return trim_ocr_commitment(value)


def _fill_roi_fields(data: dict[str, object], document: CanonicalDocument) -> None:
    labels = {
        "employeeName": ("Tôi tên là", "TÃ´i tÃªn lÃ "),
        "jobTitle": ("Chức vụ", "Ch.c v."),
        "department": ("Bộ phận", "B. ph.n"),
        "reason": ("Lý do xin nghỉ phép", "LÃ½ do xin nghá»‰ phÃ©p"),
        "handoverTasks": ("Các công việc được bàn giao", "CÃ¡c cÃ´ng viá»‡c Ä‘Æ°á»£c bÃ n giao"),
    }
    for evidence in ocr_roi_evidence(document):
        field_name = evidence.get("field")
        raw_value = evidence.get("text")
        if not isinstance(field_name, str) or not isinstance(raw_value, str):
            continue
        if data.get(field_name) is not None:
            continue
        value = ocr_line_value(raw_value, labels.get(field_name, ()))
        if value is None:
            value = strip_terminal(raw_value)
        if value:
            data[field_name] = (
                _extract_leave_reason(value)
                if field_name == "reason"
                else value
            )
