from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path

import pytest
from jsonschema import validate
from synthetic_fixtures import (
    administrative_image_bytes,
    make_ooxml_zip,
    scanned_pdf_bytes,
)

from hcns_agent.adapters.camunda7.contract import (
    CamundaWorkflowDocumentType,
    map_document_type,
)
from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.adapters.paddleocr import PaddleOcrEngine
from hcns_agent.bootstrap import build_default_intake
from hcns_agent.domain.documents import DocumentType
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.ports.ocr import OcrLine, OcrPage, OcrResult
from hcns_agent.templates.common import (
    ocr_line_value,
    repair_template_ocr_value,
    trim_ocr_commitment,
)
from hcns_agent.templates.registry import build_default_template_registry
from hcns_agent.templates.service import (
    TemplateProcessingService,
    TemplateTechnicalError,
    TemplateUnsupportedError,
    _LazyTemplateEasyOcrEngine,
    _LazyTemplatePaddleOcrEngine,
    build_default_template_processing_service,
)

ROOT = Path(__file__).resolve().parents[1]


def docx_bytes(lines: list[str]) -> bytes:
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>" for line in lines
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        f"{paragraphs}<w:sectPr/></w:body></w:document>"
    )
    return make_ooxml_zip(
        {
            "[Content_Types].xml": (
                '<Types xmlns="http://schemas.openxmlformats.org/'
                'package/2006/content-types"/>'
            ),
            "word/document.xml": document_xml,
        }
    )


def leave_lines() -> list[str]:
    return [
        "ĐƠN XIN NGHỈ PHÉP",
        "Kính gửi: - Ban Giám đốc CÔNG TY SYNTHETIC",
        "Tôi tên là: NHÂN VIÊN SYNTHETIC",
        "Chức vụ: Chuyên viên kiểm thử",
        "Bộ phận: Kiểm thử",
        "Địa chỉ: Địa chỉ synthetic",
        "Điện thoại: 0000000000",
        (
            "Nay tôi làm đơn này xin nghỉ trong thời gian 2 ngày, "
            "kể từ ngày 01/06/2026 đến hết ngày 02/06/2026."
        ),
        (
            "Lý do xin nghỉ phép: Lý do synthetic. "
            "Tôi dự kiến trở lại làm việc vào ngày 03/06/2026."
        ),
        (
            "Tôi đã bàn giao công việc cho: ĐỒNG NGHIỆP SYNTHETIC "
            "- Bộ phận: Kiểm thử."
        ),
        "Các công việc được bàn giao: Công việc synthetic.",
        "Hà Nội, ngày 30 tháng 05 năm 2026",
    ]


def overtime_lines() -> list[str]:
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


def overtime_single_day_lines() -> list[str]:
    return [
        "Hà Nội, ngày 13 tháng 08 năm 2026",
        "ĐƠN XIN TĂNG CA",
        "Căn cứ Hợp đồng lao động số HD-SINGLE-DAY ký ngày 01/01/2026;",
        "Kính gửi: Ban Giám đốc CÔNG TY SYNTHETIC.",
        "Tôi là: NHÂN VIÊN SYNTHETIC - Chức vụ: Kỹ thuật viên",
        (
            "Hiện nay, tôi đang thực hiện công việc tại vị trí Kỹ thuật viên, "
            "thời gian làm việc 08:00-17:00. Do hoàn thiện kiểm thử synthetic, "
            "tôi đề nghị được làm thêm."
        ),
        (
            "Thời gian đề nghị: Ngày 14/08/2026, làm thêm 3 giờ, từ 18 giờ 00 phút "
            "đến 21 giờ 00 phút; tổng thời gian dự kiến là 3 giờ."
        ),
        "Nội dung công việc: Hoàn thiện kiểm thử synthetic.",
    ]


def ielts_lines() -> list[str]:
    return [
        "IELTS",
        "TEST REPORT FORM",
        "Candidate name: CANDIDATE SYNTHETIC",
        "TRF number: SYNTHETIC-TRF-001",
        "Test type: Academic",
        "Overall band score: 7.5",
        "Date of test: 01/08/2026",
    ]


def process(lines: list[str], filename: str = "opaque-upload.docx") -> dict[str, object]:
    service = build_default_template_processing_service()
    return service.process(
        DocumentSource(
            document_id="SYNTHETIC-DOCUMENT",
            filename=filename,
            content=docx_bytes(lines),
            declared_media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        )
    ).public_dict()


