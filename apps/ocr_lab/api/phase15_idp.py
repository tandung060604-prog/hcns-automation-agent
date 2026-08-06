#!/usr/bin/env python3
"""Phase 15 unified IDP for the five Vietnamese HR document families."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    from .phase12_idp import (
        _blocks,
        _box_bounds,
        _field,
        _labeled,
        _regex_field,
        _schema_output,
        accent_key,
        classify_hr_document,
    )
except ImportError:  # Direct script execution used by the local OCR server.
    from phase12_idp import (
        _blocks,
        _box_bounds,
        _field,
        _labeled,
        _regex_field,
        _schema_output,
        accent_key,
        classify_hr_document,
    )


DOCUMENT_FAMILIES = (
    "CV",
    "ADMINISTRATIVE_REQUEST",
    "CONTRACT_DECISION",
    "DEGREE_CERTIFICATE",
    "EMPLOYEE_FORM_TABLE",
)

IDP_PARSER_VERSION = "phase17-structured-hr-parser/2.0.0"

DOCUMENT_FAMILY_BY_TYPE = {
    "CV": "CV",
    "LEAVE_REQUEST": "ADMINISTRATIVE_REQUEST",
    "OVERTIME_REQUEST": "ADMINISTRATIVE_REQUEST",
    "BUSINESS_TRIP_REQUEST": "ADMINISTRATIVE_REQUEST",
    "EQUIPMENT_REQUEST": "ADMINISTRATIVE_REQUEST",
    "EMPLOYEE_INFO_UPDATE": "ADMINISTRATIVE_REQUEST",
    "EMPLOYMENT_CONTRACT": "CONTRACT_DECISION",
    "PROBATION_AGREEMENT": "CONTRACT_DECISION",
    "HR_DECISION": "CONTRACT_DECISION",
    "DEGREE_CERTIFICATE": "DEGREE_CERTIFICATE",
    "CERTIFICATE": "DEGREE_CERTIFICATE",
    "EMPLOYEE_INFORMATION_FORM": "EMPLOYEE_FORM_TABLE",
    "ONBOARDING_CHECKLIST": "EMPLOYEE_FORM_TABLE",
    "EMPLOYEE_MASTER_LIST": "EMPLOYEE_FORM_TABLE",
    "TRAINING_ATTENDANCE": "EMPLOYEE_FORM_TABLE",
}

WORKFLOW_TYPE_BY_DOCUMENT_TYPE = {
    "IDENTITY_DOCUMENT": "IDENTITY_DOCUMENT",
    "CV": "CV",
    "LEAVE_REQUEST": "LEAVE_REQUEST",
    "OVERTIME_REQUEST": "OVERTIME_REQUEST",
    "EMPLOYMENT_CONTRACT": "EMPLOYMENT_CONTRACT",
    "PROBATION_AGREEMENT": "EMPLOYMENT_CONTRACT",
    "HR_DECISION": "HR_DECISION",
    "DEGREE_CERTIFICATE": "DEGREE",
    "CERTIFICATE": "CERTIFICATE",
}

BUSINESS_SCHEMA_BY_FAMILY = {
    "CV": "schemas/hr_document_families/cv.schema.json",
    "ADMINISTRATIVE_REQUEST": (
        "schemas/hr_document_families/administrative_request.schema.json"
    ),
    "CONTRACT_DECISION": (
        "schemas/hr_document_families/contract_decision.schema.json"
    ),
    "DEGREE_CERTIFICATE": (
        "schemas/hr_document_families/degree_certificate.schema.json"
    ),
    "EMPLOYEE_FORM_TABLE": (
        "schemas/hr_document_families/employee_form_table.schema.json"
    ),
    "IDENTITY_DOCUMENT": "schemas/business_document.schema.json",
    "OTHER_HR_DOCUMENT": "schemas/business_document.schema.json",
}

BUSINESS_SCHEMA_BY_TYPE: dict[str, str] = {}

FAMILY_FIELD_SCHEMAS: dict[str, tuple[str, ...]] = {
    "CV": (
        "fullName",
        "headline",
        "email",
        "phoneNumber",
        "address",
        "education",
        "experience",
        "skills",
    ),
    "ADMINISTRATIVE_REQUEST": (
        "documentTitle",
        "requestNumber",
        "employeeName",
        "employeeId",
        "department",
        "jobTitle",
        "reason",
        "startDate",
        "endDate",
    ),
    "CONTRACT_DECISION": (
        "documentNumber",
        "employeeName",
        "employeeId",
        "jobTitle",
        "action",
        "salary",
        "startDate",
        "endDate",
        "effectiveDate",
    ),
    "DEGREE_CERTIFICATE": (
        "recipientName",
        "credentialType",
        "credentialId",
        "issuingOrganization",
        "fieldOfStudy",
        "degreeLevel",
        "classification",
        "issueDate",
    ),
    "EMPLOYEE_FORM_TABLE": (
        "formNumber",
        "employeeName",
        "employeeId",
        "dateOfBirth",
        "gender",
        "department",
        "jobTitle",
        "email",
        "phoneNumber",
        "address",
        "organization",
        "joinDate",
    ),
}

SENSITIVE_FIELDS = {
    "fullName",
    "employeeName",
    "employeeId",
    "dateOfBirth",
    "gender",
    "email",
    "phoneNumber",
    "address",
    "salary",
    "recipientName",
}

_TYPE_RULES: dict[str, tuple[tuple[str, float], ...]] = {
    "CV": (
        ("curriculum vitae", 6.0),
        ("muc tieu nghe nghiep", 3.0),
        ("kinh nghiem lam viec", 3.0),
        ("hoc van", 1.5),
        ("ky nang", 1.5),
    ),
    "LEAVE_REQUEST": (
        ("don de nghi nghi phep", 7.0),
        ("don xin nghi phep", 7.0),
        ("thoi gian nghi", 2.0),
    ),
    "OVERTIME_REQUEST": (
        ("phieu dang ky lam them gio", 7.0),
        ("don dang ky lam them gio", 7.0),
        ("gio tang ca", 2.0),
    ),
    "BUSINESS_TRIP_REQUEST": (
        ("giay de nghi cong tac", 7.0),
        ("don de nghi cong tac", 7.0),
        ("dia diem cong tac", 2.0),
    ),
    "EQUIPMENT_REQUEST": (
        ("phieu de nghi cap thiet bi", 7.0),
        ("de nghi cap thiet bi lam viec", 6.0),
        ("ten thiet bi", 2.0),
    ),
    "EMPLOYEE_INFO_UPDATE": (
        ("phieu de nghi cap nhat thong tin nhan su", 7.0),
        ("thong tin de nghi thay doi", 2.0),
    ),
    "EMPLOYMENT_CONTRACT": (
        ("hop dong lao dong", 7.0),
        ("hop dong", 2.5),
        ("nguoi lao dong", 2.0),
        ("muc luong", 2.0),
    ),
    "PROBATION_AGREEMENT": (
        ("hop dong thu viec", 7.0),
        ("thoi gian thu viec", 2.0),
    ),
    "HR_DECISION": (
        ("quyet dinh bo nhiem", 7.0),
        ("quyet dinh dieu chuyen nhan su", 7.0),
        ("quyet dinh dieu chinh tien luong", 7.0),
        ("quyet dinh nhan su", 6.0),
    ),
    "DEGREE_CERTIFICATE": (
        ("bang tot nghiep", 7.0),
        ("bang cu nhan", 7.0),
        ("chung chi", 7.0),
        ("certificate", 5.0),
        ("certification", 5.0),
        ("credential id", 3.0),
        ("so hieu van bang", 2.0),
        ("ielts", 7.0),
        ("test report form", 6.0),
    ),
    "EMPLOYEE_INFORMATION_FORM": (
        ("phieu thong tin nhan vien", 7.0),
        ("thong tin nhan vien", 2.0),
    ),
    "ONBOARDING_CHECKLIST": (
        ("checklist tiep nhan nhan vien moi", 7.0),
        ("checklist tiep nhan", 7.0),
        ("danh sach tiep nhan nhan vien moi", 6.0),
    ),
    "EMPLOYEE_MASTER_LIST": (
        ("danh sach nhan su", 7.0),
        ("danh sach nhan vien", 6.0),
    ),
    "TRAINING_ATTENDANCE": (
        ("danh sach tham du va ket qua dao tao", 7.0),
        ("danh sach tham du dao tao", 7.0),
        ("ket qua dao tao", 2.0),
    ),
}

_SECTION_HEADINGS = {
    "muc tieu nghe nghiep",
    "hoc van",
    "kinh nghiem",
    "kinh nghiem lam viec",
    "ky nang",
    "chung chi",
    "du an",
    "so thich",
    "nguoi tham chieu",
}


def classify_phase15_document(
    canonical: dict[str, Any],
    existing_route: str | None = None,
) -> dict[str, Any]:
    """Classify a canonical document into subtype and one of five HR families."""
    base = classify_hr_document(canonical, existing_route)
    if base.get("documentType") == "IDENTITY_DOCUMENT":
        return {
            **base,
            "documentFamily": "IDENTITY_DOCUMENT",
            "documentSubtype": "IDENTITY_DOCUMENT",
            "workflowDocumentType": "IDENTITY_DOCUMENT",
            "schemaRef": BUSINESS_SCHEMA_BY_FAMILY["IDENTITY_DOCUMENT"],
        }

    text = accent_key(canonical.get("plainText", ""))
    leading = [accent_key(block.get("text")) for block in _blocks(canonical)[:8]]
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    for document_type, rules in _TYPE_RULES.items():
        matched: list[str] = []
        score = 0.0
        for marker, weight in rules:
            if marker not in text:
                continue
            title_match = any(
                item == marker or item.startswith(f"{marker} ")
                for item in leading
            )
            effective_weight = (
                weight
                if weight < 5.0 or title_match
                else weight * 0.2
            )
            score += effective_weight + (1.0 if title_match else 0.0)
            matched.append(marker)
        scores[document_type] = score
        evidence[document_type] = matched

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    selected, best_score = ranked[0] if ranked else ("GENERIC_DOCUMENT", 0.0)
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if best_score < 2.5:
        selected = str(base.get("documentType") or "GENERIC_DOCUMENT")
        confidence = float(base.get("confidence") or 0.0)
        selected_evidence = list(base.get("evidence") or [])
    else:
        margin = max(0.0, best_score - second_score)
        confidence = min(0.99, 0.60 + best_score * 0.035 + margin * 0.025)
        selected_evidence = evidence[selected]

    family = DOCUMENT_FAMILY_BY_TYPE.get(selected, "OTHER_HR_DOCUMENT")
    workflow_type = WORKFLOW_TYPE_BY_DOCUMENT_TYPE.get(
        selected,
        "OTHER_HR_DOCUMENT",
    )
    return {
        "documentType": selected,
        "documentSubtype": selected,
        "documentFamily": family,
        "workflowDocumentType": workflow_type,
        "confidence": round(confidence, 6),
        "status": "accepted" if confidence >= 0.80 else "needs_review",
        "evidence": selected_evidence[:8],
        "scores": {
            document_type: round(score, 3)
            for document_type, score in scores.items()
        },
        "supportedDocumentFamilies": list(DOCUMENT_FAMILIES),
        "schemaRef": BUSINESS_SCHEMA_BY_TYPE.get(
            selected,
            BUSINESS_SCHEMA_BY_FAMILY[family],
        ),
    }


def _field_or_not_found(
    canonical: dict[str, Any],
    labels: tuple[str, ...],
) -> dict[str, Any]:
    return _labeled(canonical, labels)


def _email_field(canonical: dict[str, Any]) -> dict[str, Any]:
    return _regex_field(
        canonical,
        (r"\b([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\b",),
        validator=lambda value: bool(
            re.fullmatch(
                r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
                str(value),
                re.IGNORECASE,
            )
        ),
        method="email_pattern",
    )


def _phone_field(canonical: dict[str, Any]) -> dict[str, Any]:
    return _regex_field(
        canonical,
        (r"(?:\+?84|0)([\s.-]?\d){8,10}",),
        group=0,
        validator=lambda value: 9 <= len(re.sub(r"\D", "", str(value))) <= 12,
        method="phone_pattern",
    )


def _first_matching_block(
    canonical: dict[str, Any],
    predicate: Any,
    *,
    method: str,
) -> dict[str, Any]:
    for block in _blocks(canonical):
        text = str(block.get("text") or "").strip()
        if text and predicate(text):
            return _field(text, block, method=method)
    return _field(None, None, method=method)


def _bounded_labeled(
    canonical: dict[str, Any],
    labels: tuple[str, ...],
    *,
    stop_labels: tuple[str, ...] = (),
    data_type: str = "string",
    normalizer: Any = None,
    validator: Any = None,
    method: str = "bounded_label_value",
) -> dict[str, Any]:
    """Read one scalar label without swallowing following labelled fields."""

    blocks = _blocks(canonical)
    ordered_labels = sorted(labels, key=len, reverse=True)
    label_pattern = "|".join(re.escape(label) for label in ordered_labels)
    pattern = re.compile(
        rf"(?:^|\s+[|;/]\s*)(?:{label_pattern})\s*(?:[:\-]\s*)?(.*)$",
        re.IGNORECASE,
    )
    ordered_stops = sorted(
        set(labels + stop_labels),
        key=len,
        reverse=True,
    )
    stop_pattern = "|".join(re.escape(label) for label in ordered_stops)

    def cut_at_next_label(value: str) -> str:
        if not stop_pattern:
            return value
        boundary = re.search(
            rf"(?:\s+[|;/]\s+|\s{{2,}})"
            rf"(?=(?:{stop_pattern})\s*(?:[:\-]|$))",
            value,
            re.IGNORECASE,
        )
        return value[: boundary.start()] if boundary else value

    def starts_with_label(value: str) -> bool:
        return bool(
            stop_pattern
            and re.match(
                rf"^(?:{stop_pattern})\s*(?:[:\-]|$)",
                value,
                re.IGNORECASE,
            )
        )

    for index, block in enumerate(blocks):
        text = str(block.get("text") or "").strip()
        match = pattern.search(text)
        if not match:
            continue
        value = cut_at_next_label(match.group(1)).strip(" :|-")
        evidence = block
        if not value:
            for candidate in blocks[index + 1 : index + 3]:
                candidate_text = str(candidate.get("text") or "").strip()
                if not candidate_text or starts_with_label(candidate_text):
                    break
                if len(candidate_text) > 180:
                    break
                value = cut_at_next_label(candidate_text).strip(" :|-")
                evidence = candidate
                break
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
            evidence,
            data_type=data_type,
            normalized_value=normalized,
            valid=valid,
            method=method,
        )
    return _field(None, None, data_type=data_type, method=method)


def _field_after_marker(
    canonical: dict[str, Any],
    markers: tuple[str, ...],
    *,
    predicate: Any = None,
    method: str,
) -> dict[str, Any]:
    blocks = _blocks(canonical)
    normalized_markers = tuple(accent_key(marker) for marker in markers)
    for index, block in enumerate(blocks):
        key = accent_key(block.get("text"))
        if not any(marker in key for marker in normalized_markers):
            continue
        for candidate in blocks[index + 1 : index + 4]:
            value = str(candidate.get("text") or "").strip()
            if not value:
                continue
            if predicate is None or predicate(value):
                return _field(value, candidate, method=method)
    return _field(None, None, method=method)


def _likely_person_name(value: str) -> bool:
    key = accent_key(value)
    words = value.split()
    letters = [character for character in value if character.isalpha()]
    excluded = (
        "chung nhan",
        "hoan thanh",
        "certificate",
        "certification",
        "truong dai hoc",
        "university",
        "cong ty",
    )
    return (
        2 <= len(words) <= 7
        and len(letters) >= 5
        and not any(character.isdigit() for character in value)
        and not any(marker in key for marker in excluded)
    )


def _document_title(canonical: dict[str, Any]) -> dict[str, Any]:
    title_markers = tuple(
        marker
        for rules in _TYPE_RULES.values()
        for marker, weight in rules
        if weight >= 5.0
    )
    return _first_matching_block(
        canonical,
        lambda value: any(
            marker in accent_key(value) for marker in title_markers
        ),
        method="document_title_marker",
    )


def _section_field(
    canonical: dict[str, Any],
    headings: tuple[str, ...],
) -> dict[str, Any]:
    blocks = _blocks(canonical)
    normalized_headings = tuple(accent_key(item) for item in headings)
    for index, block in enumerate(blocks):
        key = accent_key(block.get("text"))
        if not any(
            key == heading or key.startswith(f"{heading} ")
            for heading in normalized_headings
        ):
            continue
        values: list[str] = []
        evidence = None
        for candidate in blocks[index + 1 :]:
            candidate_key = accent_key(candidate.get("text"))
            if _is_section_heading(candidate_key):
                break
            if candidate.get("text"):
                evidence = evidence or candidate
                values.append(str(candidate["text"]).strip())
        if values:
            return _field(
                "\n".join(values),
                evidence,
                method="section_after_heading",
            )
    return _field(None, None, method="section_after_heading")


def _is_section_heading(value: str) -> bool:
    key = accent_key(value).strip()
    return key in _SECTION_HEADINGS or any(
        key.startswith(f"{heading} ") or key.startswith(f"{heading}&")
        for heading in _SECTION_HEADINGS
    )


def _cv_name(canonical: dict[str, Any]) -> dict[str, Any]:
    labeled = _labeled(canonical, ("Họ và tên", "Họ tên", "Full name"))
    if labeled["value"] is not None:
        return labeled

    excluded = {
        "curriculum vitae",
        "nhan vien",
        "chuyen vien",
        "muc tieu nghe nghiep",
        "hoc van",
        "kinh nghiem lam viec",
    }

    def likely_name(value: str) -> bool:
        key = accent_key(value)
        words = value.split()
        letters = [character for character in value if character.isalpha()]
        uppercase = [character for character in letters if character.isupper()]
        return (
            2 <= len(words) <= 6
            and len(letters) >= 6
            and len(uppercase) / max(1, len(letters)) >= 0.18
            and not _is_section_heading(key)
            and not any(marker in key for marker in excluded)
            and "@" not in value
        )

    for block in _blocks(canonical)[:12]:
        value = str(block.get("text") or "").strip()
        split = re.split(r"(?<=[a-zà-ỹ])(?=[A-ZĐ])", value, maxsplit=1)
        if len(split) == 2 and likely_name(split[0].strip()):
            return _field(split[0].strip(), block, method="cv_top_name_candidate")
        if likely_name(value):
            return _field(value, block, method="cv_top_name_candidate")
    return _field(None, None, method="cv_top_name_candidate")


def parse_cv(canonical: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "fullName": _cv_name(canonical),
        "headline": _field_or_not_found(
            canonical,
            ("Vị trí ứng tuyển", "Chức danh", "Vị trí"),
        ),
        "email": _email_field(canonical),
        "phoneNumber": _phone_field(canonical),
        "address": _field_or_not_found(canonical, ("Địa chỉ",)),
        "education": _section_field(canonical, ("Học vấn",)),
        "experience": _section_field(
            canonical,
            ("Kinh nghiệm làm việc", "Kinh nghiệm"),
        ),
        "skills": _section_field(canonical, ("Kỹ năng",)),
    }
    return _schema_output("CV", fields)


def parse_administrative_request(
    canonical: dict[str, Any],
    document_type: str,
) -> dict[str, Any]:
    start_date = _labeled(
        canonical,
        ("Từ ngày", "Ngày bắt đầu", "Ngày đi", "Thời gian bắt đầu"),
    )
    if start_date["value"] is None:
        start_date = _regex_field(
            canonical,
            (
                r"(?:từ ngày|ngày đi)\s*[:\-]?\s*"
                r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            ),
            method="administrative_start_date_pattern",
        )
    end_date = _labeled(
        canonical,
        ("Đến ngày", "Ngày kết thúc", "Ngày về", "Thời gian kết thúc"),
    )
    if end_date["value"] is None:
        end_date = _regex_field(
            canonical,
            (
                r"(?:đến ngày|ngày về)\s*[:\-]?\s*"
                r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            ),
            method="administrative_end_date_pattern",
        )
    fields = {
        "documentTitle": _document_title(canonical),
        "requestNumber": _labeled(
            canonical,
            ("Số", "Số phiếu", "Mã phiếu"),
        ),
        "employeeName": _labeled(
            canonical,
            ("Họ và tên", "Họ tên", "Tên nhân viên", "Người đề nghị"),
        ),
        "employeeId": _labeled(
            canonical,
            ("Mã nhân viên", "Mã NV", "MSNV"),
        ),
        "department": _labeled(canonical, ("Phòng ban", "Bộ phận")),
        "jobTitle": _labeled(canonical, ("Chức danh", "Chức vụ", "Vị trí")),
        "reason": _labeled(
            canonical,
            ("Lý do", "Mục đích", "Nội dung đề nghị"),
        ),
        "startDate": start_date,
        "endDate": end_date,
    }
    return _schema_output(document_type, fields)


_CREDENTIAL_TYPE_KEYS = (
    "bang cu nhan",
    "bang ky su",
    "bang thac si",
    "bang tien si",
    "bang tot nghiep",
    "chung chi",
    "professional certificate",
    "certificate of course completion",
    "certification",
    "certificate",
)

_CREDENTIAL_METADATA_LABELS = (
    "Trình độ",
    "Bậc",
    "Degree level",
    "Ngành",
    "Ngành đào tạo",
    "Chuyên ngành",
    "Field",
    "Xếp loại",
    "Loại tốt nghiệp",
    "Classification",
    "Ngày cấp",
    "Cấp ngày",
    "Issue date",
    "Issued",
    "Completed",
    "Số hiệu/Mã chứng nhận",
    "Số hiệu văn bằng",
    "Số vào sổ cấp bằng",
    "Mã chứng chỉ",
    "Credential ID",
    "Learner ID",
)


def _credential_type(canonical: dict[str, Any]) -> dict[str, Any]:
    def is_credential_type(value: str) -> bool:
        key = accent_key(value)
        return any(
            key == marker or key.startswith(f"{marker} ")
            for marker in _CREDENTIAL_TYPE_KEYS
        )

    return _first_matching_block(
        canonical,
        is_credential_type,
        method="credential_type_heading",
    )


def _credential_issuer(canonical: dict[str, Any]) -> dict[str, Any]:
    blocks = _blocks(canonical)
    heading_index = len(blocks)
    for index, block in enumerate(blocks):
        key = accent_key(block.get("text"))
        if any(
            key == marker or key.startswith(f"{marker} ")
            for marker in _CREDENTIAL_TYPE_KEYS
        ):
            heading_index = index
            break

    excluded = (
        "cong hoa xa hoi chu nghia viet nam",
        "doc lap tu do hanh phuc",
        "ministry of",
        "tran trong chung nhan",
    )
    for block in blocks[:heading_index]:
        value = str(block.get("text") or "").strip()
        key = accent_key(value)
        letters = [character for character in value if character.isalpha()]
        if (
            1 <= len(value.split()) <= 12
            and len(letters) >= 3
            and not any(marker in key for marker in excluded)
        ):
            return _field(value, block, method="credential_leading_issuer")
    return _field(None, None, method="credential_leading_issuer")


def parse_degree_certificate(canonical: dict[str, Any]) -> dict[str, Any]:
    recipient = _bounded_labeled(
        canonical,
        ("Cấp cho", "Họ và tên", "Người được cấp", "Awarded to"),
        stop_labels=_CREDENTIAL_METADATA_LABELS,
    )
    if recipient["value"] is None:
        recipient = _field_after_marker(
            canonical,
            (
                "Trân trọng chứng nhận",
                "This certifies that",
                "Awarded to",
            ),
            predicate=_likely_person_name,
            method="recipient_after_credential_marker",
        )

    program = _field_after_marker(
        canonical,
        (
            "đã hoàn thành và đáp ứng yêu cầu của",
            "đã hoàn thành",
            "has successfully completed",
            "completed the requirements of",
        ),
        method="program_after_completion_marker",
    )
    labeled_field = _bounded_labeled(
        canonical,
        ("Ngành", "Ngành đào tạo", "Chuyên ngành", "Field"),
        stop_labels=_CREDENTIAL_METADATA_LABELS,
    )
    if labeled_field["value"] is not None:
        program = labeled_field

    fields = {
        "recipientName": recipient,
        "credentialType": _credential_type(canonical),
        "credentialId": _bounded_labeled(
            canonical,
            (
                "Số hiệu/Mã chứng nhận",
                "Số hiệu văn bằng",
                "Số vào sổ cấp bằng",
                "Mã chứng chỉ",
                "Credential ID",
                "Learner ID",
            ),
            stop_labels=_CREDENTIAL_METADATA_LABELS,
        ),
        "issuingOrganization": _credential_issuer(canonical),
        "fieldOfStudy": program,
        "degreeLevel": _bounded_labeled(
            canonical,
            ("Trình độ", "Bậc", "Degree level"),
            stop_labels=_CREDENTIAL_METADATA_LABELS,
        ),
        "classification": _bounded_labeled(
            canonical,
            ("Xếp loại", "Loại tốt nghiệp", "Classification"),
            stop_labels=_CREDENTIAL_METADATA_LABELS,
        ),
        "issueDate": _bounded_labeled(
            canonical,
            ("Ngày cấp", "Cấp ngày", "Issue date", "Issued", "Completed"),
            stop_labels=_CREDENTIAL_METADATA_LABELS,
        ),
    }
    return _schema_output("DEGREE_CERTIFICATE", fields)


_TABLE_HEADER_MARKERS: dict[str, tuple[str, ...]] = {
    "ONBOARDING_CHECKLIST": (
        "stt",
        "hang muc",
        "phu trach",
        "han hoan thanh",
        "trang thai",
        "ghi chu",
    ),
    "EMPLOYEE_MASTER_LIST": (
        "stt",
        "ma nv",
        "ho va ten",
        "bo phan",
        "chuc danh",
        "ngay vao",
        "loai hd",
        "trang thai",
    ),
    "TRAINING_ATTENDANCE": (
        "stt",
        "ma nv",
        "ho va ten",
        "bo phan",
        "co mat",
        "diem",
        "ket qua",
        "ky nhan",
    ),
}

_TABLE_STOP_MARKERS = (
    "tong cong",
    "nguoi lap",
    "nguoi phe duyet",
    "xac nhan",
    "ghi chu cuoi",
)


def _coordinate_rows(
    canonical: dict[str, Any],
) -> list[tuple[float, list[dict[str, Any]]]]:
    blocks = [
        block
        for page in canonical.get("pages", [])
        for block in page.get("ocrBlocks", [])
        if _box_bounds((block.get("evidence") or {}).get("bbox"))
    ]
    heights = [
        bounds[3] - bounds[1]
        for block in blocks
        for bounds in [_box_bounds((block.get("evidence") or {}).get("bbox"))]
        if bounds
    ]
    median_height = (
        sorted(heights)[len(heights) // 2] if heights else 16.0
    )
    tolerance = max(7.0, median_height * 0.48)
    rows: list[tuple[float, list[dict[str, Any]]]] = []
    for block in sorted(
        blocks,
        key=lambda item: (
            _box_bounds((item.get("evidence") or {}).get("bbox"))[1],
            _box_bounds((item.get("evidence") or {}).get("bbox"))[0],
        ),
    ):
        bounds = _box_bounds((block.get("evidence") or {}).get("bbox"))
        center_y = (bounds[1] + bounds[3]) / 2
        target_index = min(
            range(len(rows)),
            key=lambda index: abs(center_y - rows[index][0]),
            default=-1,
        )
        if (
            target_index >= 0
            and abs(center_y - rows[target_index][0]) <= tolerance
        ):
            previous_y, row = rows[target_index]
            row.append(block)
            rows[target_index] = (
                (previous_y * (len(row) - 1) + center_y) / len(row),
                row,
            )
        else:
            rows.append((center_y, [block]))
    return [
        (
            center_y,
            sorted(
                row,
                key=lambda item: _box_bounds(
                    (item.get("evidence") or {}).get("bbox")
                )[0],
            ),
        )
        for center_y, row in sorted(rows, key=lambda item: item[0])
    ]


def _header_match_count(
    blocks: list[dict[str, Any]],
    markers: tuple[str, ...],
) -> int:
    keys = [accent_key(block.get("text")) for block in blocks]
    return sum(
        any(
            key == marker
            or key.startswith(f"{marker} ")
            or marker.startswith(f"{key} ")
            for key in keys
        )
        for marker in markers
    )


def _column_model(
    header_blocks: list[dict[str, Any]],
) -> tuple[list[float], list[str]]:
    items = []
    widths = []
    for block in header_blocks:
        bounds = _box_bounds((block.get("evidence") or {}).get("bbox"))
        if not bounds:
            continue
        items.append(((bounds[0] + bounds[2]) / 2, block["text"]))
        widths.append(bounds[2] - bounds[0])
    if not items:
        return [], []
    median_width = sorted(widths)[len(widths) // 2]
    tolerance = max(18.0, median_width * 0.18)
    clusters: list[list[tuple[float, str]]] = []
    for center, text in sorted(items):
        if (
            clusters
            and abs(
                center
                - sum(item[0] for item in clusters[-1])
                / len(clusters[-1])
            )
            <= tolerance
        ):
            clusters[-1].append((center, text))
        else:
            clusters.append([(center, text)])
    centers = [
        sum(item[0] for item in cluster) / len(cluster)
        for cluster in clusters
    ]
    names = [
        " / ".join(dict.fromkeys(item[1] for item in cluster))
        for cluster in clusters
    ]
    return centers, names


def _assigned_row(
    blocks: list[dict[str, Any]],
    centers: list[float],
) -> tuple[list[str], list[dict[str, Any] | None]]:
    values = [""] * len(centers)
    sources: list[dict[str, Any] | None] = [None] * len(centers)
    for block in blocks:
        bounds = _box_bounds((block.get("evidence") or {}).get("bbox"))
        if not bounds:
            continue
        center = (bounds[0] + bounds[2]) / 2
        column = min(
            range(len(centers)),
            key=lambda index: abs(centers[index] - center),
        )
        value = str(block.get("text") or "").strip()
        values[column] = " ".join(
            item for item in (values[column], value) if item
        )
        sources[column] = sources[column] or block
    return values, sources


def _merge_assigned_rows(
    target: tuple[list[str], list[dict[str, Any] | None]],
    addition: tuple[list[str], list[dict[str, Any] | None]],
) -> None:
    target_values, target_sources = target
    addition_values, addition_sources = addition
    for index, value in enumerate(addition_values):
        if not value:
            continue
        target_values[index] = " ".join(
            item for item in (target_values[index], value) if item
        )
        target_sources[index] = target_sources[index] or addition_sources[index]


def _coordinate_table(
    canonical: dict[str, Any],
    document_type: str,
) -> dict[str, Any] | None:
    markers = _TABLE_HEADER_MARKERS.get(document_type)
    if not markers:
        return None
    rows = _coordinate_rows(canonical)
    best: tuple[int, int, int] | None = None
    for start in range(len(rows)):
        for size in (1, 2):
            if start + size > len(rows):
                continue
            blocks = [
                block
                for _, row in rows[start : start + size]
                for block in row
            ]
            matches = _header_match_count(blocks, markers)
            score = matches * 100 - size * 10 + min(len(blocks), 9)
            if best is None or score > best[0]:
                best = (score, start, size)
    if best is None:
        return None
    _, header_start, header_size = best
    header_blocks = [
        block
        for _, row in rows[header_start : header_start + header_size]
        for block in row
    ]
    if _header_match_count(header_blocks, markers) < 3:
        return None
    centers, names = _column_model(header_blocks)
    if len(centers) < 3:
        return None

    data_rows = rows[header_start + header_size :]
    gaps = [
        data_rows[index + 1][0] - data_rows[index][0]
        for index in range(len(data_rows) - 1)
        if data_rows[index + 1][0] > data_rows[index][0]
    ]
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 30.0
    logical_rows: list[
        tuple[
            float,
            tuple[list[str], list[dict[str, Any] | None]],
        ]
    ] = []
    pending: tuple[
        float,
        tuple[list[str], list[dict[str, Any] | None]],
    ] | None = None
    for center_y, blocks in data_rows:
        row_key = " ".join(accent_key(block.get("text")) for block in blocks)
        if any(marker in row_key for marker in _TABLE_STOP_MARKERS):
            break
        assigned = _assigned_row(blocks, centers)
        values = assigned[0]
        if sum(bool(value) for value in values) < 2:
            continue
        leftmost = next((value for value in values if value), "")
        has_employee_id = any(
            re.fullmatch(
                r"(?=.*\d)[A-ZÀ-ỸĐ][A-ZÀ-ỸĐ0-9]{2,}"
                r"(?:[-/][A-ZÀ-ỸĐ0-9]+)*",
                value,
                re.IGNORECASE,
            )
            for value in values
        )
        starts_row = bool(re.fullmatch(r"\d{1,3}", leftmost)) or has_employee_id
        if starts_row:
            if pending:
                _merge_assigned_rows(assigned, pending[1])
                pending = None
            logical_rows.append((center_y, assigned))
            continue
        if logical_rows and center_y - logical_rows[-1][0] <= median_gap * 0.45:
            _merge_assigned_rows(logical_rows[-1][1], assigned)
        else:
            pending = (center_y, assigned)

    normalized_rows = []
    for row_index, (_, (values, sources)) in enumerate(logical_rows):
        cells = []
        for column_index, (value, block) in enumerate(
            zip(values, sources, strict=True)
        ):
            confidence = float(block.get("confidence", 0.0)) if block else 0.0
            cells.append(
                {
                    "columnIndex": column_index,
                    "value": value,
                    "status": (
                        "accepted"
                        if value and confidence >= 0.94
                        else "needs_review"
                        if value
                        else "not_found"
                    ),
                    "evidence": (block or {}).get("evidence"),
                }
            )
        normalized_rows.append(
            {
                "rowIndex": row_index,
                "values": values,
                "cells": cells,
                "status": (
                    "accepted"
                    if cells
                    and all(
                        cell["status"] in {"accepted", "not_found"}
                        for cell in cells
                    )
                    else "needs_review"
                ),
            }
        )
    if not normalized_rows:
        return None
    return {
        "tableIndex": 0,
        "tableType": document_type,
        "sourceKind": "ocr_coordinate_table",
        "columns": [
            {"columnIndex": index, "name": name}
            for index, name in enumerate(names)
        ],
        "rows": normalized_rows,
        "summary": {
            "rowCount": len(normalized_rows),
            "acceptedRowCount": sum(
                row["status"] == "accepted" for row in normalized_rows
            ),
            "columnCount": len(names),
        },
    }


def _generic_tables(
    canonical: dict[str, Any],
    document_type: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for table_index, table in enumerate(canonical.get("tables", [])):
        source_kind = str(table.get("sourceKind") or "")
        rows = []
        for row_index, row in enumerate(table.get("rows", [])):
            values = list(row.get("values") or [])
            cells = list(row.get("cells") or [])
            needs_review = source_kind not in {"xlsx_cells", "docx_table"}
            if cells:
                needs_review = any(
                    cell.get("status") != "accepted" for cell in cells
                )
            rows.append(
                {
                    "rowIndex": int(row.get("rowIndex", row_index)),
                    "values": values,
                    "cells": cells,
                    "status": (
                        "needs_review" if needs_review else "accepted"
                    ),
                }
            )
        output.append(
            {
                "tableIndex": int(table.get("tableIndex", table_index)),
                "tableType": "HR_FORM_TABLE",
                "sourceKind": source_kind,
                "columns": list(table.get("columns") or []),
                "rows": rows,
                "summary": {
                    "rowCount": len(rows),
                    "acceptedRowCount": sum(
                        row["status"] == "accepted" for row in rows
                    ),
                    "columnCount": len(table.get("columns") or []),
                },
            }
        )
    coordinate_table = _coordinate_table(canonical, document_type)
    if coordinate_table and not output:
        output.append(coordinate_table)
    return output


def parse_employee_form_table(
    canonical: dict[str, Any],
    document_type: str,
) -> dict[str, Any]:
    fields = {
        "formNumber": _labeled(
            canonical,
            ("Số phiếu", "Mã biểu mẫu", "Mã phiếu", "Số"),
        ),
        "employeeName": _labeled(
            canonical,
            ("Họ và tên", "Họ tên", "Tên nhân viên"),
        ),
        "employeeId": _labeled(
            canonical,
            ("Mã nhân viên", "Mã NV", "MSNV"),
        ),
        "dateOfBirth": _labeled(canonical, ("Ngày sinh",)),
        "gender": _labeled(canonical, ("Giới tính",)),
        "department": _labeled(canonical, ("Phòng ban", "Bộ phận")),
        "jobTitle": _labeled(canonical, ("Chức danh", "Chức vụ", "Vị trí")),
        "email": _email_field(canonical),
        "phoneNumber": _phone_field(canonical),
        "address": _labeled(
            canonical,
            ("Địa chỉ liên hệ", "Địa chỉ thường trú", "Địa chỉ"),
        ),
        "organization": _labeled(
            canonical,
            ("Đơn vị", "Công ty", "Tổ chức"),
        ),
        "joinDate": _labeled(
            canonical,
            ("Ngày vào làm", "Ngày nhận việc"),
        ),
    }
    return _schema_output(
        document_type,
        fields,
        _generic_tables(canonical, document_type),
    )


def _contract_decision_schema(
    canonical: dict[str, Any],
    document_type: str,
) -> dict[str, Any]:
    labels = (
        "Người lao động",
        "Họ và tên",
        "Mã nhân viên",
        "Mã NV",
        "Công việc/Chức danh",
        "Chức danh",
        "Vị trí công việc",
        "Vị trí",
        "Mức lương cơ bản",
        "Lương cơ bản",
        "Mức lương",
        "Ngày bắt đầu",
        "Ngày hiệu lực",
        "Từ ngày",
        "Ngày kết thúc",
        "Đến ngày",
        "Hết hạn ngày",
    )
    document_number = _regex_field(
        canonical,
        (
            r"^\s*Số(?:\s+hợp đồng)?\s*[:\-]?\s*"
            r"([A-ZÀ-Ỹ0-9Đ][A-ZÀ-Ỹ0-9Đ./-]{3,})",
        ),
        validator=lambda value: bool(
            re.fullmatch(r"[A-ZÀ-Ỹ0-9Đ][A-ZÀ-Ỹ0-9Đ./-]{3,}", str(value), re.I)
        ),
        method="contract_decision_number_pattern",
    )

    employee_name = _bounded_labeled(
        canonical,
        ("Người lao động", "Họ và tên"),
        stop_labels=labels,
    )
    if document_type == "HR_DECISION" or employee_name["value"] is None:
        article_name = _regex_field(
            canonical,
            (
                r"(?:ông/bà|ông|bà)\s+(.{3,80}?)"
                r"(?=\s*,\s*mã\s+nhân\s+viên\b)",
            ),
            validator=lambda value: _likely_person_name(str(value)),
            method="decision_article_person",
        )
        if article_name["value"] is not None:
            employee_name = article_name

    employee_id = _bounded_labeled(
        canonical,
        ("Mã nhân viên", "Mã NV"),
        stop_labels=labels,
        normalizer=lambda value: re.sub(
            r"^(EMP)[./](?=\d)",
            r"\1-",
            value.strip(),
            flags=re.IGNORECASE,
        ),
        validator=lambda value: bool(
            re.fullmatch(r"EMP-\d{3,}", str(value), re.IGNORECASE)
        ),
        method="employee_id_label",
    )
    if employee_id["value"] is None:
        employee_id = _regex_field(
            canonical,
            (
                r"mã\s+nhân\s+viên\s+(EMP[./-]?\d{3,})",
            ),
            normalizer=lambda value: re.sub(
                r"^(EMP)[./]?(?=\d)",
                r"\1-",
                value,
                flags=re.IGNORECASE,
            ),
            validator=lambda value: bool(
                re.fullmatch(r"EMP-\d{3,}", str(value), re.IGNORECASE)
            ),
            method="decision_article_employee_id",
        )

    job_title = _bounded_labeled(
        canonical,
        ("Công việc/Chức danh", "Chức danh", "Vị trí công việc", "Vị trí"),
        stop_labels=labels,
    )
    salary = _bounded_labeled(
        canonical,
        ("Mức lương cơ bản", "Lương cơ bản", "Mức lương"),
        stop_labels=labels,
    )
    start_date = _bounded_labeled(
        canonical,
        ("Ngày bắt đầu", "Từ ngày"),
        stop_labels=labels,
        data_type="date",
    )
    end_date = _bounded_labeled(
        canonical,
        ("Ngày kết thúc", "Đến ngày", "Hết hạn ngày"),
        stop_labels=labels,
        data_type="date",
    )
    action = _regex_field(
        canonical,
        (
            r"^(Về\s+việc\s+.{4,180})$",
        ),
        group=1,
        method="decision_subject_line",
    )
    effective_date = _regex_field(
        canonical,
        (
            r"(?:hiệu\s+lực\s+từ|kể\s+từ|"
            r"thời\s+điểm\s+nhận\s+nhiệm\s+vụ\s+mới(?:\s+là)?)"
            r"\s*(?:ngày)?\s*[:\-]?\s*"
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        ),
        data_type="date",
        method="decision_effective_date_pattern",
    )

    fields = {
        "documentNumber": document_number,
        "employeeName": employee_name,
        "employeeId": employee_id,
        "jobTitle": job_title,
        "action": action,
        "salary": salary,
        "startDate": start_date,
        "endDate": end_date,
        "effectiveDate": effective_date,
    }
    return _schema_output(
        document_type,
        fields,
        _generic_tables(canonical, document_type),
    )


def extract_phase15_document(
    canonical: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    """Extract a family-specific evidence-bearing business payload."""
    document_type = str(classification["documentType"])
    family = str(classification.get("documentFamily") or "OTHER_HR_DOCUMENT")

    if document_type == "IDENTITY_DOCUMENT":
        extraction = _schema_output(document_type, {})
    elif document_type == "CV":
        extraction = parse_cv(canonical)
    elif family == "ADMINISTRATIVE_REQUEST":
        extraction = parse_administrative_request(canonical, document_type)
    elif family == "CONTRACT_DECISION":
        extraction = _contract_decision_schema(canonical, document_type)
    elif family == "DEGREE_CERTIFICATE":
        extraction = parse_degree_certificate(canonical)
    elif family == "EMPLOYEE_FORM_TABLE":
        extraction = parse_employee_form_table(canonical, document_type)
    else:
        extraction = _schema_output(document_type, {})
    fields = _enforce_sensitive_review_policy(extraction.get("fields", {}))
    return {
        **extraction,
        "fields": fields,
        "summary": _field_summary(fields),
        "parserVersion": IDP_PARSER_VERSION,
    }


_TRUSTED_SENSITIVE_SOURCES = {
    "human_review",
    "pdf_text_layer",
    "docx_text",
    "docx_table",
    "xlsx_cells",
}


def _enforce_sensitive_review_policy(
    fields: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Prevent OCR-only sensitive values from being falsely auto-accepted."""
    protected: dict[str, dict[str, Any]] = {}
    for name, field in fields.items():
        updated = dict(field)
        evidence = updated.get("evidence") or {}
        source_kind = str(evidence.get("sourceKind") or "")
        if (
            name in SENSITIVE_FIELDS
            and updated.get("value") is not None
            and updated.get("status") == "accepted"
            and source_kind not in _TRUSTED_SENSITIVE_SOURCES
        ):
            updated["status"] = "needs_review"
            updated["reviewReason"] = "sensitive_ocr_requires_human_review"
        protected[name] = updated
    return protected


