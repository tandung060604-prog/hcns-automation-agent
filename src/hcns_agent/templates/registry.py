"""Deterministic content-based registry for approved document templates."""

from __future__ import annotations

from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.domain.documents import DocumentType, SourceFormat
from hcns_agent.templates.common import (
    document_text,
    fuzzy_ocr_contains,
    normalize_for_match,
    normalize_for_ocr_match,
)
from hcns_agent.templates.leave_request.parser import LeaveRequestParser
from hcns_agent.templates.leave_request.validator import LeaveRequestValidator
from hcns_agent.templates.model import TemplateDefinition, TemplateDetection
from hcns_agent.templates.overtime_request.parser import OvertimeRequestParser
from hcns_agent.templates.overtime_request.validator import OvertimeRequestValidator
from hcns_agent.templates.review_only import ReviewOnlyParser, ReviewOnlyValidator

_NATIVE_TEMPLATE_FILE_TYPES = ("docx", "pdf")
_OCR_TEMPLATE_FILE_TYPES = ("pdf", "png", "jpg", "jpeg")


class TemplateRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, TemplateDefinition] = {}

    def register(self, definition: TemplateDefinition) -> None:
        if definition.template_id in self._definitions:
            raise ValueError(f"Template already registered: {definition.template_id}")
        self._definitions[definition.template_id] = definition

    def detect(self, document: CanonicalDocument) -> TemplateDetection | None:
        normalize = (
            normalize_for_ocr_match
            if document.source_format in {SourceFormat.IMAGE, SourceFormat.PDF_SCAN}
            else normalize_for_match
        )
        text = document_text(document)
        normalized = normalize(text)
        normalized_plain = normalize_for_ocr_match(text)
        uses_ocr_matching = document.source_format in {
            SourceFormat.IMAGE,
            SourceFormat.PDF_SCAN,
        }
        candidates: list[TemplateDetection] = []
        for definition in self._definitions.values():
            if (
                definition.template_id == "vietnam-citizen-id-front-v1"
                and any(
                    marker in normalized
                    for marker in ("back", "mat sau", "dac diem nhan dang")
                )
            ):
                continue
            matched = tuple(
                anchor
                for anchor in definition.anchors
                if (
                    normalize(anchor) in normalized
                    or normalize_for_ocr_match(anchor) in normalized_plain
                    or (
                        uses_ocr_matching
                        and fuzzy_ocr_contains(text, anchor)
                    )
                )
            )
            if len(matched) < definition.minimum_anchor_matches:
                continue
            confidence = round(len(matched) / len(definition.anchors), 4)
            candidates.append(
                TemplateDetection(
                    definition=definition,
                    matched_anchors=matched,
                    confidence=confidence,
                )
            )
        candidates.sort(
            key=lambda candidate: (
                -candidate.confidence,
                -len(candidate.matched_anchors),
                candidate.definition.template_id,
            )
        )
        if not candidates:
            return None
        if len(candidates) > 1 and candidates[0].confidence == candidates[1].confidence:
            return None
        return candidates[0]

    def list_templates(self) -> tuple[dict[str, object], ...]:
        return tuple(
            self._definitions[key].public_dict() for key in sorted(self._definitions)
        )

    def get(self, template_id: str) -> TemplateDefinition | None:
        """Return one frozen template definition by its stable identifier."""

        return self._definitions.get(template_id)


