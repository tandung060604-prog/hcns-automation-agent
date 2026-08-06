from __future__ import annotations

from typing import Any

from apps.ocr_lab.api.external_dataset_prediction import _external_fields, build_aggregate_report
from apps.ocr_lab.api.phase15_idp import classify_phase15_document, extract_phase15_document


def _canonical(lines: list[str]) -> dict[str, Any]:
    blocks = [
        {
            "text": line,
            "sourceKind": "pdf_text_layer",
            "confidence": 1.0,
            "evidence": {"pageIndex": 0, "sourceRef": f"test:{index}", "bbox": None},
        }
        for index, line in enumerate(lines)
    ]
    return {
        "plainText": "\n".join(lines),
        "pages": [{"blocks": blocks, "ocrBlocks": []}],
        "tables": [],
    }


def _ocr_canonical(lines: list[str]) -> dict[str, Any]:
    blocks = []
    for index, line in enumerate(lines):
        y = index * 40
        blocks.append(
            {
                "text": line,
                "sourceKind": "ocr",
                "confidence": 0.94,
                "evidence": {
                    "pageIndex": 0,
                    "sourceRef": f"ocr:{index}",
                    "bbox": [[10, y], [180, y], [180, y + 20], [10, y + 20]],
                },
            }
        )
    return {
        "plainText": "\n".join(lines),
        "pages": [{"blocks": blocks, "ocrBlocks": blocks}],
        "tables": [],
    }


def test_data12_aggregate_is_prediction_scoring_only() -> None:
    prediction = {
        "datasetId": "synthetic-test",
        "documents": [
            {
                "caseId": "cv-001",
                "category": "cv",
                "predictedCategory": "cv",
                "processing": {
                    "usesOcr": True,
                    "recommendedAction": "MANUAL_REVIEW",
                },
                "fields": {
                    name: {"value": value}
                    for name, value in {
                        "full_name": "Synthetic User",
                        "headline": None,
                        "email": None,
                        "phone_number": None,
                        "address": None,
                        "desired_role": None,
                        "years_experience": None,
                        "experience": None,
                        "skills": None,
                        "education": None,
                    }.items()
                },
            }
        ],
    }
    ground_truth = {
        "cases": [
            {
                "caseId": "cv-001",
                "fields": [
                    {"name": "full_name", "value": "Synthetic User"},
                    *[
                        {"name": name, "value": None}
                        for name in (
                            "headline",
                            "email",
                            "phone_number",
                            "address",
                            "desired_role",
                            "years_experience",
                            "experience",
                            "skills",
                            "education",
                        )
                    ],
                ],
            }
        ]
    }

    report = build_aggregate_report(prediction, ground_truth)

    assert report["fieldCount"] == 10
    assert report["metrics"]["fieldExactMatchCount"] == 10
    assert report["schemaErrors"] == 0
    assert report["ocrPolicy"]["falseAutoContinueCount"] == 0
    assert report["containsRawFieldValues"] is False
    assert report["promotionAllowed"] is False


def test_data13_aggregate_excludes_non_ocr_scan_cases() -> None:
    prediction = {
        "datasetId": "synthetic-test",
        "ocrScopePolicy": "cccd-and-certificate-only",
        "documents": [
            {
                "caseId": "cv-scan",
                "category": "cv",
                "sourceFormat": "IMAGE",
                "evaluationIncluded": False,
                "fields": {},
                "processing": {
                    "usesOcr": False,
                    "recommendedAction": "REJECT_UNSUPPORTED",
                },
            }
        ],
    }
    report = build_aggregate_report(prediction, {"cases": []})
    assert report["schemaVersion"] == "external-dataset-data13-aggregate/1.0.0"
    assert report["documentCount"] == 1
    assert report["evaluatedDocumentCount"] == 0
    assert report["policyExcludedDocumentCount"] == 1
    assert report["fieldCount"] == 0
    assert report["ocrPolicy"]["unsupportedNoOcrCount"] == 1


