from __future__ import annotations

import pytest

from scripts.run_data31_schema_replay import _ground_truth_coverage, build_data31_coverage_scope


def test_ground_truth_coverage_separates_empty_and_predicted_fields() -> None:
    prediction = {
        "documents": [
            {
                "caseId": "contract-001",
                "category": "contract",
                "fields": {
                    "contract_number": {"value": "C-1"},
                    "contract_sign_date": {"value": "2026-01-01"},
                },
            }
        ]
    }
    ground_truth = {
        "cases": [
            {
                "caseId": "contract-001",
                "fields": [
                    {"name": "contract_number", "value": "C-1"},
                    {"name": "contract_sign_date", "value": None},
                ],
            }
        ]
    }

    coverage = _ground_truth_coverage(prediction, ground_truth)

    assert coverage["total"]["fields"] == 14
    assert coverage["total"]["populated"] == 1
    assert coverage["total"]["empty"] == 13
    assert coverage["total"]["predictionForEmpty"] == 1
    assert coverage["total"]["bothEmpty"] == 12


def test_data31_coverage_scope_merges_gt_and_excludes_case_field() -> None:
    names = (
        "contract_number", "contract_sign_date", "effective_date", "probation_end_date",
        "employer_name", "employer_representative", "employee_name", "employee_id_number",
        "job_title", "workplace", "weekly_hours", "probation_salary_monthly",
        "allowances_summary", "salary_payment_schedule",
    )
    inventory = {
        "dataset": {"datasetId": "DATA-31"},
        "cases": [{
            "caseId": "contract-001",
            "category": "contract",
            "sourceSha256": "sha256:synthetic",
        }],
    }
    ground_truth = {"cases": [{
        "caseId": "contract-001",
        "fields": [
            {"name": name, "value": "known" if name == "contract_number" else None}
            for name in names
        ],
    }]}
    missing = names[1:]
    decisions = {
        "schemaVersion": "data31-ground-truth-coverage-decision/1.0.0",
        "datasetId": "DATA-31",
        "status": "COMPLETE",
        "cases": {
            "contract-001": {
                "category": "contract",
                "sourceSha256": "sha256:synthetic",
                "fields": {
                    name: {
                        "disposition": (
                            "OUT_OF_SCOPE" if name == "effective_date" else "GROUND_TRUTH"
                        ),
                        "value": None if name == "effective_date" else f"truth-{name}",
                    }
                    for name in missing
                },
            }
        },
    }

    effective, scope, summary = build_data31_coverage_scope(
        inventory, ground_truth, decisions
    )

    assert summary == {
        "status": "COMPLETE",
        "missingFieldCount": 13,
        "decidedFieldCount": 13,
        "activeFieldCount": 13,
        "outOfScopeFieldCount": 1,
        "scopeOverrideFieldCount": 0,
        "groundTruthOverrideFieldCount": 0,
    }
    assert len(scope["contract-001"]) == 13
    assert "effective_date" not in scope["contract-001"]
    values = {field["name"]: field["value"] for field in effective["cases"][0]["fields"]}
    assert values["contract_sign_date"] == "truth-contract_sign_date"
    assert values["effective_date"] is None

    decisions["cases"]["contract-001"]["fields"]["effective_date"]["value"] = "unexpected"
    with pytest.raises(ValueError, match="OUT_OF_SCOPE"):
        build_data31_coverage_scope(inventory, ground_truth, decisions)


def test_data31_coverage_scope_rejects_incomplete_overlay() -> None:
    inventory = {
        "dataset": {"datasetId": "DATA-31"},
        "cases": [{
            "caseId": "contract-001",
            "category": "contract",
            "sourceSha256": "sha256:synthetic",
        }],
    }
    ground_truth = {"cases": [{
        "caseId": "contract-001",
        "fields": [{"name": "contract_number", "value": None}],
    }]}
    decisions = {
        "schemaVersion": "data31-ground-truth-coverage-decision/1.0.0",
        "datasetId": "DATA-31",
        "status": "COMPLETE",
        "cases": {},
    }

    with pytest.raises(ValueError, match="incomplete"):
        build_data31_coverage_scope(inventory, ground_truth, decisions)


def test_data31_scope_override_excludes_populated_field_without_rewriting_gt() -> None:
    names = (
        "contract_number", "contract_sign_date", "effective_date", "probation_end_date",
        "employer_name", "employer_representative", "employee_name", "employee_id_number",
        "job_title", "workplace", "weekly_hours", "probation_salary_monthly",
        "allowances_summary", "salary_payment_schedule",
    )
    inventory = {
        "dataset": {"datasetId": "DATA-31"},
        "cases": [{
            "caseId": "contract-001",
            "category": "contract",
            "sourceSha256": "sha256:synthetic",
        }],
    }
    ground_truth = {"cases": [{
        "caseId": "contract-001",
        "fields": [{"name": name, "value": "known"} for name in names],
    }]}
    decisions = {
        "schemaVersion": "data31-ground-truth-coverage-decision/1.0.0",
        "datasetId": "DATA-31",
        "status": "COMPLETE",
        "cases": {},
        "scopeOverrides": {
            "contract-001": {
                "category": "contract",
                "sourceSha256": "sha256:synthetic",
                "fields": {
                    "job_title": {"disposition": "OUT_OF_SCOPE", "value": None},
                },
            }
        },
    }

    effective, scope, summary = build_data31_coverage_scope(
        inventory, ground_truth, decisions
    )

    assert summary == {
        "status": "COMPLETE",
        "missingFieldCount": 0,
        "decidedFieldCount": 0,
        "activeFieldCount": 13,
        "outOfScopeFieldCount": 1,
        "scopeOverrideFieldCount": 1,
        "groundTruthOverrideFieldCount": 0,
    }
    assert "job_title" not in scope["contract-001"]
    assert effective["cases"][0]["fields"][8]["value"] == "known"


def test_data31_ground_truth_override_updates_private_effective_view_only() -> None:
    inventory = {
        "dataset": {"datasetId": "DATA-31"},
        "cases": [{
            "caseId": "ielts-001",
            "category": "ielts",
            "sourceSha256": "sha256:synthetic",
        }],
    }
    names = ("recipient_name", "credential_id", "credential_type", "overall_score", "issue_date")
    ground_truth = {"cases": [{
        "caseId": "ielts-001",
        "fields": [{"name": name, "value": f"sealed-{name}"} for name in names],
    }]}
    decisions = {
        "schemaVersion": "data31-ground-truth-coverage-decision/1.0.0",
        "datasetId": "DATA-31",
        "status": "COMPLETE",
        "cases": {},
        "groundTruthOverrides": {
            "ielts-001": {
                "category": "ielts",
                "sourceSha256": "sha256:synthetic",
                "fields": {
                    "credential_type": {
                        "disposition": "GROUND_TRUTH",
                        "value": "ACADEMIC",
                    }
                },
            }
        },
    }

    effective, scope, summary = build_data31_coverage_scope(
        inventory, ground_truth, decisions
    )

    assert summary["groundTruthOverrideFieldCount"] == 1
    assert scope["ielts-001"] == names
    assert effective["cases"][0]["fields"][2]["value"] == "ACADEMIC"
    assert ground_truth["cases"][0]["fields"][2]["value"] == "sealed-credential_type"
