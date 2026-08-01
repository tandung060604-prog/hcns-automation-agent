"""Parser for the approved Vietnamese overtime-request DOCX template."""

from __future__ import annotations

import re

from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.domain.documents import SourceFormat
from hcns_agent.templates.common import (
    clock_time,
    document_text,
    extract_unique,
    iso_date,
    named_dates,
    normalize_for_ocr_match,
    number_value,
    ocr_line_value,
    ocr_lines,
    ocr_roi_evidence,
    repair_template_ocr_value,
    strip_terminal,
    trim_ocr_commitment,
)
from hcns_agent.templates.model import ParsedTemplate, TemplateDetection


class OvertimeRequestParser:
    version = "1.0.0"

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

        contract = re.search(
            r"Hợp\s+đồng\s+lao\s+động\s+số\s+(.+?)\s+ký\s+ngày\s+"
            r"(\d{1,2}/\d{1,2}/\d{4})",
            text,
            flags=re.IGNORECASE,
        )
        employment = re.search(
            r"thời\s+gian\s+làm\s+việc\s+(.+?)\.\s*Do\s+(.+?),\s*"
            r"tôi\s+đề\s+nghị",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        period = re.search(
            r"Thời\s+gian\s+đề\s+nghị\s*:\s*Từ\s+ngày\s+"
            r"(\d{1,2}/\d{1,2}/\d{4})\s+đến\s+hết\s+ngày\s+"
            r"(\d{1,2}/\d{1,2}/\d{4}).*?tăng\s+thêm\s+"
            r"(\d+(?:[.,]\d+)?)\s+giờ\s+mỗi\s+ngày,\s+từ\s+"
            r"(\d{1,2})\s+giờ(?:\s+(\d{1,2})\s+phút)?\s+đến\s+"
            r"(\d{1,2})\s+giờ(?:\s+(\d{1,2})\s+phút)?.*?"
            r"tổng\s+thời\s+gian\s+dự\s+kiến\s+là\s+"
            r"(\d+(?:[.,]\d+)?)\s+giờ",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        employee = re.search(
            r"Tôi\s+là\s*:\s*(.+?)\s*-\s*Chức\s+vụ\s*:\s*([^\n]+)",
            text,
            flags=re.IGNORECASE,
        )
        if document.source_format in {SourceFormat.IMAGE, SourceFormat.PDF_SCAN}:
            employee = employee or re.search(
                r"Tôi\s+là\s*:\s*(.+?)\s*-\s*Ch.c\s+v.\s*:\s*([^\n]+)",
                text,
                flags=re.IGNORECASE,
            )
            employment = employment or re.search(
                r"thi\s+gian\s+làm\s+vi.c\s+(.+?)\.\s*Do\s+(.+?),\s*"
                r"t[ôo]i\s+(?:đ|d).{0,4}ngh",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            period = period or re.search(
                r"Thi\s+gian\s+.{0,12}ngh\s*:\s*T.\s+ngày\s+"
                r"(\d{1,2}/\d{1,2}/\d{4}).*?ngày\s+"
                r"(\d{1,2}/\d{1,2}/\d{4}).*?tăng\s+thêm\s+"
                r"(\d+(?:[.,]\d+)?)\s+gi.{0,3}mi\s+ngày.*?t.\s+"
                r"(\d{1,2})\s+gi(?:\s+(\d{1,2})\s+phút)?.*?"
                r"(?:đ|d).{0,3}\s+(\d{1,2})\s+gi"
                r"(?:\s+(\d{1,2})\s+phút)?.*?"
                r"t.ng\s+thi\s+gian\s+d.\s+ki.n\s+là\s+"
                r"(\d+(?:[.,]\d+)?)\s+gi",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
        request_dates = named_dates(text)

        data: dict[str, object] = {
            "documentId": document.document_id,
            "documentType": detection.definition.document_type.value,
            "templateId": detection.definition.template_id,
            "templateVersion": detection.definition.version,
            "documentTitle": "ĐƠN XIN TĂNG CA",
            "formNumber": None,
            "organization": field(
                "organization",
                r"Kính\s+gửi\s*:\s*Ban\s+Giám\s+đốc\s+([^\n.]+)",
            ),
            "employeeName": strip_terminal(employee.group(1)) if employee else None,
            "employeeId": None,
            "jobTitle": strip_terminal(employee.group(2)) if employee else None,
            "department": None,
            "requestDate": request_dates[0] if request_dates else None,
            "laborContractNumber": strip_terminal(contract.group(1)) if contract else None,
            "laborContractDate": iso_date(contract.group(2)) if contract else None,
            "standardWorkSchedule": strip_terminal(employment.group(1)) if employment else None,
            "reason": strip_terminal(employment.group(2)) if employment else None,
            "startDate": iso_date(period.group(1)) if period else None,
            "endDate": iso_date(period.group(2)) if period else None,
            "overtimeHoursPerDay": number_value(period.group(3)) if period else None,
            "overtimeStartTime": clock_time(period.group(4), period.group(5)) if period else None,
            "overtimeEndTime": clock_time(period.group(6), period.group(7)) if period else None,
            "totalOvertimeHours": number_value(period.group(8)) if period else None,
            "workContent": field(
                "workContent",
                r"Nội\s+dung\s+công\s+việc\s*:\s*([\s\S]+?)"
                r"(?:\.\s*Tôi\s+cam\s+kết|\nTôi\s+cam\s+kết|$)",
            ),
            "sourceFile": document.source.filename,
        }
        if (
            document.source_format in {SourceFormat.IMAGE, SourceFormat.PDF_SCAN}
            and data["workContent"] is None
        ):
            work_content = re.search(
                r"N.i\s+dung\s+công\s+vi.c\s*:?\s*([\s\S]+?)"
                r"(?:\.\s*Tôi\s+cam|\nTôi\s+cam|$)",
                text,
                flags=re.IGNORECASE,
            )
            if work_content:
                data["workContent"] = strip_terminal(work_content.group(1))
        if document.source_format in {SourceFormat.IMAGE, SourceFormat.PDF_SCAN}:
            _fill_ocr_geometry_fields(data, document)
            _fill_roi_fields(data, document)
            data["jobTitle"] = repair_template_ocr_value(data.get("jobTitle"), "jobTitle")
            data["department"] = repair_template_ocr_value(
                data.get("department"), "department"
            )
            slash_dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", text)
            if data["startDate"] is None and len(slash_dates) >= 3:
                data["startDate"] = iso_date(slash_dates[1])
                data["endDate"] = iso_date(slash_dates[2])
            _fill_numeric_ocr_fields(data, text)
            signature = re.search(
                r"NGƯỜI\s+LÀM\s+ĐƠN\s*\n"
                r"(?:\([^\n]*\)\s*\n)?([^\n]+)",
                text,
                flags=re.IGNORECASE,
            )
            if signature:
                data["employeeName"] = strip_terminal(signature.group(1))
        return ParsedTemplate(data=data, conflicting_fields=tuple(sorted(conflicts)))


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
    reason_values: list[str] = []
    reason_started = False
    for observation in lines:
        box = observation.source.bounding_box
        if box is None:
            continue
        ratio = ((box.y0 + box.y1) / 2) / page_height
        if not 0.21 <= ratio <= 0.30:
            continue
        text = observation.text
        value = ocr_line_value(
            text,
            ("Tôi là", "TÃ´i lÃ "),
            stop_labels=("Chức vụ", "Ch.c v."),
        )
        if value:
            data["employeeName"] = strip_terminal(value.split("-", 1)[0])
        job_value = ocr_line_value(text, ("Chức vụ", "Ch.c v."))
        if job_value:
            if ":" in text:
                job_value = strip_terminal(text.rsplit(":", 1)[1])
            data["jobTitle"] = strip_terminal(job_value)
        if "-" in text:
            job_text = text.split("-", 1)[1]
            value = ocr_line_value(job_text, ("Chức vụ", "Ch.c v."))
            if value:
                data["jobTitle"] = strip_terminal(value)
    for observation in lines:
        box = observation.source.bounding_box
        if box is None:
            continue
        ratio = ((box.y0 + box.y1) / 2) / page_height
        if not 0.25 <= ratio <= 0.39:
            continue
        value = observation.text
        if not reason_started:
            reason_match = re.search(r"\bD[oô]\b\s+(.+)$", value)
            if reason_match is None:
                continue
            reason_started = True
            value = reason_match.group(1)
        request_marker = re.search(
            r"[,;]?\s*(?:tôi|toi|ti)\s+[dđ]\S{0,5}\s+ngh",
            value,
            flags=re.IGNORECASE,
        )
        if request_marker:
            value = value[: request_marker.start()]
            reason_values.append(value)
            break
        reason_values.append(value)
    if reason_values:
        data["reason"] = trim_ocr_commitment(" ".join(reason_values))
    content_values: list[str] = []
    content_started = False
    for observation in lines:
        box = observation.source.bounding_box
        if box is None:
            continue
        ratio = ((box.y0 + box.y1) / 2) / page_height
        if not 0.40 <= ratio <= 0.58:
            continue
        value = ocr_line_value(
            observation.text,
            ("Nội dung công việc", "Ná»™i dung cÃ´ng viá»‡c"),
        )
        if value:
            content_started = True
            content_values.append(value)
        elif content_started:
            if re.search(r"cam\s+k\w{0,4}t", observation.text, re.IGNORECASE):
                break
            content_values.append(observation.text)
    if content_values:
        data["workContent"] = trim_ocr_commitment(" ".join(content_values))


def _fill_numeric_ocr_fields(data: dict[str, object], text: str) -> None:
    """Recover the fixed numeric block without relying on Vietnamese marks."""
    normalized = normalize_for_ocr_match(text)
    overtime_marker = re.search(
        r"t.?ng\s+them\s+\d+(?:[.,]\d+)?\s+gi\w*",
        normalized,
        flags=re.IGNORECASE,
    )
    time_text = normalized[overtime_marker.end() :] if overtime_marker else normalized
    hour_pairs = re.findall(
        r"\b(\d{1,2})\s+gi\w*\s+(\d{1,2})\s+phut\b",
        time_text,
        flags=re.IGNORECASE,
    )
    per_day = re.search(
        r"t.?ng\s+them\s+(\d+(?:[.,]\d+)?)\s+gi\w*",
        normalized,
        flags=re.IGNORECASE,
    )
    total = re.search(
        r"t.?ng\s+thi\s+gian.*?\b(\d+(?:[.,]\d+)?)\s+gi\w*",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if data.get("overtimeHoursPerDay") is None and per_day:
        data["overtimeHoursPerDay"] = number_value(per_day.group(1))
    if len(hour_pairs) >= 2:
        if data.get("overtimeStartTime") is None:
            data["overtimeStartTime"] = clock_time(*hour_pairs[0])
        if data.get("overtimeEndTime") is None:
            data["overtimeEndTime"] = clock_time(*hour_pairs[1])
    if data.get("totalOvertimeHours") is None and total:
        data["totalOvertimeHours"] = number_value(total.group(1))


def _fill_roi_fields(data: dict[str, object], document: CanonicalDocument) -> None:
    labels = {
        "employeeName": ("Tôi là", "TÃ´i lÃ "),
        "jobTitle": ("Chức vụ", "Ch.c v."),
        "reason": ("Lý do", "Do"),
        "workContent": ("Nội dung công việc", "Ná»™i dung cÃ´ng viá»‡c"),
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
        if field_name == "employeeName" and value:
            value = strip_terminal(value.split("-", 1)[0])
        if value:
            data[field_name] = value
