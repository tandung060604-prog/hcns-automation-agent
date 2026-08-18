from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import apps.ocr_lab.api.external_dataset_prediction as prediction_module
from apps.ocr_lab.api.external_dataset_prediction import (
    MATCHING_POLICY_V2,
    _cv_header_fields,
    _external_fields,
    _field,
    _field_match,
    build_aggregate_report,
    build_gate_report,
    load_prediction_document,
    resolve_prediction_source,
)
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


def _positioned_ocr_canonical(items: list[tuple[str, int, int, int]]) -> dict[str, Any]:
    blocks = []
    for index, (text, x, y, width) in enumerate(items):
        box = [[x, y], [x + width, y], [x + width, y + 20], [x, y + 20]]
        blocks.append(
            {
                "text": text,
                "sourceKind": "ocr",
                "confidence": 0.94,
                "evidence": {
                    "pageIndex": 0,
                    "sourceRef": f"ocr:{index}",
                    "bbox": box,
                },
            }
        )
    return {
        "plainText": "\n".join(item[0] for item in items),
        "pages": [{"blocks": blocks, "ocrBlocks": blocks}],
        "tables": [],
    }


def test_data29_adapter_delegates_to_promoted_parser(monkeypatch: Any) -> None:
    expected = {"field": {"value": None}}
    calls: list[tuple[object, str, bool]] = []

    def promoted(canonical: object, category: str, *, ocr: bool) -> object:
        calls.append((canonical, category, ocr))
        return expected

    monkeypatch.setattr(prediction_module, "extract_structured_hr_fields", promoted)
    canonical = {"pages": []}

    result = _external_fields("cv", canonical, {"fields": {}}, ocr=True)

    assert result is expected
    assert calls == [(canonical, "cv", True)]


