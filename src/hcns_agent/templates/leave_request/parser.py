"""Parser for the approved Vietnamese leave-request DOCX template."""

from __future__ import annotations

import re

from hcns_agent.domain.canonical import CanonicalDocument, Table
from hcns_agent.templates.common import (
    document_text,
    extract_unique,
    iso_date,
    named_dates,
    normalize_for_match,
    number_value,
    strip_terminal,
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