def test_family_mapping_keeps_multiline_cv_and_contract_evidence() -> None:
    cv = _canonical(
        [
            "CURRICULUM VITAE",
            "Họ và tên",
            "NGUYỄN VĂN A",
            "Vị trí ứng tuyển",
            "KỸ SƯ DỮ LIỆU",
            "Địa chỉ",
            "Hà Nội",
            "HỌC VẤN",
            "Đại học Kiểm thử",
            "KINH NGHIỆM LÀM VIỆC",
            "Công ty Synthetic",
            "KỸ NĂNG",
            "Python, SQL",
        ]
    )
    cv_classification = classify_phase15_document(cv)
    cv_extraction = extract_phase15_document(cv, cv_classification)
    cv_fields = _external_fields("cv", cv, cv_extraction, ocr=False)

    assert cv_fields["full_name"]["value"] == "NGUYỄN VĂN A"
    assert cv_fields["headline"]["value"] == "KỸ SƯ DỮ LIỆU"
    assert cv_fields["address"]["value"] == "Hà Nội"
    assert cv_fields["headline"]["extractor"] == "phase17-family-layout"

    contract = _canonical(
        [
            "HỢP ĐỒNG THỬ VIỆC",
            "Số hợp đồng",
            "HD-2026-001",
            "Ngày ký",
            "01/02/2026",
            "Người lao động",
            "Trần Thị B",
            "Công việc/Chức danh",
            "Chuyên viên nhân sự",
            "Hiệu lực từ",
            "05/02/2026",
            "Mức lương thử việc",
            "12.000.000 VND",
        ]
    )
    contract_classification = classify_phase15_document(contract)
    contract_extraction = extract_phase15_document(contract, contract_classification)
    contract_fields = _external_fields("contract", contract, contract_extraction, ocr=False)

    assert contract_fields["contract_number"]["value"] == "HD-2026-001"
    assert contract_fields["contract_sign_date"]["normalizedValue"] == "01/02/2026"
    assert contract_fields["employee_name"]["value"] == "Trần Thị B"
    assert contract_fields["job_title"]["value"] == "Chuyên viên nhân sự"
    assert contract_fields["effective_date"]["normalizedValue"] == "05/02/2026"


def test_data13_all_active_families_are_scored_when_prediction_includes_visual_cv() -> None:
    fields = {
        name: {"value": "synthetic"}
        for name in (
            "full_name", "headline", "email", "phone_number", "address",
            "desired_role", "years_experience", "experience", "skills", "education",
        )
    }
    report = build_aggregate_report(
        {
            "datasetId": "synthetic-test",
            "ocrScopePolicy": "all-active-families",
            "documents": [{
                "caseId": "cv-001",
                "category": "cv",
                "sourceFormat": "IMAGE",
                "evaluationIncluded": True,
                "fields": fields,
                "processing": {"usesOcr": True, "recommendedAction": "MANUAL_REVIEW"},
            }],
        },
        {"cases": [{
            "caseId": "cv-001",
            "fields": [{"name": name, "value": "synthetic"} for name in fields],
        }]},
    )

    assert report["evaluatedDocumentCount"] == 1
    assert report["policyExcludedDocumentCount"] == 0
    assert report["ocrPolicy"]["unsupportedNoOcrCount"] == 0
    assert report["metrics"]["fieldExactMatchRate"] == 1.0


def test_ielts_layout_parser_uses_form_geometry_and_keeps_manual_review() -> None:
    canonical = _ocr_canonical(
        [
            "IELTS",
            "Test Report Form",
            "ACADEMIC",
            "Family Name",
            "NGUYEN",
            "First Name(s)",
            "THU PHUONG",
            "Candidate ID",
            "081203004567",
            "Overall",
            "Band",
            "Score",
            "6.0",
            "Date",
            "10/MAY/2023",
            "Test Report Form Number",
            "23VN500938NGUT028A",
            "Date",
            "22/05/2023",
        ]
    )
    classification = classify_phase15_document(canonical)
    extraction = extract_phase15_document(canonical, classification)
    fields = _external_fields("ielts", canonical, extraction, ocr=True)

    assert classification["documentFamily"] == "DEGREE_CERTIFICATE"
    assert fields["recipient_name"]["value"] == "NGUYEN THU PHUONG"
    assert fields["credential_id"]["value"] == "23VN500938NGUT028A"
    assert fields["credential_type"]["value"] == "IELTS Academic"
    assert fields["overall_score"]["value"] == "6.0"
    assert fields["issue_date"]["normalizedValue"] == "2023-05-22"
    assert all(field["status"] == "needs_review" for field in fields.values())


def test_soft_text_policy_accepts_case_and_eighty_percent_coverage_only() -> None:
    names = (
        "full_name", "headline", "email", "phone_number", "address",
        "desired_role", "years_experience", "experience", "skills", "education",
    )
    truth_fields = {name: None for name in names}
    prediction_fields = {name: None for name in names}
    truth_fields.update({
        "full_name": "Correct Person",
        "headline": "Data Analyst",
        "skills": "Python; SQL; Excel; Power BI; Docker",
    })
    prediction_fields.update({
        "full_name": "Correct Person",
        "headline": "data analyst",
        "skills": "python sql excel power bi",
    })
    report = build_aggregate_report(
        {
            "datasetId": "synthetic-test",
            "ocrScopePolicy": "all-active-families",
            "documents": [{
                "caseId": "cv-001",
                "category": "cv",
                "predictedCategory": "cv",
                "fields": {name: {"value": value} for name, value in prediction_fields.items()},
                "processing": {"usesOcr": False, "recommendedAction": "USER_REVIEW"},
            }],
        },
        {"cases": [{
            "caseId": "cv-001",
            "fields": [{"name": name, "value": value} for name, value in truth_fields.items()],
        }]},
    )

    assert report["metrics"]["fieldExactMatchRate"] == 0.8
    assert report["metrics"]["fieldAcceptedMatchRate"] == 1.0
    assert report["byCategory"]["cv"]["acceptedRate"] == 1.0
