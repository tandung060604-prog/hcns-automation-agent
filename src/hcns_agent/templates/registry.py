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
        uses_ocr_matching = document.source_format in {
            SourceFormat.IMAGE,
            SourceFormat.PDF_SCAN,
        }
        candidates: list[TemplateDetection] = []
        for definition in self._definitions.values():
            matched = tuple(
                anchor
                for anchor in definition.anchors
                if (
                    normalize(anchor) in normalized
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
            supported_file_types=("docx", "pdf", "png", "jpg", "jpeg"),
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
            supported_file_types=("docx", "pdf", "png", "jpg", "jpeg"),
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
    return registry