def _field_summary(
    fields: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    statuses = [str(field.get("status") or "") for field in fields.values()]
    present = sum(field.get("value") is not None for field in fields.values())
    accepted = statuses.count("accepted")
    expected = len(fields)
    return {
        "expectedFieldCount": expected,
        "presentFieldCount": present,
        "acceptedFieldCount": accepted,
        "needsReviewFieldCount": statuses.count("needs_review"),
        "notFoundFieldCount": statuses.count("not_found"),
        "documentCompleteness": round(present / max(1, expected), 6),
        "acceptedCoverage": round(accepted / max(1, expected), 6),
        "readyForAutomaticUse": expected > 0 and accepted == expected,
    }


def _with_sensitivity(
    fields: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        name: {
            **field,
            "sensitive": name in SENSITIVE_FIELDS,
        }
        for name, field in fields.items()
    }


def build_phase15_business_json(
    document_id: str,
    canonical: dict[str, Any],
    classification: dict[str, Any],
    extraction: dict[str, Any],
    *,
    contains_real_pii: bool = True,
    result_reference: str = "phase15/idp_result.json",
) -> dict[str, Any]:
    """Build local Business JSON while keeping raw PII out of Camunda variables."""
    document_type = str(classification["documentType"])
    family = str(classification.get("documentFamily") or "OTHER_HR_DOCUMENT")
    fields = _with_sensitivity(extraction.get("fields", {}))
    tables = list(extraction.get("tables", []))
    summary = dict(extraction.get("summary", {}))
    sensitive_needs_review = any(
        field.get("sensitive")
        and field.get("value") is not None
        and field.get("status") != "accepted"
        for field in fields.values()
    )
    review_required = (
        classification.get("status") != "accepted"
        or summary.get("expectedFieldCount", 0) == 0
        or bool(canonical.get("metadata", {}).get("requiresImageOcr"))
        or any(field.get("status") != "accepted" for field in fields.values())
        or any(
            row.get("status") != "accepted"
            for table in tables
            for row in table.get("rows", [])
        )
    )
    idp_status = "NEEDS_REVIEW" if review_required else "READY"
    workflow_type = str(
        classification.get("workflowDocumentType")
        or WORKFLOW_TYPE_BY_DOCUMENT_TYPE.get(
            document_type,
            "OTHER_HR_DOCUMENT",
        )
    )
    payload = {
        "documentId": document_id,
        "documentType": document_type,
        "documentFamily": family,
        "parserVersion": extraction.get(
            "parserVersion",
            IDP_PARSER_VERSION,
        ),
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
        "summary": summary,
    }
    business_json = {
        "schemaVersion": "2.0.0",
        "schemaRef": classification.get("schemaRef"),
        "documentId": document_id,
        "documentType": document_type,
        "documentFamily": family,
        "workflowDocumentType": workflow_type,
        "idpStatus": idp_status,
        "containsRealPII": bool(contains_real_pii),
        "processingPolicy": {
            "evidenceRequired": True,
            "unverifiedValuesMayBeAccepted": False,
            "localOnly": True,
            "sensitiveFieldNeedsReview": sensitive_needs_review,
        },
        "payload": payload,
        "camunda": {
            "businessKey": document_id,
            "variables": {
                "documentReference": document_id,
                "detectedDocumentType": document_type,
                "workflowDocumentType": workflow_type,
                "sourceFormat": canonical.get("sourceFormat"),
                "classificationStatus": classification.get("status"),
                "classificationConfidence": classification.get("confidence"),
                "parseStatus": "SUCCESS",
                "qualityStatus": (
                    "REVIEW_REQUIRED" if review_required else "PASS"
                ),
                "reviewRequired": review_required,
                "sensitiveFieldNeedsReview": sensitive_needs_review,
                "requiredFieldsComplete": bool(
                    summary.get("documentCompleteness") == 1.0
                ),
                "resultReference": result_reference,
                "schemaVersion": "2.0.0",
            },
        },
    }
    validate_phase15_business_json(business_json)
    return business_json


def validate_phase15_business_json(payload: dict[str, Any]) -> None:
    required = {
        "schemaVersion",
        "schemaRef",
        "documentId",
        "documentType",
        "documentFamily",
        "workflowDocumentType",
        "idpStatus",
        "payload",
        "camunda",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"Phase 15 Business JSON missing keys: {sorted(missing)}")
    if payload["idpStatus"] not in {"READY", "NEEDS_REVIEW"}:
        raise ValueError("Invalid Phase 15 IDP status")
    variables = payload.get("camunda", {}).get("variables", {})
    forbidden = {
        "idpPayload",
        "rawFile",
        "ocrText",
        "recognizedText",
        "fields",
        "tables",
    }
    leaked = forbidden & set(variables)
    if leaked:
        raise ValueError(
            f"Raw document content is forbidden in Camunda variables: {sorted(leaked)}"
        )
    for field_name, field in payload.get("payload", {}).get("fields", {}).items():
        if field.get("value") is not None and not field.get("evidence"):
            raise ValueError(
                f"Field {field_name} has a value without OCR/native evidence"
            )
        if (
            field.get("status") == "accepted"
            and not field.get("validation", {}).get("valid")
        ):
            raise ValueError(
                f"Field {field_name} is accepted without validation"
            )


def schema_path_for_family(repository_root: Path, family: str) -> Path:
    """Resolve a checked-in schema without accepting an arbitrary path."""
    relative = BUSINESS_SCHEMA_BY_FAMILY.get(
        family,
        BUSINESS_SCHEMA_BY_FAMILY["OTHER_HR_DOCUMENT"],
    )
    candidate = (repository_root / relative).resolve()
    schemas_root = (repository_root / "schemas").resolve()
    if schemas_root not in candidate.parents:
        raise ValueError("Schema path escaped the repository schema directory")
    return candidate
