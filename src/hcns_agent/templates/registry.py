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
from hcns_agent.templates.model import TemplateDefinition, TemplateDetection, TemplateParser
from hcns_agent.templates.overtime_request.parser import OvertimeRequestParser
from hcns_agent.templates.overtime_request.validator import OvertimeRequestValidator
from hcns_agent.templates.citizen_id_front import CitizenIdFrontParser
from hcns_agent.templates.review_only import ReviewOnlyParser, ReviewOnlyValidator
from hcns_agent.templates.structured_hr import (
    STRUCTURED_HR_PARSER_ID,
    STRUCTURED_HR_PARSER_VERSION,
    StructuredHrParser,
)

_NATIVE_TEMPLATE_FILE_TYPES = ("docx", "pdf")
_OCR_TEMPLATE_FILE_TYPES = ("pdf", "png", "jpg", "jpeg")


class TemplateRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, TemplateDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, definition: TemplateDefinition) -> None:
        if definition.template_id in self._definitions:
            raise ValueError(f"Template already registered: {definition.template_id}")
        self._definitions[definition.template_id] = definition

    def register_alias(self, alias: str, target: str) -> None:
        if alias in self._definitions or alias in self._aliases:
            raise ValueError(f"Template alias already registered: {alias}")
        if target not in self._definitions:
            raise ValueError(f"Template alias target is not registered: {target}")
        self._aliases[alias] = target

    def detect(self, document: CanonicalDocument) -> TemplateDetection | None:
        normalize = (
            normalize_for_ocr_match
            if document.source_format in {SourceFormat.IMAGE, SourceFormat.PDF_SCAN}
            else normalize_for_match
        )
        text = document_text(document)
        normalized = normalize(text)
        normalized_plain = normalize_for_ocr_match(text)
        normalized_compact = normalized_plain.replace(" ", "")
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
                    or normalize_for_ocr_match(anchor).replace(" ", "")
                    in normalized_compact
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

        return self._definitions.get(self._aliases.get(template_id, template_id))


