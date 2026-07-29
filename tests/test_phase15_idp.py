from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from apps.ocr_lab.api.phase15_idp import (
    BUSINESS_SCHEMA_BY_FAMILY,
    DOCUMENT_FAMILIES,
    FAMILY_FIELD_SCHEMAS,
    IDP_PARSER_VERSION,
    build_phase15_business_json,
    classify_phase15_document,
    extract_phase15_document,
)

_ROOT = Path(__file__).resolve().parents[1]


def canonical_document(
    lines: list[str],
    *,
    source_format: str = "PDF",
    source_kind: str = "pdf_text_layer",
) -> dict[str, Any]:
    blocks = [
        {
            "blockIndex": index,
            "text": line,
            "sourceKind": source_kind,
            "confidence": 1.0,
            "evidence": {
                "pageIndex": 0,
                "sourceRef": f"synthetic:line:{index}",
                "bbox": None,
            },
        }
        for index, line in enumerate(lines)
    ]
    return {
        "schemaVersion": "1.0.0",
        "sourceFormat": source_format,
        "adapter": "synthetic_native",
        "ingestionMode": "NATIVE",
        "pageCount": 1,
        "pages": [
            {
                "pageIndex": 0,
                "ingestionMode": "native",
                "blocks": blocks,
                "nativeBlocks": blocks,
                "ocrBlocks": [],
            }
        ],
        "tables": [],
        "plainText": "\n".join(lines),
        "metadata": {},
    }


class Phase15ClassificationTests(unittest.TestCase):
    def test_classifies_the_five_hr_document_families(self) -> None:
        cases = (
            (
                ["CURRICULUM VITAE", "HỌC VẤN", "KỸ NĂNG"],
                "CV",
                "CV",
            ),
            (
                ["PHIẾU ĐĂNG KÝ LÀM THÊM GIỜ", "Mã nhân viên: SYN-001"],
                "OVERTIME_REQUEST",
                "ADMINISTRATIVE_REQUEST",
            ),
            (
                ["HỢP ĐỒNG THỬ VIỆC", "Thời gian thử việc: SYNTHETIC"],
                "PROBATION_AGREEMENT",
                "CONTRACT_DECISION",
            ),
            (
                ["BẰNG TỐT NGHIỆP", "Số hiệu văn bằng: SYN-001"],
                "DEGREE_CERTIFICATE",
                "DEGREE_CERTIFICATE",
            ),
            (
                ["CHECKLIST TIẾP NHẬN NHÂN VIÊN MỚI"],
                "ONBOARDING_CHECKLIST",
                "EMPLOYEE_FORM_TABLE",
            ),
        )

        for lines, expected_type, expected_family in cases:
            with self.subTest(expected_type=expected_type):
                result = classify_phase15_document(canonical_document(lines))
                self.assertEqual(expected_type, result["documentType"])
                self.assertEqual(expected_family, result["documentFamily"])
                self.assertIn(expected_family, DOCUMENT_FAMILIES)

    def test_unknown_document_stays_reviewable(self) -> None:
        result = classify_phase15_document(
            canonical_document(["NỘI DUNG SYNTHETIC KHÔNG XÁC ĐỊNH"])
        )

        self.assertEqual("OTHER_HR_DOCUMENT", result["documentFamily"])
        self.assertEqual("needs_review", result["status"])