def test_registry_lists_six_approved_templates() -> None:
    templates = build_default_template_processing_service().list_templates()

    assert [template["templateId"] for template in templates] == [
        "cv-v2",
        "ielts-certificate-v2",
        "leave-request-v1",
        "overtime-request-v1",
        "probation-contract-v2",
        "vietnam-citizen-id-front-v1",
    ]
    assert templates[0]["supportedFileTypes"] == ["docx", "pdf"]
    assert templates[1]["supportedFileTypes"] == ["pdf", "png", "jpg", "jpeg"]
    assert templates[2]["supportedFileTypes"] == templates[0]["supportedFileTypes"]
    assert all(template["lifecycle"] == "FROZEN" for template in templates)
    parser_versions = {
        template["templateId"]: template["parserVersion"] for template in templates
    }
    assert parser_versions["leave-request-v1"] == "1.0.0"
    assert parser_versions["overtime-request-v1"] == "1.1.0"


def test_leave_template_is_filename_independent_and_schema_valid() -> None:
    response = process(leave_lines(), filename="unrelated-name.docx")
    data = response["data"]
    assert isinstance(data, dict)

    assert response["documentType"] == "LEAVE_REQUEST"
    assert data["employeeName"] == "NHÂN VIÊN SYNTHETIC"
    assert data["requestDate"] == "2026-05-30"
    assert data["startDate"] == "2026-06-01"
    assert data["endDate"] == "2026-06-02"
    assert "formNumber" in data["missingFields"]
    assert "employeeId" in data["missingFields"]
    assert data["recommendedAction"] == "AUTO_CONTINUE"
    schema = json.loads(
        (ROOT / "schemas/templates/leave_request_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validate(data, schema)


def test_cv_template_is_review_first_and_keeps_values_private_from_camunda() -> None:
    response = process(
        [
            "CURRICULUM VITAE",
            "Full name: Candidate Synthetic",
            "Kinh nghiem: QA",
            "Ky nang: Python",
        ]
    )

    assert response["templateId"] == "cv-v2"
    assert response["quality"]["recommendedAction"] == "MANUAL_REVIEW"
    assert response["data"]["full_name"] == "Candidate Synthetic"
    assert "full_name" not in response["camundaVariables"]
    schema = json.loads(
        (ROOT / "schemas/templates/cv_v2.schema.json").read_text(encoding="utf-8")
    )
    validate(response["data"], schema)


def test_probation_contract_detection_ignores_vietnamese_diacritics() -> None:
    response = process(
        [
            "HỢP ĐỒNG THỬ VIỆC",
            "THỜI GIAN THỬ VIỆC: 60 ngày",
            "MỨC LƯƠNG: 10.000.000 đồng",
        ],
        filename="contract.pdf",
    )

    assert response["templateId"] == "probation-contract-v2"
    assert response["documentType"] == "EMPLOYMENT_CONTRACT"
    assert response["quality"]["recommendedAction"] == "MANUAL_REVIEW"


def test_id_front_template_rejects_back_side() -> None:
    service = build_default_template_processing_service()
    with pytest.raises(TemplateUnsupportedError):
        service.process(
            DocumentSource(
                document_id="SYNTHETIC-ID-BACK",
                filename="id.jpg",
                content=docx_bytes(["CAN CUOC CONG DAN", "BACK", "ID NUMBER: 1"]),
            )
        )


@pytest.mark.parametrize("backend", ["easyocr", "paddleocr"])
def test_lazy_ocr_engine_initializes_once_under_concurrency(
    backend: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    calls_lock = threading.Lock()
    result = OcrResult(
        document_id="SYNTHETIC-OCR",
        engine="synthetic",
        pages=(OcrPage(page_index=0, lines=(OcrLine("ok", 1.0),)),),
        duration_ms=0,
    )

    class _FakeDelegate:
        def recognize(self, source: DocumentSource) -> OcrResult:
            return result

    def build_delegate(*, device: str) -> _FakeDelegate:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.02)
        return _FakeDelegate()

    if backend == "easyocr":
        from hcns_agent.adapters.easyocr import EasyOcrEngine

        monkeypatch.setattr(
            EasyOcrEngine,
            "from_default",
            classmethod(lambda cls, *, device: build_delegate(device=device)),
        )
        engine = _LazyTemplateEasyOcrEngine()
    else:
        monkeypatch.setattr(
            PaddleOcrEngine,
            "from_default",
            classmethod(lambda cls, *, device: build_delegate(device=device)),
        )
        engine = _LazyTemplatePaddleOcrEngine()

    source = DocumentSource(
        document_id="SYNTHETIC-OCR",
        filename="synthetic.png",
        content=b"synthetic",
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(engine.recognize, [source] * 8))

    assert calls == 1
    assert results == [result] * 8
def test_overtime_template_parses_and_normalizes_time() -> None:
    response = process(overtime_lines())
    data = response["data"]
    assert isinstance(data, dict)

    assert response["documentType"] == "OVERTIME_REQUEST"
    assert data["startDate"] == "2026-06-01"
    assert data["endDate"] == "2026-06-03"
    assert data["overtimeStartTime"] == "18:00"
    assert data["overtimeEndTime"] == "20:00"
    assert data["overtimeHoursPerDay"] == 2
    assert data["totalOvertimeHours"] == 6


def test_overtime_template_parses_single_day_dataset_format() -> None:
    response = process(overtime_single_day_lines())
    data = response["data"]

    assert response["templateId"] == "overtime-request-v1"
    assert data["startDate"] == "2026-08-14"
    assert data["endDate"] == "2026-08-14"
    assert data["overtimeHoursPerDay"] == 3
    assert data["overtimeStartTime"] == "18:00"
    assert data["overtimeEndTime"] == "21:00"
    assert data["totalOvertimeHours"] == 3
    assert data["validationErrors"] == []
    assert data["recommendedAction"] == "AUTO_CONTINUE"
    schema = json.loads(
        (ROOT / "schemas/templates/overtime_request_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validate(data, schema)


def test_overtime_parser_normalizes_wrapped_reason_and_work_content() -> None:
    lines = [
        line.replace(
            "Do hoàn thiện kiểm thử synthetic",
            "Do hoàn thiện\nkiểm thử synthetic",
        ).replace(
            "Nội dung công việc: Hoàn thiện kiểm thử synthetic.",
            (
                "Nội dung công việc: Hoàn thiện kiểm thử\nsynthetic. "
                "Tôi cam kết tuân thủ quy định."
            ),
        )
        for line in overtime_lines()
    ]
    response = process(lines)
    data = response["data"]
    assert isinstance(data, dict)

    assert data["reason"] == "hoàn thiện kiểm thử synthetic"
    assert data["workContent"] == "Hoàn thiện kiểm thử synthetic"


def test_ocr_field_recovery_uses_label_spans_and_fixed_vocab_only() -> None:
    assert (
        ocr_line_value("Chc v Ky su Backend", ("Chức vụ", "Ch.c v."))
        == "Ky su Backend"
    )
    assert (
        repair_template_ocr_value("K sư Backend", "jobTitle")
        == "Kỹ sư Backend"
    )
    assert repair_template_ocr_value("ten tu do", "employeeName") == "ten tu do"
    assert (
        trim_ocr_commitment("Noi dung. Toi cam kt tuan thu quy dinh.")
        == "Noi dung"
    )
    assert trim_ocr_commitment("Lý do hợp lệ. Tôi dự kiến trở lại") == "Lý do hợp lệ"
    assert repair_template_ocr_value("Phòng Hành chính Nhân sựự", "department") == (
        "Phòng Hành chính Nhân sự"
    )


def test_leave_reason_drops_preceding_period_when_label_shares_ocr_line() -> None:
    response = process(
        [
            "Nay tôi làm đơn xin nghỉ phép trong thời gian 02 ngày.",
            (
                "02 ngày, từ ngày 03/08/2026 đến hết ngày 04/08/2026. "
                "Lý do xin nghỉ phép: Đưa con nhập học."
            ),
        ],
        filename="camera.png",
    )
    data = response["data"]
    assert isinstance(data, dict)
    assert data["reason"] == "Đưa con nhập học"


def test_missing_required_field_routes_to_manual_review_without_inference() -> None:
    lines = [line for line in leave_lines() if not line.startswith("Chức vụ:")]
    response = process(lines)
    data = response["data"]
    assert isinstance(data, dict)

    assert data["jobTitle"] is None
    assert "jobTitle" in data["missingFields"]
    assert data["recommendedAction"] == "MANUAL_REVIEW"


def test_invalid_overtime_total_routes_to_manual_review() -> None:
    lines = [
        line.replace("tổng thời gian dự kiến là 6 giờ", "tổng thời gian dự kiến là 5 giờ")
        for line in overtime_lines()
    ]
    response = process(lines)
    data = response["data"]
    assert isinstance(data, dict)

    assert "TOTAL_OVERTIME_HOURS_CONFLICT" in data["validationErrors"]
    assert data["recommendedAction"] == "MANUAL_REVIEW"


def test_partial_anchor_match_is_review_only() -> None:
    lines = [line for line in leave_lines() if not line.startswith("Tôi đã bàn giao")]
    response = process(lines)
    data = response["data"]
    assert isinstance(data, dict)

    assert "TEMPLATE_ANCHOR_PARTIAL" in data["validationErrors"]
    assert data["recommendedAction"] == "MANUAL_REVIEW"


@pytest.mark.parametrize(
    ("filename", "content_factory"),
    [
        ("synthetic-camera.png", administrative_image_bytes),
        ("synthetic-scan.pdf", scanned_pdf_bytes),
    ],
)
def test_template_ocr_sources_require_manual_review(
    filename: str,
    content_factory: Callable[[], bytes],
) -> None:
    ocr = DeterministicMockOcrEngine(
        text="\n".join(ielts_lines()),
        confidence=0.93,
    )
    service = TemplateProcessingService(
        intake=build_default_intake(ocr),
        registry=build_default_template_registry(),
        ocr_engine=ocr,
    )

    response = service.process(
        DocumentSource(
            document_id="SYNTHETIC-OCR",
            filename=filename,
            content=content_factory(),
            source_reference="object://synthetic/ocr",
        )
    ).public_dict()

    assert response["documentType"] == "CERTIFICATE"
    assert response["quality"]["recommendedAction"] == "MANUAL_REVIEW"
    assert "OCR_REVIEW_REQUIRED" in response["quality"]["validationErrors"]


def test_degraded_overtime_ocr_stays_manual_review() -> None:
    text = "\n".join(
        [
            "Hà Nội, ngày 31 tháng 05 năm 2026",
            "ĐON XIN TĂNG CA",
            "Căn cú Hp đông lao dng sõ HD-01 ký ngày 01/01/2026",
            "Tôi là: Nguyn Hi Yn - Chc v: K sư D liu",
            "Thi gian đ ngh: T ngày 01/06/2026 đn ht ngày 03/06/2026, "
            "tăng thêm 2 gi mi ngày, t 18 gi 00 phút đn 20 gi 00 phút; "
            "tng thi gian d kin là 6 gi.",
            "Ni dung công vic: Chy pipeline OCR.",
            "Tôi cam kt tuân th quy đnh.",
        ]
    )
    ocr = DeterministicMockOcrEngine(text=text, confidence=0.91)
    service = TemplateProcessingService(
        intake=build_default_intake(ocr),
        registry=build_default_template_registry(),
        ocr_engine=ocr,
    )

    response = service.process(
        DocumentSource(
            document_id="SYNTHETIC-DEGRADED-OCR",
            filename="camera-hard.png",
            content=administrative_image_bytes(),
        )
    ).public_dict()

    assert response["documentType"] == "OVERTIME_REQUEST"
    assert response["quality"]["recommendedAction"] == "MANUAL_REVIEW"


def test_detection_normalizes_unicode_case_and_whitespace() -> None:
    lines = [
        line.replace("ĐƠN XIN NGHỈ PHÉP", "đơn   xin nghỉ phép").replace(
            "Lý do xin nghỉ phép",
            "LÝ DO XIN NGHỈ PHÉP",
        )
        for line in leave_lines()
    ]
    response = process(lines)

    assert response["templateId"] == "leave-request-v1"


def test_unsupported_document_is_not_forced_into_a_template() -> None:
    service = build_default_template_processing_service()
    with pytest.raises(TemplateUnsupportedError):
        service.process(
            DocumentSource(
                "SYNTHETIC-UNKNOWN",
                "unknown.docx",
                docx_bytes(["BIỂU MẪU KHÔNG ĐƯỢC HỖ TRỢ"]),
            )
        )


def test_corrupt_docx_has_separate_technical_error() -> None:
    service = build_default_template_processing_service()
    with pytest.raises(TemplateTechnicalError):
        service.process(
            DocumentSource(
                "SYNTHETIC-CORRUPT",
                "corrupt.docx",
                b"not-a-valid-docx",
            )
        )


def test_camunda_projection_contains_no_raw_text_or_extracted_values() -> None:
    response = process(leave_lines())
    data = response["data"]
    variables = response["camundaVariables"]
    assert isinstance(data, dict)
    assert isinstance(variables, dict)

    assert "NHÂN VIÊN SYNTHETIC" not in str(variables)
    assert "Lý do synthetic" not in str(variables)
    assert "extractedDataReference" in variables
    assert set(variables) == {
        "documentType",
        "templateId",
        "templateVersion",
        "extractionStatus",
        "missingFields",
        "validationErrors",
        "recommendedAction",
        "extractedDataReference",
    }
    process_schema = json.loads(
        (ROOT / "schemas/camunda_process_variables.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validate(variables, process_schema)


def test_overtime_document_type_maps_to_camunda_contract() -> None:
    assert (
        map_document_type(DocumentType.OVERTIME_REQUEST)
        is CamundaWorkflowDocumentType.OVERTIME_REQUEST
    )


def test_template_parser_does_not_write_document_values_to_logs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    process(leave_lines())

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
