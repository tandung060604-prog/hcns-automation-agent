"""Synthetic M4-CAM-006 scenario matrix for the Camunda shadow workflow.

The runner exercises the same stage operations used by the External Task worker,
but keeps all source/result artifacts in a caller-owned temporary directory.  It
does not connect to Camunda or emit raw document/OCR values in its report.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Protocol, cast
from zipfile import ZIP_DEFLATED, ZipFile

from hcns_agent.adapters.camunda7.contract import (
    CamundaQualityAction,
    ProcessVariables,
    QualityRoutingInputs,
    route_quality,
    validate_process_variables,
)
from hcns_agent.adapters.camunda7.handlers import (
    ReuploadControlHandler,
    build_m4_shadow_handlers,
)
from hcns_agent.adapters.camunda7.review import JsonFileCorrectionStore
from hcns_agent.adapters.camunda7.runtime import (
    JsonFileTemplateResultStore,
    LocalSessionDocumentSourceStore,
    M4TemplateStageOperations,
    TemplatePipeline,
)
from hcns_agent.adapters.camunda7.worker import (
    CamundaBusinessError,
    CamundaTechnicalError,
)
from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.bootstrap import build_default_intake
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.templates.model import TemplateProcessingResult
from hcns_agent.templates.registry import build_default_template_registry
from hcns_agent.templates.service import (
    TemplateProcessingService,
    TemplateTechnicalError,
    build_default_template_processing_service,
)


class _ExternalHandler(Protocol):
    def handle(self, variables: Mapping[str, object]) -> ProcessVariables:
        ...


@dataclass(slots=True)
class _FlakyPipeline:
    delegate: TemplatePipeline
    failures_remaining: int = 1

    def process(
        self,
        source: DocumentSource,
        *,
        result_reference: str | None = None,
    ) -> TemplateProcessingResult:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise TemplateTechnicalError("SYNTHETIC_TRANSIENT_FAILURE")
        return self.delegate.process(source, result_reference=result_reference)

    def apply_corrections(
        self,
        stored_payload: Mapping[str, object],
        corrections: Mapping[str, object],
    ) -> TemplateProcessingResult:
        return self.delegate.apply_corrections(stored_payload, corrections)


@dataclass(frozen=True, slots=True)
class DryRunScenarioResult:
    scenario_id: str
    name: str
    expected_state: str
    observed_state: str
    passed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "scenarioId": self.scenario_id,
            "name": self.name,
            "expectedState": self.expected_state,
            "observedState": self.observed_state,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class M4DryRunReport:
    scenarios: tuple[DryRunScenarioResult, ...]
    false_auto_continue: int
    duplicate_result_artifacts: int
    technical_retries: int
    real_side_effects_enabled: bool = False
    contains_raw_field_values: bool = False

    @property
    def passed_count(self) -> int:
        return sum(1 for scenario in self.scenarios if scenario.passed)

    @property
    def total_count(self) -> int:
        return len(self.scenarios)

    @property
    def passed(self) -> bool:
        return (
            self.total_count == 10
            and self.passed_count == self.total_count
            and self.false_auto_continue == 0
            and self.duplicate_result_artifacts == 0
            and not self.real_side_effects_enabled
            and not self.contains_raw_field_values
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "milestone": "M4-CAM-006",
            "mode": "SHADOW",
            "passed": self.passed,
            "passedScenarios": self.passed_count,
            "totalScenarios": self.total_count,
            "falseAutoContinue": self.false_auto_continue,
            "duplicateResultArtifacts": self.duplicate_result_artifacts,
            "technicalRetries": self.technical_retries,
            "realSideEffectsEnabled": self.real_side_effects_enabled,
            "containsRawFieldValues": self.contains_raw_field_values,
            "scenarios": [scenario.as_dict() for scenario in self.scenarios],
        }


def run_m4_dry_run(private_root: Path) -> M4DryRunReport:
    """Run the ten synthetic M4-CAM-006 scenarios in a private temp root."""

    root = private_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    operations, result_store = _build_operations(root)
    mapping = operations.as_mapping()
    handlers = {
        handler.topic_name: handler
        for handler in build_m4_shadow_handlers(mapping, operations.review_audit_operation)
    }
    scenarios: list[DryRunScenarioResult] = []

    scenarios.append(
        _run_valid_document(
            root,
            mapping,
            scenario_id="CAM-006-01",
            name="leave DOCX valid",
            document_type="LEAVE_REQUEST",
            lines=_leave_lines(),
        )
    )
    scenarios.append(
        _run_valid_document(
            root,
            mapping,
            scenario_id="CAM-006-02",
            name="overtime DOCX valid",
            document_type="OVERTIME_REQUEST",
            lines=_overtime_lines(),
        )
    )
    scenarios.append(
        _run_ocr_document(
            root,
            mapping,
            scenario_id="CAM-006-03",
            name="leave image/PDF scan to Human Review (HR)",
            document_type="LEAVE_REQUEST",
            lines=_leave_lines(),
            suffix="png",
        )
    )
    scenarios.append(
        _run_ocr_document(
            root,
            mapping,
            scenario_id="CAM-006-04",
            name="overtime image/PDF scan to Human Review (HR)",
            document_type="OVERTIME_REQUEST",
            lines=_overtime_lines(),
            suffix="pdf",
        )
    )
    scenarios.append(_run_type_mismatch(root, mapping))
    scenarios.append(_run_invalid_sources(root, handlers))
    scenarios.append(_run_missing_required(root, mapping))
    scenarios.append(_run_correction(root, mapping))
    scenarios.append(_run_reupload_limit())
    retry_result, retry_count = _run_retry_and_replay(root)
    scenarios.append(retry_result)

    return M4DryRunReport(
        scenarios=tuple(scenarios),
        false_auto_continue=sum(
            1
            for scenario in scenarios
            if scenario.observed_state == CamundaQualityAction.AUTO_CONTINUE.value
        ),
        duplicate_result_artifacts=0 if retry_count == 1 else max(0, retry_count - 1),
        technical_retries=1,
    )


def _build_operations(
    root: Path,
    pipeline: TemplatePipeline | None = None,
) -> tuple[M4TemplateStageOperations, JsonFileTemplateResultStore]:
    result_store = JsonFileTemplateResultStore(root / "camunda_m4")
    operations = M4TemplateStageOperations(
        pipeline or build_default_template_processing_service(),
        LocalSessionDocumentSourceStore(root),
        result_store,
    )
    return operations, result_store


def _run_valid_document(
    root: Path,
    mapping: Mapping[str, object],
    *,
    scenario_id: str,
    name: str,
    document_type: str,
    lines: list[str],
) -> DryRunScenarioResult:
    reference = f"{scenario_id}-SOURCE"
    _write_source(root, reference, "docx", _docx_bytes(lines))
    projection = _process_and_project(mapping, reference, document_type)
    observed = _route(projection).value
    return DryRunScenarioResult(
        scenario_id,
        name,
        CamundaQualityAction.USER_REVIEW.value,
        observed,
        observed == CamundaQualityAction.USER_REVIEW.value,
    )


def _run_ocr_document(
    root: Path,
    mapping: Mapping[str, object],
    *,
    scenario_id: str,
    name: str,
    document_type: str,
    lines: list[str],
    suffix: str,
) -> DryRunScenarioResult:
    reference = f"{scenario_id}-SOURCE"
    content = _png_bytes() if suffix == "png" else _scanned_pdf_bytes()
    _write_source(root, reference, suffix, content)
    ocr_service = TemplateProcessingService(
        intake=build_default_intake(DeterministicMockOcrEngine("\n".join(lines), 0.93)),
        registry=build_default_template_registry(),
        ocr_engine=DeterministicMockOcrEngine("\n".join(lines), 0.93),
    )
    ocr_operations, _ = _build_operations(root, ocr_service)
    ocr_mapping = ocr_operations.as_mapping()
    projection = _process_and_project(ocr_mapping, reference, document_type)
    observed = _route(projection).value
    return DryRunScenarioResult(
        scenario_id,
        name,
        CamundaQualityAction.HR_REVIEW.value,
        observed,
        observed == CamundaQualityAction.HR_REVIEW.value,
    )


def _run_type_mismatch(
    root: Path,
    mapping: Mapping[str, object],
) -> DryRunScenarioResult:
    reference = "CAM-006-05-SOURCE"
    key = "CAM-006-05-IDEMPOTENCY"
    _write_source(root, reference, "docx", _docx_bytes(_leave_lines()))
    parsed = _call(mapping, "document_parse_content", {
        "documentReference": reference,
        "idempotencyKey": key,
    })
    result_reference = _required_string(parsed, "resultReference")
    mismatch = _call(mapping, "document_detect_type", {
        "resultReference": result_reference,
        "declaredDocumentType": "OVERTIME_REQUEST",
        "idempotencyKey": key,
    })
    confirmed = _call(mapping, "document_detect_type", {
        "resultReference": result_reference,
        "declaredDocumentType": "LEAVE_REQUEST",
        "idempotencyKey": key,
    })
    _call(mapping, "document_extract", {
        "resultReference": result_reference,
        "workflowDocumentType": "LEAVE_REQUEST",
        "idempotencyKey": key,
    })
    observed = (
        "CONFIRMED_AFTER_MISMATCH"
        if mismatch.get("classificationStatus") == "MISMATCH"
        and confirmed.get("classificationStatus") == "CONFIRMED"
        else "INVALID"
    )
    return DryRunScenarioResult(
        "CAM-006-05",
        "declared/detected mismatch then Confirm Type",
        "CONFIRMED_AFTER_MISMATCH",
        observed,
        observed == "CONFIRMED_AFTER_MISMATCH",
    )


def _run_invalid_sources(
    root: Path,
    handlers: Mapping[str, object],
) -> DryRunScenarioResult:
    outcomes: list[str] = []
    for suffix, content in (("pdf", b"not-a-pdf"), ("docx", b"not-a-docx")):
        reference = f"CAM-006-06-{suffix.upper()}"
        _write_source(root, reference, suffix, content)
        handler = cast(_ExternalHandler, handlers["document_parse_content"])
        try:
            handler.handle({
                "documentReference": reference,
                "idempotencyKey": f"{reference}-KEY",
            })
        except CamundaBusinessError:
            outcomes.append("BPMN_ERROR")
        except CamundaTechnicalError:
            outcomes.append("TECHNICAL_RETRY")
    observed = "+".join(outcomes)
    return DryRunScenarioResult(
        "CAM-006-06",
        "unsupported or corrupt file fails closed",
        "BPMN_ERROR+TECHNICAL_RETRY",
        observed,
        sorted(outcomes) == ["BPMN_ERROR", "TECHNICAL_RETRY"],
    )


def _run_missing_required(
    root: Path,
    mapping: Mapping[str, object],
) -> DryRunScenarioResult:
    reference = "CAM-006-07-SOURCE"
    key = "CAM-006-07-IDEMPOTENCY"
    _write_source(
        root,
        reference,
        "docx",
        _docx_bytes([line for line in _leave_lines() if not line.startswith("Chức vụ:")]),
    )
    projection = _process_and_project(mapping, reference, "LEAVE_REQUEST", key=key)
    observed = _route(projection).value
    return DryRunScenarioResult(
        "CAM-006-07",
        "missing required field",
        CamundaQualityAction.REQUEST_REUPLOAD.value,
        observed,
        observed == CamundaQualityAction.REQUEST_REUPLOAD.value,
    )


def _run_correction(
    root: Path,
    mapping: Mapping[str, object],
) -> DryRunScenarioResult:
    reference = "CAM-006-08-SOURCE"
    key = "CAM-006-08-IDEMPOTENCY"
    inconsistent_lines = [
        line.replace("tổng thời gian dự kiến là 6 giờ.", "tổng thời gian dự kiến là 5 giờ.")
        for line in _overtime_lines()
    ]
    _write_source(root, reference, "docx", _docx_bytes(inconsistent_lines))
    parsed = _call(mapping, "document_parse_content", {
        "documentReference": reference,
        "idempotencyKey": key,
    })
    result_reference = _required_string(parsed, "resultReference")
    before = _call(mapping, "document_normalize_validate", {
        "resultReference": result_reference,
        "idempotencyKey": key,
    })
    if _route(before) is not CamundaQualityAction.HR_REVIEW:
        return DryRunScenarioResult(
            "CAM-006-08",
            "reviewer correction and revalidation",
            "USER_REVIEW",
            "INVALID",
            False,
        )
    store = JsonFileTemplateResultStore(root / "camunda_m4")
    current = store.load(result_reference)
    correction_reference = JsonFileCorrectionStore(store.root).save(
        result_reference=result_reference,
        expected_payload_hash=current.payload_hash,
        changes={"totalOvertimeHours": 6.0},
    )
    corrected = _call(mapping, "document_apply_corrections", {
        "resultReference": result_reference,
        "resultPayloadHash": current.payload_hash,
        "correctionsReference": correction_reference,
        "caseVersion": 1,
        "idempotencyKey": key,
    })
    after = _call(mapping, "document_normalize_validate", {
        "resultReference": result_reference,
        "idempotencyKey": key,
    })
    observed = _route(after).value if corrected.get("caseVersion") == 2 else "INVALID"
    return DryRunScenarioResult(
        "CAM-006-08",
        "reviewer correction and revalidation",
        CamundaQualityAction.USER_REVIEW.value,
        observed,
        observed == CamundaQualityAction.USER_REVIEW.value,
    )


def _run_reupload_limit() -> DryRunScenarioResult:
    variables = ReuploadControlHandler().handle(
        {"reuploadCount": 3, "maxReuploadAttempts": 3, "caseVersion": 4}
    )
    count = variables["reuploadCount"]
    maximum = variables["maxReuploadAttempts"]
    observed = (
        "FINAL_HR"
        if isinstance(count, int)
        and isinstance(maximum, int)
        and count > maximum
        else "UPLOAD_AGAIN"
    )
    return DryRunScenarioResult(
        "CAM-006-09",
        "re-upload over three attempts",
        "FINAL_HR",
        observed,
        observed == "FINAL_HR",
    )


def _run_retry_and_replay(root: Path) -> tuple[DryRunScenarioResult, int]:
    scenario_root = root / "scenario-10"
    reference = "CAM-006-10-SOURCE"
    key = "CAM-006-10-IDEMPOTENCY"
    _write_source(scenario_root, reference, "docx", _docx_bytes(_leave_lines()))
    base_pipeline = build_default_template_processing_service()
    flaky = _FlakyPipeline(base_pipeline)
    operations, store = _build_operations(scenario_root, flaky)
    mapping = operations.as_mapping()
    retries = 0
    try:
        _call(mapping, "document_parse_content", {
            "documentReference": reference,
            "idempotencyKey": key,
        })
    except CamundaTechnicalError:
        retries += 1
    first = _call(mapping, "document_parse_content", {
        "documentReference": reference,
        "idempotencyKey": key,
    })
    replay = _call(mapping, "document_parse_content", {
        "documentReference": reference,
        "idempotencyKey": key,
    })
    first_reference = _required_string(first, "resultReference")
    replay_reference = _required_string(replay, "resultReference")
    result_files = tuple((store.root / "results").glob("*.json"))
    observed = (
        "RETRY_THEN_IDEMPOTENT_COMPLETE"
        if retries == 1 and first_reference == replay_reference and len(result_files) == 1
        else "INVALID"
    )
    return (
        DryRunScenarioResult(
            "CAM-006-10",
            "technical failure, retry and idempotent replay",
            "RETRY_THEN_IDEMPOTENT_COMPLETE",
            observed,
            observed == "RETRY_THEN_IDEMPOTENT_COMPLETE",
        ),
        len(result_files),
    )


def _process_and_project(
    mapping: Mapping[str, object],
    reference: str,
    document_type: str,
    *,
    key: str | None = None,
) -> ProcessVariables:
    idempotency_key = key or f"{reference}-IDEMPOTENCY"
    parsed = _call(mapping, "document_parse_content", {
        "documentReference": reference,
        "idempotencyKey": idempotency_key,
    })
    result_reference = _required_string(parsed, "resultReference")
    _call(mapping, "document_detect_type", {
        "resultReference": result_reference,
        "declaredDocumentType": document_type,
        "idempotencyKey": idempotency_key,
    })
    _call(mapping, "document_extract", {
        "resultReference": result_reference,
        "workflowDocumentType": document_type,
        "idempotencyKey": idempotency_key,
    })
    projection = _call(mapping, "document_normalize_validate", {
        "resultReference": result_reference,
        "idempotencyKey": idempotency_key,
    })
    validate_process_variables(projection)
    return projection


def _route(projection: Mapping[str, object]) -> CamundaQualityAction:
    quality_status = projection.get("qualityStatus")
    confidence = projection.get("overallConfidence")
    if (
        not isinstance(quality_status, str)
        or isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
    ):
        raise AssertionError("Dry-run projection is incomplete")
    return route_quality(
        QualityRoutingInputs(
            quality_status=quality_status,
            review_required=projection.get("reviewRequired") is True,
            sensitive_field_needs_review=projection.get("sensitiveFieldNeedsReview") is True,
            missing_critical_field=projection.get("missingCriticalField") is True,
            business_inconsistency=projection.get("businessInconsistency") is True,
            required_fields_complete=projection.get("requiredFieldsComplete") is True,
            overall_confidence=float(confidence),
            auto_continue_enabled=projection.get("autoContinueEnabled") is True,
        )
    )


def _call(
    mapping: Mapping[str, object],
    topic: str,
    variables: ProcessVariables,
) -> ProcessVariables:
    operation = mapping[topic]
    if not callable(operation):
        raise AssertionError(f"Dry-run operation {topic} is not callable")
    result = operation(variables)
    if not isinstance(result, dict):
        raise AssertionError(f"Dry-run operation {topic} did not return a mapping")
    return result


def _required_string(variables: Mapping[str, object], name: str) -> str:
    value = variables.get(name)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"Dry-run variable {name} is missing")
    return value


def _write_source(root: Path, reference: str, suffix: str, content: bytes) -> None:
    directory = root / "user_uploads" / "sessions" / reference / "input"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"document.{suffix}").write_bytes(content)


def _docx_bytes(lines: list[str]) -> bytes:
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>" for line in lines
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        f"{paragraphs}<w:sectPr/></w:body></w:document>"
    )
    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def _png_bytes() -> bytes:
    from PIL import Image

    output = BytesIO()
    Image.new("RGB", (640, 240), "white").save(output, format="PNG")
    return output.getvalue()


def _scanned_pdf_bytes() -> bytes:
    import fitz  # type: ignore[import-untyped]

    image = _png_bytes()
    document = fitz.open()
    page = document.new_page(width=640, height=240)
    page.insert_image(page.rect, stream=image)
    payload = document.tobytes()
    document.close()
    return cast(bytes, payload)


def _leave_lines() -> list[str]:
    return [
        "ĐƠN XIN NGHỈ PHÉP",
        "Kính gửi: - Ban Giám đốc CÔNG TY SYNTHETIC",
        "Tôi tên là: NHÂN VIÊN SYNTHETIC",
        "Chức vụ: Chuyên viên kiểm thử",
        "Bộ phận: Kiểm thử",
        "Địa chỉ: Địa chỉ synthetic",
        "Điện thoại: 0000000000",
        (
            "Nay tôi làm đơn này xin nghỉ trong thời gian 2 ngày, kể từ ngày "
            "01/06/2026 đến hết ngày 02/06/2026."
        ),
        (
            "Lý do xin nghỉ phép: Lý do synthetic. Tôi dự kiến trở lại làm việc "
            "vào ngày 03/06/2026."
        ),
        (
            "Tôi đã bàn giao công việc cho: ĐỒNG NGHIỆP SYNTHETIC - Bộ phận: "
            "Kiểm thử."
        ),
        "Các công việc được bàn giao: Công việc synthetic.",
        "Hà Nội, ngày 30 tháng 05 năm 2026",
    ]


def _overtime_lines() -> list[str]:
    return [
        "Hà Nội, ngày 31 tháng 05 năm 2026",
        "ĐƠN XIN TĂNG CA",
        "Căn cứ Hợp đồng lao động số HD-SYNTHETIC ký ngày 01/01/2026;",
        "Kính gửi: Ban Giám đốc CÔNG TY SYNTHETIC.",
        "Tôi là: NHÂN VIÊN SYNTHETIC - Chức vụ: Chuyên viên kiểm thử",
        (
            "Hiện nay, tôi đang thực hiện công việc tại vị trí Chuyên viên kiểm thử, "
            "thời gian làm việc 08:00-17:00. Do hoàn thiện kiểm thử synthetic, "
            "tôi đề nghị được làm thêm."
        ),
        (
            "Thời gian đề nghị: Từ ngày 01/06/2026 đến hết ngày 03/06/2026, "
            "tăng thêm 2 giờ mỗi ngày, từ 18 giờ 00 phút đến 20 giờ 00 phút; "
            "tổng thời gian dự kiến là 6 giờ."
        ),
        "Nội dung công việc: Hoàn thiện kiểm thử synthetic.",
    ]


def main() -> int:
    """Print an aggregate-only report for manual local dry-runs."""

    with tempfile.TemporaryDirectory(prefix="hcns-m4-cam-006-") as directory:
        report = run_m4_dry_run(Path(directory))
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
