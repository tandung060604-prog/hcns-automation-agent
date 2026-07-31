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
    number_value,
    strip_terminal,
)
from hcns_agent.templates.model import ParsedTemplate, TemplateDetection


class OvertimeRequestParser:
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
            slash_dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", text)
            if data["startDate"] is None and len(slash_dates) >= 3:
                data["startDate"] = iso_date(slash_dates[1])
                data["endDate"] = iso_date(slash_dates[2])
            if data["overtimeHoursPerDay"] is None:
                numeric_period = re.search(
                    r"tăng\s+thêm\s+(\d+(?:[.,]\d+)?)\s+gi.{0,3}m.\s+ngày"
                    r"\D{0,12}(\d{1,2})\s+gi\s+(\d{1,2})\s+phút"
                    r"\D{0,8}(\d{1,2})\s+gi\s+(\d{1,2})\s+phút"
                    r".*?(\d+(?:[.,]\d+)?)\s+gi",
                    text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if numeric_period:
                    data["overtimeHoursPerDay"] = number_value(
                        numeric_period.group(1)
                    )
                    data["overtimeStartTime"] = clock_time(
                        numeric_period.group(2),
                        numeric_period.group(3),
                    )
                    data["overtimeEndTime"] = clock_time(
                        numeric_period.group(4),
                        numeric_period.group(5),
                    )
                    data["totalOvertimeHours"] = number_value(
                        numeric_period.group(6)
                    )
            signature = re.search(
                r"NGƯỜI\s+LÀM\s+ĐƠN\s*\n"
                r"(?:\([^\n]*\)\s*\n)?([^\n]+)",
                text,
                flags=re.IGNORECASE,
            )
            if signature:
                data["employeeName"] = strip_terminal(signature.group(1))
        return ParsedTemplate(data=data, conflicting_fields=tuple(sorted(conflicts)))
