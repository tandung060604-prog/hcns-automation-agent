from __future__ import annotations

from hcns_agent.templates.compatibility import (
    canonicalize_corrections,
    canonicalize_template_payload,
)


def test_legacy_cv_result_is_projected_to_canonical_v2_fields() -> None:
    payload = canonicalize_template_payload(
        {
            "templateId": "cv-v1",
            "templateVersion": "1.0",
            "data": {
                "fullName": "Synthetic",
                "phoneNumber": "000",
                "desiredRole": "Analyst",
                "yearsExperience": "2",
            },
            "quality": {"missingFields": ["phoneNumber"]},
            "detection": {"templateId": "cv-v1", "templateVersion": "1.0"},
            "camundaVariables": {"templateId": "cv-v1", "templateVersion": "1.0"},
        }
    )

    assert payload["templateId"] == "cv-v2"
    assert payload["templateVersion"] == "2.0"
    assert payload["schemaVersion"] == "2.0.0"
    assert payload["data"]["full_name"] == "Synthetic"
    assert payload["data"]["phone_number"] == "000"
    assert payload["data"]["desired_role"] == "Analyst"
    assert payload["data"]["years_experience"] == "2"
    assert payload["quality"]["missingFields"] == ["phone_number"]
    assert payload["camundaVariables"]["templateId"] == "cv-v2"


def test_canonical_result_is_idempotent() -> None:
    payload = {
        "templateId": "cv-v2",
        "templateVersion": "2.0",
        "data": {"full_name": "Synthetic"},
    }
    assert canonicalize_template_payload(payload) == payload


def test_legacy_probation_contract_result_is_projected_to_v2_fields() -> None:
    payload = canonicalize_template_payload(
        {
            "templateId": "probation-contract-v1",
            "templateVersion": "1.0",
            "data": {
                "employeeName": "Synthetic Employee",
                "employeeId": "EMP-000",
                "jobTitle": "Synthetic Role",
                "salary": "1000000",
                "effectiveDate": "2026-01-01",
                "probationEndDate": "2026-03-01",
                "employerName": "Synthetic Employer",
                "contractNumber": "CT-000",
                "contractSignDate": "2025-12-01",
                "employerRepresentative": "Synthetic Director",
                "weeklyHours": "40",
                "allowancesSummary": "None",
                "salaryPaymentSchedule": "Monthly",
            },
        }
    )

    assert payload["templateId"] == "probation-contract-v2"
    assert payload["data"]["employee_name"] == "Synthetic Employee"
    assert payload["data"]["employee_id_number"] == "EMP-000"
    assert payload["data"]["probation_salary_monthly"] == "1000000"
    assert payload["data"]["effective_date"] == "2026-01-01"
    assert payload["data"]["contract_number"] == "CT-000"
    assert payload["data"]["contract_sign_date"] == "2025-12-01"
    assert payload["data"]["employer_representative"] == "Synthetic Director"
    assert payload["data"]["weekly_hours"] == "40"


def test_legacy_ielts_result_and_corrections_use_v2_fields() -> None:
    payload = canonicalize_template_payload(
        {
            "templateId": "ielts-certificate-v1",
            "templateVersion": "1.0",
            "data": {
                "recipientName": "Synthetic Candidate",
                "credentialId": "TRF-000",
                "credentialType": "IELTS Academic",
                "overallScore": "7.0",
                "issueDate": "2026-01-01",
            },
        }
    )

    assert payload["templateId"] == "ielts-certificate-v2"
    assert payload["data"]["recipient_name"] == "Synthetic Candidate"
    assert payload["data"]["credential_id"] == "TRF-000"
    assert payload["data"]["overall_score"] == "7.0"
    assert canonicalize_corrections(
        "ielts-certificate-v1",
        {"recipientName": "Updated Synthetic Candidate", "issueDate": "2026-02-01"},
    ) == {
        "recipient_name": "Updated Synthetic Candidate",
        "issue_date": "2026-02-01",
    }