def build_default_template_registry() -> TemplateRegistry:
    registry = TemplateRegistry()
    registry.register(
        TemplateDefinition(
            template_id="leave-request-v1",
            document_type=DocumentType.LEAVE_REQUEST,
            version="1.0",
            parser_id="leave-request/parser",
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
            parser_id="overtime-request/parser",
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
            parser_version="1.1.0",
            anchors=(
                "ĐƠN XIN TĂNG CA",
                "Thời gian đề nghị",
                "Nội dung công việc",
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
        version: str = "1.0",
        parser_version: str = "1.0.0",
        parser_id: str = "review-only/label-next-line",
        parser: TemplateParser | None = None,
        optional_fields: tuple[str, ...] = (),
        schema_version: str = "2.0.0",
    ) -> TemplateDefinition:
        return TemplateDefinition(
            template_id=template_id,
            document_type=document_type,
            version=version,
            parser_id=parser_id,
            supported_file_types=supported_file_types,
            required_fields=required_fields,
            optional_fields=optional_fields,
            schema_ref=schema_ref,
            parser_version=parser_version,
            anchors=anchors,
            minimum_anchor_matches=minimum_anchor_matches,
            parser=parser or ReviewOnlyParser(field_labels),
            validator=ReviewOnlyValidator(),
            schema_version=schema_version,
        )

    registry.register(
        review_template(
            template_id="probation-contract-v2",
            document_type=DocumentType.EMPLOYMENT_CONTRACT,
            supported_file_types=_NATIVE_TEMPLATE_FILE_TYPES,
            required_fields=(
                "contract_number", "contract_sign_date", "effective_date",
                "probation_end_date", "employer_name", "employer_representative",
                "employee_name", "employee_id_number", "job_title", "workplace",
                "weekly_hours", "probation_salary_monthly", "allowances_summary",
                "salary_payment_schedule",
            ),
            optional_fields=("professional_title", "role_title"),
            schema_ref="schemas/templates/probation_contract_v2.schema.json",
            anchors=(
                "probation",
                "HỢP ĐỒNG THỬ VIỆC",
                "THỜI GIAN THỬ VIỆC",
                "MỨC LƯƠNG",
            ),
            minimum_anchor_matches=2,
            version="2.1",
            parser_version=STRUCTURED_HR_PARSER_VERSION,
            parser_id=STRUCTURED_HR_PARSER_ID,
            parser=StructuredHrParser(),
            schema_version="2.1.0",
            field_labels={
                "contract_number": ("contract number", "so hop dong"),
                "contract_sign_date": ("contract sign date", "ngay ky hop dong"),
                "effective_date": ("effective date", "ngay hieu luc"),
                "probation_end_date": ("probation end", "ket thuc thu viec"),
                "employer_name": ("employer", "nguoi su dung lao dong"),
                "employer_representative": ("employer representative", "nguoi dai dien"),
                "employee_name": ("employee name", "nguoi lao dong", "ho va ten"),
                "employee_id_number": ("employee id", "ma nhan vien", "so cccd"),
                "job_title": ("job title", "chuc danh", "vi tri cong viec"),
                "workplace": ("workplace", "dia diem lam viec"),
                "weekly_hours": ("weekly hours", "gio lam viec"),
                "probation_salary_monthly": ("salary", "muc luong", "luong thu viec"),
                "allowances_summary": ("allowances", "phu cap"),
                "salary_payment_schedule": ("salary payment", "ky tra luong"),
            },
        )
    )
    registry.register(
        review_template(
            template_id="cv-v2",
            document_type=DocumentType.CV,
            supported_file_types=_NATIVE_TEMPLATE_FILE_TYPES,
            required_fields=(
                "full_name", "headline", "email", "phone_number", "address",
                "desired_role", "years_experience", "experience", "skills", "education",
            ),
            schema_ref="schemas/templates/cv_v2.schema.json",
            anchors=("curriculum vitae", "kinh nghiem", "ky nang"),
            minimum_anchor_matches=2,
            version="2.0",
            parser_version=STRUCTURED_HR_PARSER_VERSION,
            parser_id=STRUCTURED_HR_PARSER_ID,
            parser=StructuredHrParser(),
            field_labels={
                "full_name": ("full name", "ho va ten", "name"),
                "headline": ("headline", "muc tieu nghe nghiep", "position"),
                "email": ("email", "thu dien tu"),
                "phone_number": ("phone", "dien thoai", "so dien thoai"),
                "address": ("address", "dia chi"),
                "desired_role": ("desired role", "muc tieu nghe nghiep", "position"),
                "years_experience": ("years experience", "so nam kinh nghiem"),
                "education": ("education", "hoc van"),
                "experience": ("experience", "kinh nghiem"),
                "skills": ("skills", "ky nang"),
            },
        )
    )
    registry.register(
        review_template(
            template_id="ielts-certificate-v2",
            document_type=DocumentType.CERTIFICATE,
            supported_file_types=_OCR_TEMPLATE_FILE_TYPES,
            required_fields=(
                "recipient_name", "credential_id", "credential_type",
                "overall_score", "issue_date",
            ),
            schema_ref="schemas/templates/ielts_certificate_v2.schema.json",
            anchors=("ielts", "test report form", "overall band score"),
            minimum_anchor_matches=2,
            version="2.0",
            parser_version=STRUCTURED_HR_PARSER_VERSION,
            parser_id=STRUCTURED_HR_PARSER_ID,
            parser=StructuredHrParser(),
            field_labels={
                "recipient_name": ("recipient name", "candidate name", "name"),
                "credential_id": ("credential id", "test report form number", "trf number"),
                "credential_type": ("test type", "credential type", "ielts"),
                "overall_score": ("overall band score", "overall score"),
                "issue_date": ("issue date", "test date", "date of test"),
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
            # Include OCR-noisy variants from latin recognizer (e.g. "CN CƯC CNG DN",
            # "Date of bith", "Citzen Identy Card") so front CCCD still detects.
            anchors=(
                "can cuoc cong dan",
                "cn cuc cng dn",
                "citizen identity",
                "citzen identy",
                "date of birth",
                "date of bith",
                "place of origin",
                "ho va ten",
                "nationality",
                "quoc tich",
            ),
            minimum_anchor_matches=2,
            parser=CitizenIdFrontParser(),
            field_labels={
                "idNumber": ("id number", "so/no", "so cccd", "so dinh danh ca nhan", "no:"),
                "fullName": ("full name", "ful name", "ho va ten", "ho và ten"),
                "dateOfBirth": ("date of birth", "date of bith", "ngay sinh", "nay sinh"),
                "sex": ("sex", "gioi tinh", "giới tính", "nam/nu"),
                "nationality": ("nationality", "quoc tich", "quốc tịch"),
                "placeOfOrigin": ("place of origin", "que quan", "quê quán"),
                "placeOfResidence": (
                    "place of residence",
                    "noi thuong tru",
                    "nơi thường trú",
                    "pce rsidence",
                ),
            },
        )
    )
    registry.register_alias("probation-contract-v1", "probation-contract-v2")
    registry.register_alias("cv-v1", "cv-v2")
    registry.register_alias("ielts-certificate-v1", "ielts-certificate-v2")
    return registry