class Phase15ExtractionTests(unittest.TestCase):
    def test_timesheet_uses_dedicated_fields_and_preserves_daily_cells(
        self,
    ) -> None:
        canonical = canonical_document(
            [
                "BẢNG CHẤM CÔNG THÁNG 08/2099",
                "CÔNG TY SYNTHETIC",
            ],
            source_format="XLSX",
            source_kind="xlsx_cells",
        )
        columns = [
            "TT",
            "Mã NV",
            "Họ và tên",
            "Chức vụ/Bộ phận",
            "1",
            "2",
            "Tổng cộng ngày công",
        ]
        canonical["tables"] = [
            {
                "tableIndex": 0,
                "sourceKind": "xlsx_cells",
                "columns": [
                    {"columnIndex": index, "name": name}
                    for index, name in enumerate(columns)
                ],
                "rows": [
                    {
                        "rowIndex": 1,
                        "values": [
                            1,
                            "SYN001",
                            "Nhân viên mẫu",
                            "Phòng thử nghiệm",
                            "X",
                            "P",
                            1.5,
                        ],
                        "cells": [
                            {
                                "status": "accepted",
                                "evidence": {
                                    "sheetName": "Synthetic",
                                    "rowIndex": 1,
                                    "columnIndex": index,
                                },
                            }
                            for index in range(len(columns))
                        ],
                    }
                ],
            }
        ]
        classification = {
            "documentType": "TIMESHEET",
            "documentFamily": "EMPLOYEE_FORM_TABLE",
        }

        extraction = extract_phase15_document(canonical, classification)

        self.assertEqual(
            {"timesheetPeriod", "totalEmployees", "companyName"},
            set(extraction["fields"]),
        )
        self.assertEqual(1, len(extraction["tables"]))
        self.assertEqual(
            "SYN001",
            extraction["tables"][0]["rows"][0]["values"][0],
        )
        self.assertEqual(
            "phase17-structured-hr-parser/2.0.0",
            extraction["parserVersion"],
        )

    def test_ocr_sensitive_field_is_never_automatically_accepted(
        self,
    ) -> None:
        canonical = canonical_document(
            [
                "PHIẾU THÔNG TIN NHÂN VIÊN",
                "Họ và tên: NHÂN VIÊN SYNTHETIC",
            ],
            source_format="IMAGE",
            source_kind="ocr",
        )
        classification = {
            "documentType": "EMPLOYEE_INFORMATION_FORM",
            "documentFamily": "EMPLOYEE_FORM_TABLE",
        }

        extraction = extract_phase15_document(canonical, classification)

        field = extraction["fields"]["employeeName"]
        self.assertEqual("needs_review", field["status"])
        self.assertEqual(
            "sensitive_ocr_requires_human_review",
            field["reviewReason"],
        )
        self.assertFalse(extraction["summary"]["readyForAutomaticUse"])

    def test_cv_extracts_evidence_bearing_fields(self) -> None:
        canonical = canonical_document(
            [
                "CURRICULUM VITAE",
                "NHÂN VIÊN SYNTHETIC",
                "Email: synthetic@example.test",
                "Điện thoại: 0900000000",
                "HỌC VẤN",
                "Chương trình kiểm thử",
                "KINH NGHIỆM LÀM VIỆC",
                "Dự án kiểm thử",
                "KỸ NĂNG",
                "Kiểm thử tài liệu",
            ]
        )
        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)

        self.assertEqual(IDP_PARSER_VERSION, extraction["parserVersion"])
        self.assertEqual(
            set(FAMILY_FIELD_SCHEMAS["CV"]),
            set(extraction["fields"]),
        )
        self.assertEqual(
            "synthetic@example.test",
            extraction["fields"]["email"]["value"],
        )
        for field in extraction["fields"].values():
            if field["value"] is not None:
                self.assertIsNotNone(field["evidence"])

    def test_ocr_values_remain_review_only_below_threshold(self) -> None:
        canonical = canonical_document(
            [
                "PHIẾU THÔNG TIN NHÂN VIÊN",
                "Họ và tên: NHÂN VIÊN SYNTHETIC",
            ],
            source_kind="ocr",
        )
        canonical["pages"][0]["blocks"][1]["confidence"] = 0.80
        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)

        self.assertEqual(
            "needs_review",
            extraction["fields"]["employeeName"]["status"],
        )

    def test_hr_decision_uses_article_evidence_without_bare_employee_id(self) -> None:
        canonical = canonical_document(
            [
                "QUYẾT ĐỊNH BỔ NHIỆM",
                "Số: 35/2026/QĐ-NS-SYN",
                "Về việc bổ nhiệm chức danh Trưởng nhóm dữ liệu",
                (
                    "Điều 1. Bổ nhiệm bà Nhân Viên Mẫu, mã nhân viên "
                    "EMP.0042, giữ chức danh Trưởng nhóm dữ liệu."
                ),
                "Quyết định có hiệu lực từ ngày 01/09/2026.",
            ],
            source_kind="ocr",
        )
        for block in canonical["pages"][0]["blocks"]:
            block["confidence"] = 0.82

        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)
        fields = extraction["fields"]

        self.assertEqual("HR_DECISION", classification["documentType"])
        self.assertEqual("35/2026/QĐ-NS-SYN", fields["documentNumber"]["value"])
        self.assertEqual("Nhân Viên Mẫu", fields["employeeName"]["value"])
        self.assertEqual("EMP-0042", fields["employeeId"]["normalizedValue"])
        self.assertEqual(
            "Về việc bổ nhiệm chức danh Trưởng nhóm dữ liệu",
            fields["action"]["value"],
        )
        self.assertEqual("01/09/2026", fields["effectiveDate"]["value"])
        self.assertTrue(
            all(
                field["status"] == "needs_review"
                for field in fields.values()
                if field["value"] is not None
            )
        )

    def test_hr_decision_rejects_incomplete_employee_id(self) -> None:
        canonical = canonical_document(
            [
                "QUYẾT ĐỊNH ĐIỀU CHUYỂN NHÂN SỰ",
                "Điều chuyển ông Nhân Viên Mẫu, mã nhân viên EMP, kể từ nay.",
            ],
            source_kind="ocr",
        )

        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)

        self.assertIsNone(extraction["fields"]["employeeId"]["value"])
        self.assertEqual(
            "not_found",
            extraction["fields"]["employeeId"]["status"],
        )

    def test_contract_reads_scalar_values_from_separate_blocks(self) -> None:
        canonical = canonical_document(
            [
                "HỢP ĐỒNG LAO ĐỘNG",
                "Số: 18/2026/HĐLĐ-SYN",
                "Người lao động:",
                "Nhân Viên Mẫu",
                "Công việc/Chức danh:",
                "Kỹ sư AI ứng dụng",
                "Mức lương cơ bản:",
                "24.000.000 đồng/tháng",
                "Ngày bắt đầu:",
                "15/08/2026",
                "Ngày kết thúc:",
                "14/08/2028",
            ]
        )

        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)
        fields = extraction["fields"]

        self.assertEqual("EMPLOYMENT_CONTRACT", classification["documentType"])
        self.assertEqual("Nhân Viên Mẫu", fields["employeeName"]["value"])
        self.assertEqual("Kỹ sư AI ứng dụng", fields["jobTitle"]["value"])
        self.assertEqual("24.000.000 đồng/tháng", fields["salary"]["value"])
        self.assertEqual("15/08/2026", fields["startDate"]["value"])
        self.assertEqual("14/08/2028", fields["endDate"]["value"])

    def test_degree_uses_structural_markers_and_bounded_metadata(self) -> None:
        canonical = canonical_document(
            [
                "TRƯỜNG ĐẠI HỌC KIỂM THỬ",
                "BẰNG CỬ NHÂN",
                "Trân trọng chứng nhận",
                "NHÂN VIÊN MẪU",
                "đã hoàn thành và đáp ứng yêu cầu của",
                "CÔNG NGHỆ THÔNG TIN",
                (
                    "Trình độ: Đại học / Ngành: Công nghệ thông tin / "
                    "Xếp loại: Khá"
                ),
                "Ngày cấp: Hà Nội, ngày 20/06/2026",
                "Số hiệu/Mã chứng nhận: SYN-001",
            ]
        )

        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)
        fields = extraction["fields"]

        self.assertEqual("DEGREE_CERTIFICATE", classification["documentType"])
        self.assertEqual("NHÂN VIÊN MẪU", fields["recipientName"]["value"])
        self.assertEqual("BẰNG CỬ NHÂN", fields["credentialType"]["value"])
        self.assertEqual(
            "TRƯỜNG ĐẠI HỌC KIỂM THỬ",
            fields["issuingOrganization"]["value"],
        )
        self.assertEqual("Công nghệ thông tin", fields["fieldOfStudy"]["value"])
        self.assertEqual("Đại học", fields["degreeLevel"]["value"])
        self.assertEqual("Khá", fields["classification"]["value"])
        self.assertEqual(
            "Hà Nội, ngày 20/06/2026",
            fields["issueDate"]["value"],
        )
        self.assertEqual("SYN-001", fields["credentialId"]["value"])

    def test_camunda_variables_contain_references_not_raw_payload(self) -> None:
        canonical = canonical_document(
            [
                "PHIẾU ĐĂNG KÝ LÀM THÊM GIỜ",
                "Họ và tên: NHÂN VIÊN SYNTHETIC",
            ]
        )
        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)
        business = build_phase15_business_json(
            "synthetic-document",
            canonical,
            classification,
            extraction,
            contains_real_pii=False,
        )

        variables = business["camunda"]["variables"]
        self.assertEqual("phase15/idp_result.json", variables["resultReference"])
        self.assertNotIn("idpPayload", variables)
        self.assertNotIn("fields", variables)
        self.assertIn("fields", business["payload"])
        self.assertEqual(
            IDP_PARSER_VERSION,
            business["payload"]["parserVersion"],
        )

    def test_employee_table_is_rebuilt_from_ocr_coordinates(self) -> None:
        canonical = canonical_document(
            [
                "CHECKLIST TIẾP NHẬN NHÂN VIÊN MỚI",
                "STT",
                "Hạng mục",
                "Phụ trách",
                "Trạng thái",
                "1",
                "Tạo tài khoản",
                "CNTT",
                "Hoàn tất",
                "2",
                "Bàn giao tài sản",
                "Hành chính",
                "Chờ xử lý",
            ],
            source_kind="ocr",
        )
        coordinates = (
            (10, 10),
            (10, 100),
            (110, 100),
            (310, 100),
            (460, 100),
            (10, 150),
            (110, 150),
            (310, 150),
            (460, 150),
            (10, 200),
            (110, 200),
            (310, 200),
            (460, 200),
        )
        for block, (left, top) in zip(
            canonical["pages"][0]["blocks"],
            coordinates,
            strict=True,
        ):
            block["evidence"]["bbox"] = [
                [left, top],
                [left + 90, top],
                [left + 90, top + 24],
                [left, top + 24],
            ]
        canonical["pages"][0]["ocrBlocks"] = canonical["pages"][0]["blocks"]
        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)

        self.assertEqual("ONBOARDING_CHECKLIST", classification["documentType"])
        self.assertEqual(1, len(extraction["tables"]))
        self.assertEqual(2, extraction["tables"][0]["summary"]["rowCount"])


class Phase15SchemaTests(unittest.TestCase):
    def test_each_family_has_a_checked_in_schema(self) -> None:
        for family in DOCUMENT_FAMILIES:
            with self.subTest(family=family):
                relative = BUSINESS_SCHEMA_BY_FAMILY[family]
                schema_path = _ROOT / relative
                self.assertTrue(schema_path.is_file())
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                self.assertEqual(family, schema["properties"]["documentFamily"]["const"])


if __name__ == "__main__":
    unittest.main()