def test_prediction_source_resolution_is_inventory_only() -> None:
    temp_root = Path(Path.cwd().anchor) / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="prediction-source-", dir=temp_root) as raw_root:
        root = Path(raw_root)
        source = root / "cv-001.png"
        source.write_bytes(b"synthetic-image")
        inventory = root / "inventory.json"
        inventory.write_text(
            json.dumps(
                {
                    "cases": [
                        {
                            "caseId": "cv-001",
                            "sourceRelativePath": "cv-001.png",
                            "sourceSha256": (
                                "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
                            ),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        assert resolve_prediction_source(root, inventory, "cv-001") == source.resolve()


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
    assert report["metrics"]["applicableFieldCount"] == 1
    assert report["metrics"]["applicableFieldPresenceCount"] == 1
    assert report["metrics"]["applicableCompletenessRate"] == 1.0
    assert report["metrics"]["sensitiveFalseAcceptanceCount"] == 0
    assert report["metrics"]["parserCorrectRegressionCount"] == 0
    assert report["schemaErrors"] == 0
    assert report["ocrPolicy"]["ocrDocumentCount"] == 1
    assert report["ocrPolicy"]["manualReviewRate"] == 1.0
    assert report["ocrPolicy"]["ocrAlwaysManualReview"] is True
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


def test_masked_ielts_identifier_is_treated_as_absent() -> None:
    names = ("recipient_name", "credential_id", "credential_type", "overall_score", "issue_date")
    prediction = {
        "datasetId": "synthetic-test",
        "documents": [{
            "caseId": "ielts-001",
            "category": "ielts",
            "predictedCategory": "ielts",
            "fields": {name: {"value": None} for name in names},
            "processing": {"usesOcr": True, "recommendedAction": "MANUAL_REVIEW"},
        }],
    }
    ground_truth = {"cases": [{
        "caseId": "ielts-001",
        "fields": [
            {"name": name, "value": None if name == "credential_id" else "value"}
            for name in names
        ],
    }]}

    report = build_aggregate_report(prediction, ground_truth)

    assert report["metrics"]["applicableFieldCount"] == 4
    assert report["metrics"]["applicableFieldPresenceCount"] == 0
    assert report["metrics"]["applicableCompletenessRate"] == 0.0


def test_data20_sensitive_false_acceptance_is_additive_and_separate() -> None:
    names = (
        "full_name", "headline", "email", "phone_number", "address", "desired_role",
        "years_experience", "experience", "skills", "education",
    )
    prediction_values = {name: None for name in names}
    truth_values = {name: None for name in names}
    truth_values["experience"] = "A B C D"
    prediction_values["experience"] = "a b c d"
    report = build_aggregate_report(
        {
            "datasetId": "synthetic-test",
            "documents": [{
                "caseId": "cv-001",
                "category": "cv",
                "predictedCategory": "cv",
                "fields": {name: {"value": value} for name, value in prediction_values.items()},
                "processing": {"usesOcr": False, "recommendedAction": "USER_REVIEW"},
            }],
        },
        {"cases": [{
            "caseId": "cv-001",
            "fields": [
                {
                    "name": name,
                    "value": value,
                    "sensitive": name == "experience",
                }
                for name, value in truth_values.items()
            ],
        }]},
    )

    assert report["metrics"]["fieldExactMatchCount"] == 9
    assert report["metrics"]["fieldAcceptedMatchCount"] == 10
    assert report["metrics"]["applicableFieldCount"] == 1
    assert report["metrics"]["applicableCompletenessRate"] == 1.0
    assert report["metrics"]["sensitiveFalseAcceptanceCount"] == 1


def test_data20_parser_regression_compares_fixed_candidate_baseline_set() -> None:
    names = (
        "full_name", "headline", "email", "phone_number", "address", "desired_role",
        "years_experience", "experience", "skills", "education",
    )
    truth_values = {name: None for name in names}
    truth_values["full_name"] = "Exact Person"

    def prediction(value: str) -> dict[str, Any]:
        fields = {name: None for name in names}
        fields["full_name"] = value
        return {
            "datasetId": "synthetic-test",
            "documents": [{
                "caseId": "cv-001",
                "category": "cv",
                "predictedCategory": "cv",
                "fields": {name: {"value": item} for name, item in fields.items()},
                "processing": {"usesOcr": False, "recommendedAction": "USER_REVIEW"},
            }],
        }

    baseline = prediction("Exact Person")
    candidate = prediction("Wrong Person")
    report = build_aggregate_report(
        candidate,
        {"cases": [{
            "caseId": "cv-001",
            "fields": [{"name": name, "value": value} for name, value in truth_values.items()],
        }]},
        baseline_prediction=baseline,
    )

    assert report["metrics"]["parserCorrectRegressionCount"] == 1
    assert report["parserRegressionComparison"] == {
        "baselineProvided": True,
        "sameEvaluationSet": True,
        "sameScanEvaluationSet": True,
        "baselineDocumentCount": 1,
        "candidateDocumentCount": 1,
        "overlapDocumentCount": 1,
        "baselineScanDocumentCount": 0,
        "candidateScanDocumentCount": 0,
        "scanOverlapDocumentCount": 0,
    }


def test_data20_gate_harness_is_deterministic_and_requires_fallback_ten_points() -> None:
    specs = {
        "cv": (
            "full_name", "headline", "email", "phone_number", "address", "desired_role",
            "years_experience", "experience", "skills", "education",
        ),
        "contract": (
            "contract_number", "contract_sign_date", "effective_date", "probation_end_date",
            "employer_name", "employer_representative", "employee_name", "employee_id_number",
            "job_title", "workplace", "weekly_hours", "probation_salary_monthly",
            "allowances_summary", "salary_payment_schedule",
        ),
        "ielts": (
            "recipient_name",
            "credential_id",
            "credential_type",
            "overall_score",
            "issue_date",
        ),
    }
    ground_truth = {"cases": [{
        "caseId": f"{category}-001",
        "fields": [{"name": name, "value": "synthetic"} for name in names],
    } for category, names in specs.items()]}

    def artifact(*, wrong_cv_name: bool = False) -> dict[str, Any]:
        documents = []
        for category, names in specs.items():
            values = {name: {"value": "synthetic"} for name in names}
            if category == "cv" and wrong_cv_name:
                for name in names[:7]:
                    values[name] = {"value": "not exact"}
            documents.append({
                "caseId": f"{category}-001",
                "category": category,
                "predictedCategory": category,
                "fields": values,
                "processing": {"usesOcr": True, "recommendedAction": "MANUAL_REVIEW"},
            })
        return {
            "datasetId": "synthetic-test",
            "documents": documents,
        }

    candidate = build_aggregate_report(artifact(), ground_truth)
    baseline = build_aggregate_report(artifact(wrong_cv_name=True), ground_truth)
    candidate_with_baseline = build_aggregate_report(
        artifact(), ground_truth, baseline_prediction=artifact(wrong_cv_name=True)
    )
    passing = build_gate_report(candidate_with_baseline, baseline, fallback_candidate=True)
    holding = build_gate_report(candidate, baseline, fallback_candidate=True)

    assert passing["decision"] == "PASS"
    assert passing["fallback"]["strictImprovementRate"] >= 0.1
    assert holding["decision"] == "HOLD"
    assert holding["fallback"]["status"] == "HOLD"


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
    assert cv_fields["headline"]["extractor"] == "structured-hr/family-layout"

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


def test_cv_header_splits_glued_uppercase_name_from_title() -> None:
    canonical = _canonical(["SYNTHETIC USERData Analyst"])
    name, headline = _cv_header_fields(canonical)
    assert name["value"] == "SYNTHETIC USER"
    assert headline["value"] == "Data Analyst"


def test_cv_native_skills_stop_at_next_heading_and_remove_layout_labels() -> None:
    canonical = _canonical(
        [
            "CURRICULUM VITAE",
            "K\u1ef8 N\u0102NG",
            "\u2022 H\u1ea1ch to\u00e1n & l\u1eadp b\u00e1o c\u00e1o t\u00e0i ch\u00ednh",
            "\u2022 Ph\u1ea7n m\u1ec1m MISA, FAST",
            "\u2022 Tin h\u1ecdc v\u0103n ph\u00f2ng: Word, Excel",
            "CH\u1ee8NG CH\u1ec8",
            "\u2022 IELTS 6.5",
        ]
    )
    classification = classify_phase15_document(canonical)
    extraction = extract_phase15_document(canonical, classification)
    fields = _external_fields("cv", canonical, extraction, ocr=False)

    assert fields["skills"]["value"] == (
        "H\u1ea1ch to\u00e1n v\u00e0 l\u1eadp b\u00e1o c\u00e1o t\u00e0i ch\u00ednh "
        "MISA, FAST Word, Excel"
    )
    assert "IELTS" not in fields["skills"]["value"]


def test_cv_native_skill_normalization_matches_flattened_skill_tokens() -> None:
    canonical = _canonical(
        [
            "CURRICULUM VITAE",
            "K\u1ef8 N\u0102NG",
            "\u2022 Ng\u00f4n ng\u1eef: Java, Python",
            "\u2022 Backend: Spring Boot, Node.js",
            "CH\u1ee8NG CH\u1ec8",
        ]
    )
    classification = classify_phase15_document(canonical)
    extraction = extract_phase15_document(canonical, classification)
    fields = _external_fields("cv", canonical, extraction, ocr=False)
    match = _field_match(
        "cv",
        "skills",
        "Java; Python; Spring Boot; Node.js",
        fields["skills"]["value"],
        policy_version=MATCHING_POLICY_V2,
    )

    assert match["matchType"] == "CANONICAL_EXACT"
    assert match["exact"] is True


def test_prediction_document_uses_matching_policy_pinned_by_report() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        prediction = root / "prediction.json"
        report = root / "report.json"
        marker = root / "marker.json"
        ground_truth = root / "ground-truth.json"
        prediction.write_text(
            json.dumps(
                {
                    "documents": [
                        {
                            "caseId": "cv-001",
                            "category": "cv",
                            "fields": {"full_name": {"value": "TEST USER"}},
                            "processing": {"usesOcr": False},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        report.write_text(
            json.dumps({"matchingPolicy": {"version": MATCHING_POLICY_V2}}),
            encoding="utf-8",
        )
        marker.write_text("{}", encoding="utf-8")
        ground_truth.write_text(
            json.dumps(
                {
                    "cases": [
                        {
                            "caseId": "cv-001",
                            "fields": [
                                {
                                    "name": "full_name",
                                    "value": "test user",
                                }
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        detail = load_prediction_document(
            (prediction, report, marker), "cv-001", ground_truth
        )

    assert detail["matchingPolicyVersion"] == MATCHING_POLICY_V2
    assert detail["comparison"]["full_name"]["exact"] is True


def test_cv_desired_role_normalizes_title_conjunction_without_touching_prose() -> None:
    canonical = _canonical(
        [
            "CURRICULUM VITAE",
            "M\u1ee4C TI\u00caU NGH\u1ec0 NGHI\u1ec6P",
            "Mong mu\u1ed1n theo h\u01b0\u1edbng Senior Data Analyst v\u00e0 Analytics Engineer",
            "H\u1eccC V\u1ea4N",
            "\u2022 University",
        ]
    )
    classification = classify_phase15_document(canonical)
    extraction = extract_phase15_document(canonical, classification)
    fields = _external_fields("cv", canonical, extraction, ocr=False)

    assert fields["desired_role"]["value"] == "Senior Data Analyst / Analytics Engineer"


def test_contract_party_normalization_does_not_cross_party_boundary() -> None:
    contract = _canonical(
        [
            "BÊN A: NGƯỜI SỬ DỤNG LAO ĐỘNG",
            "Đại diện bởi: Bà ALPHA REPRESENTATIVE",
            "Chức vụ: Giám đốc",
            "BÊN B: NGƯỜI LAO ĐỘNG",
            "Họ và tên: BETA EMPLOYEE Giới tính: Nữ",
            "Điều 1. Công việc",
        ]
    )
    classification = classify_phase15_document(contract)
    extraction = extract_phase15_document(contract, classification)
    fields = _external_fields("contract", contract, extraction, ocr=False)

    assert fields["employer_representative"]["value"] == "ALPHA REPRESENTATIVE"
    assert fields["employee_name"]["value"] == "BETA EMPLOYEE"


def test_contract_party_fallback_strips_person_prefix_and_role_suffix() -> None:
    contract = _canonical(
        [
            "BÊN A: NGƯỜI SỬ DỤNG LAO ĐỘNG",
            "Đại diện: Ông ALPHA REPRESENTATIVE Chức vụ: Giám đốc",
            "BÊN B: NGƯỜI LAO ĐỘNG",
            "Họ và tên: BETA EMPLOYEE Giới tính: Nam",
        ]
    )
    classification = classify_phase15_document(contract)
    extraction = extract_phase15_document(contract, classification)
    fields = _external_fields("contract", contract, extraction, ocr=False)

    assert fields["employer_representative"]["value"] == "ALPHA REPRESENTATIVE"
    assert fields["employee_name"]["value"] == "BETA EMPLOYEE"


def test_cv_ocr_sections_follow_geometry_not_engine_order() -> None:
    canonical = _positioned_ocr_canonical(
        [
            ("CURRICULUM VITAE", 10, 0, 650),
            ("NGUYỄN VĂN A", 10, 30, 220),
            ("HỌC VẤN", 10, 70, 180),
            ("KINH NGHIỆM LÀM VIỆC", 420, 70, 230),
            ("Công ty Synthetic", 420, 110, 220),
            ("Chuyên viên nhân sự", 420, 145, 220),
            ("Đại học Kiểm thử", 10, 110, 220),
            ("Kỹ thuật phần mềm", 10, 145, 220),
            ("KỸ NĂNG", 10, 210, 160),
            ("Python, SQL", 10, 250, 180),
        ]
    )
    classification = classify_phase15_document(canonical)
    extraction = extract_phase15_document(canonical, classification)
    fields = _external_fields("cv", canonical, extraction, ocr=True)

    assert fields["education"]["value"] == "Đại học Kiểm thử Kỹ thuật phần mềm"
    assert fields["experience"]["value"] == "Công ty Synthetic Chuyên viên nhân sự"
    assert fields["skills"]["value"] == "Python, SQL"
    assert fields["education"]["status"] == "needs_review"


def test_cv_ocr_section_infers_full_width_heading_from_body_geometry() -> None:
    canonical = _positioned_ocr_canonical(
        [
            ("KINH NGHIỆM LÀM VIỆC", 10, 0, 120),
            ("Công ty Synthetic", 10, 40, 220),
            ("Backend Engineer", 500, 40, 180),
            ("KỸ NĂNG", 10, 100, 120),
            ("Python", 10, 140, 100),
        ]
    )
    classification = classify_phase15_document(canonical)
    extraction = extract_phase15_document(canonical, classification)
    fields = _external_fields("cv", canonical, extraction, ocr=True)

    assert fields["experience"]["value"] == "Công ty Synthetic Backend Engineer"


def test_cv_ocr_skills_repair_uses_repeated_document_token_only() -> None:
    canonical = _positioned_ocr_canonical(
        [
            ("CURRICULUM VITAE", 10, 0, 650),
            ("KINH NGHI\u1ec6M L\u00c0M VI\u1ec6C", 10, 40, 300),
            ("Backend Engineer PostgreSQL", 10, 80, 300),
            ("K\u1ef8 N\u0102NG", 10, 140, 200),
            ("Java, Postgresqu", 10, 180, 200),
        ]
    )
    classification = classify_phase15_document(canonical)
    extraction = extract_phase15_document(canonical, classification)
    fields = _external_fields("cv", canonical, extraction, ocr=True)

    assert fields["skills"]["value"] == "Java, PostgreSQL"
    assert fields["skills"]["method"] == "cv_skills_ocr_document_anchor"
    assert fields["skills"]["status"] == "needs_review"


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


def test_field_tolerates_missing_ocr_confidence() -> None:
    field = _field(
        "masked",
        method="test",
        block={"confidence": None},
        review=True,
    )

    assert field["value"] == "masked"
    assert field["confidence"] is None


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


def test_contract_semantic_metric_is_symmetric_and_keeps_raw_strict_metric() -> None:
    names = (
        "contract_number", "contract_sign_date", "effective_date", "probation_end_date",
        "employer_name", "employer_representative", "employee_name", "employee_id_number",
        "job_title", "workplace", "weekly_hours", "probation_salary_monthly",
        "allowances_summary", "salary_payment_schedule",
    )
    prediction_values = {name: None for name in names}
    truth_values = {name: None for name in names}
    prediction_values.update({
        "employer_representative": "VÕ THU HẰNG",
        "employee_name": "NGUYỄN HỮU LONG",
    })
    truth_values.update({
        "employer_representative": "Bà Võ Thu Hằng – Giám đốc",
        "employee_name": "Nguyễn Hữu Long",
    })
    report = build_aggregate_report(
        {
            "datasetId": "synthetic-test",
            "documents": [{
                "caseId": "contract-003",
                "category": "contract",
                "predictedCategory": "contract",
                "fields": {name: {"value": value} for name, value in prediction_values.items()},
                "processing": {"usesOcr": False, "recommendedAction": "USER_REVIEW"},
            }],
        },
        {"cases": [{
            "caseId": "contract-003",
            "fields": [{"name": name, "value": value} for name, value in truth_values.items()],
        }]},
    )

    assert report["metrics"]["fieldExactMatchCount"] == 12
    assert report["metrics"]["fieldSemanticMatchCount"] == 14
    assert report["metrics"]["fieldSemanticMatchRate"] == 1.0
    assert report["byCategory"]["contract"]["semanticExactRate"] == 1.0


def test_policy_v2_canonicalizes_case_layout_dates_duration_and_scores() -> None:
    cases = (
        ("cv", "full_name", "Vũ Tú Anh", "VŨ TÚ ANH", "CANONICAL_EXACT"),
        ("cv", "education", "Đại học; Kinh tế", "ĐẠI HỌC - KINH TẾ", "CANONICAL_EXACT"),
        ("cv", "years_experience", "2 năm", "2 năm kinh nghiệm", "CANONICAL_EXACT"),
        ("cv", "years_experience", "Hơn 6 năm", "hơn 6 năm", "CANONICAL_EXACT"),
        ("ielts", "issue_date", "06/06/2024", "2024-06-06", "CANONICAL_EXACT"),
        ("ielts", "overall_score", "6.5", "6.50", "CANONICAL_EXACT"),
    )
    for category, name, truth, guess, match_type in cases:
        result = _field_match(category, name, truth, guess, policy_version="2.0.0")
        assert result["exact"] is True
        assert result["match"] is True
        assert result["matchType"] == match_type
        assert result["rawExact"] is False


def test_policy_v2_keeps_overextraction_partial_and_sensitive_values_strict() -> None:
    partial = _field_match(
        "cv",
        "desired_role",
        "Chuyên viên chính",
        "chuyên viên chính và đóng góp vào hiệu quả vận hành bền vững",
        policy_version="2.0.0",
    )
    assert partial["exact"] is False
    assert partial["match"] is True
    assert partial["matchType"] == "ACCEPTED_PARTIAL"
    assert partial["overExtraction"] is True
    assert partial["groundTruthTokenCoverage"] == 1.0

    for category, name, truth, guess in (
        ("cv", "full_name", "Vũ Tú Anh", "Vũ Tú Anh Financial Accountant"),
        ("cv", "full_name", "Vũ Tú Anh", "Vũ Tú"),
        ("contract", "probation_salary_monthly", "12000000 đồng/tháng", "12000000"),
        ("ielts", "issue_date", "06/06/2024", "06/07/2024"),
        ("cv", "years_experience", "Hơn 6 năm", "6 năm"),
    ):
        result = _field_match(category, name, truth, guess, policy_version="2.0.0")
        assert result["exact"] is False
        assert result["match"] is False
        assert result["matchType"] == "MISMATCH"


def test_policy_v2_report_separates_canonical_and_raw_exact_metrics() -> None:
    names = (
        "full_name", "headline", "email", "phone_number", "address", "desired_role",
        "years_experience", "experience", "skills", "education",
    )
    truth = {name: None for name in names}
    guess = {name: None for name in names}
    truth.update({
        "full_name": "Vũ Tú Anh",
        "years_experience": "2 năm",
        "desired_role": "Chuyên viên chính",
    })
    guess.update({
        "full_name": "VŨ TÚ ANH",
        "years_experience": "2 năm kinh nghiệm",
        "desired_role": "Chuyên viên chính và vận hành",
    })
    report = build_aggregate_report(
        {
            "datasetId": "synthetic-test",
            "documents": [{
                "caseId": "cv-002",
                "category": "cv",
                "predictedCategory": "cv",
                "fields": {name: {"value": value} for name, value in guess.items()},
                "processing": {"usesOcr": False, "recommendedAction": "USER_REVIEW"},
            }],
        },
        {"cases": [{
            "caseId": "cv-002",
            "fields": [{"name": name, "value": value} for name, value in truth.items()],
        }]},
        policy_version="2.0.0",
    )
    assert report["matchingPolicy"]["version"] == "2.0.0"
    assert report["metrics"]["fieldExactMatchCount"] == 9
    assert report["metrics"]["fieldRawExactMatchCount"] == 7
    assert report["metrics"]["fieldAcceptedMatchCount"] == 10
    assert report["metrics"]["fieldExactMatchRate"] != report["metrics"]["fieldAcceptedMatchRate"]
