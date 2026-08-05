from __future__ import annotations

from apps.ocr_lab.api.external_dataset_prediction import build_aggregate_report


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