def build_default_template_registry() -> TemplateRegistry:
    registry = TemplateRegistry()
    registry.register(
        TemplateDefinition(
            template_id="leave-request-v1",
            document_type=DocumentType.LEAVE_REQUEST,
            version="1.0",
            supported_file_types=_NATIVE_TEMPLATE_FILE_TYPES,
            required_fields=(
                "employeeName",
                "jobTitle",
                "department",
                "requestDate",
                "startDate",
                "endDate",
                "reason",
            ),
            optional_fields=(
                "formNumber",
                "organization",
                "employeeId",
                "address",
                "phone",
                "leaveDays",
                "expectedReturnDate",
                "handoverTo",
                "handoverDepartment",
                "handoverTasks",
                "approverName",
            ),
            schema_ref="schemas/templates/leave_request_v1.schema.json",
            parser_version="1.0.0",
            anchors=(
                "ĐƠN XIN NGHỈ PHÉP",
                "Lý do xin nghỉ phép",
                "Tôi đã bàn giao công việc cho",
            ),
            minimum_anchor_matches=2,
            parser=LeaveRequestParser(),
            validator=LeaveRequestValidator(),
        )
    )
    registry.register(
        TemplateDefinition(
            template_id="overtime-request-v1",
            document_type=DocumentType.OVERTIME_REQUEST,
            version="1.0",
            supported_file_types=_NATIVE_TEMPLATE_FILE_TYPES,
            required_fields=(
                "employeeName",
                "jobTitle",
                "requestDate",
                "reason",
                "startDate",
                "endDate",
                "overtimeHoursPerDay",
                "overtimeStartTime",
                "overtimeEndTime",
                "totalOvertimeHours",
                "workContent",
            ),
            optional_fields=(
                "formNumber",
                "organization",
                "employeeId",
                "department",
                "laborContractNumber",
                "laborContractDate",
                "standardWorkSchedule",
            ),
            schema_ref="schemas/templates/overtime_request_v1.schema.json",
            parser_version="1.0.0",
            anchors=(
                "ĐƠN XIN TĂNG CA",
                "Thời gian đề nghị",
                "Nội dung công việc",
                "tăng thêm",
            ),
            minimum_anchor_matches=3,
            parser=OvertimeRequestParser(),
            validator=OvertimeRequestValidator(),
        )
    )
    def review_template(
        *,
        template_id: str,
        document_type: DocumentType,
        supported_file_types: tuple[str, ...],
        required_fields: tuple[str, ...],
        schema_ref: str,
        anchors: tuple[str, ...],
        minimum_anchor_matches: int,
        field_labels: dict[str, tuple[str, ...]],
    ) -> TemplateDefinition:
        return TemplateDefinition(
            template_id=template_id,
            document_type=document_type,
            version="1.0",
            supported_file_types=supported_file_types,
            required_fields=required_fields,
            optional_fields=(),
            schema_ref=schema_ref,
            parser_version="1.0.0",
            anchors=anchors,
            minimum_anchor_matches=minimum_anchor_matches,
            parser=ReviewOnlyParser(field_labels),
            validator=ReviewOnlyValidator(),
        )

    registry.register(
        review_template(
            template_id="probation-contract-v1",
            document_type=DocumentType.EMPLOYMENT_CONTRACT,
            supported_file_types=_NATIVE_TEMPLATE_FILE_TYPES,
            required_fields=(
                "employeeName", "employeeId", "jobTitle", "salary",
                "effectiveDate", "probationEndDate", "employerName",
            ),
            schema_ref="schemas/templates/probation_contract_v1.schema.json",
            anchors=(
                "probation",
                "HỢP ĐỒNG THỬ VIỆC",
                "THỜI GIAN THỬ VIỆC",
                "MỨC LƯƠNG",
            ),
            minimum_anchor_matches=2,
            field_labels={
                "employeeName": ("employee name", "nguoi lao dong", "ho va ten"),
                "employeeId": ("employee id", "ma nhan vien", "so cccd"),
                "jobTitle": ("job title", "chuc danh", "vi tri cong viec"),
                "salary": ("salary", "muc luong", "luong thu viec"),
                "effectiveDate": ("effective date", "ngay hieu luc"),
                "probationEndDate": ("probation end", "ket thuc thu viec"),
                "employerName": ("employer", "nguoi su dung lao dong"),
            },
        )
    )
    registry.register(
        review_template(
            template_id="cv-v1",
            document_type=DocumentType.CV,
            supported_file_types=_NATIVE_TEMPLATE_FILE_TYPES,
            required_fields=(
                "fullName", "headline", "email", "phoneNumber", "address",
                "education", "experience", "skills",
            ),
            schema_ref="schemas/templates/cv_v1.schema.json",
            anchors=("curriculum vitae", "kinh nghiem", "ky nang"),
            minimum_anchor_matches=2,
            field_labels={
                "fullName": ("full name", "ho va ten", "name"),
                "headline": ("headline", "muc tieu nghe nghiep", "position"),
                "email": ("email", "thu dien tu"),
                "phoneNumber": ("phone", "dien thoai", "so dien thoai"),
                "address": ("address", "dia chi"),
                "education": ("education", "hoc van"),
                "experience": ("experience", "kinh nghiem"),
                "skills": ("skills", "ky nang"),
            },
        )
    )
    registry.register(
        review_template(
            template_id="ielts-certificate-v1",
            document_type=DocumentType.CERTIFICATE,
            supported_file_types=_OCR_TEMPLATE_FILE_TYPES,
            required_fields=(
                "recipientName", "credentialId", "credentialType",
                "overallScore", "issueDate",
            ),
            schema_ref="schemas/templates/ielts_certificate_v1.schema.json",
            anchors=("ielts", "test report form", "overall band score"),
            minimum_anchor_matches=2,
            field_labels={
                "recipientName": ("recipient name", "candidate name", "name"),
                "credentialId": ("credential id", "test report form number", "trf number"),
                "credentialType": ("test type", "credential type", "ielts"),
                "overallScore": ("overall band score", "overall score"),
                "issueDate": ("issue date", "test date", "date of test"),
            },
        )
    )
    registry.register(
        review_template(
            template_id="vietnam-citizen-id-front-v1",
            document_type=DocumentType.IDENTITY_CARD,
            supported_file_types=_OCR_TEMPLATE_FILE_TYPES,
            required_fields=(
                "idNumber", "fullName", "dateOfBirth", "sex", "nationality",
                "placeOfOrigin", "placeOfResidence",
            ),
            schema_ref="schemas/templates/vietnam_citizen_id_front_v1.schema.json",
            anchors=("can cuoc cong dan", "date of birth", "nationality", "front"),
            minimum_anchor_matches=3,
            field_labels={
                "idNumber": ("id number", "so cccd", "so dinh danh ca nhan"),
                "fullName": ("full name", "ho va ten"),
                "dateOfBirth": ("date of birth", "ngay sinh"),
                "sex": ("sex", "gioi tinh"),
                "nationality": ("nationality", "quoc tich"),
                "placeOfOrigin": ("place of origin", "que quan"),
                "placeOfResidence": ("place of residence", "noi thuong tru"),
            },
        )
    )
    return registry
