"""Compatibility boundary for the canonical Template-first field contract.

The external benchmark uses snake_case names.  Older local sessions were
written with the first review-only contract (camelCase).  New processing uses
the v2 identifiers; this module keeps old result files readable without
rewriting private data or changing their source documents.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CANONICAL_TEMPLATE_IDS = {
    "cv-v1": "cv-v2",
    "probation-contract-v1": "probation-contract-v2",
    "ielts-certificate-v1": "ielts-certificate-v2",
}

CANONICAL_TEMPLATE_VERSIONS = {
    "cv-v2": "2.0",
    "probation-contract-v2": "2.1",
    "ielts-certificate-v2": "2.0",
}

CANONICAL_SCHEMA_VERSIONS = {
    "cv-v2": "2.0.0",
    "probation-contract-v2": "2.1.0",
    "ielts-certificate-v2": "2.0.0",
}

CANONICAL_FIELDS = {
    "cv-v2": (
        "full_name", "headline", "email", "phone_number", "address",
        "desired_role", "years_experience", "experience", "skills", "education",
    ),
    "probation-contract-v2": (
        "contract_number", "contract_sign_date", "effective_date", "probation_end_date",
        "employer_name", "employer_representative", "employee_name", "employee_id_number",
        "professional_title", "role_title", "job_title", "workplace", "weekly_hours",
        "probation_salary_monthly",
        "allowances_summary", "salary_payment_schedule",
    ),
    "ielts-certificate-v2": (
        "recipient_name", "credential_id", "credential_type", "overall_score", "issue_date",
    ),
}

LEGACY_FIELD_MAP: dict[str, dict[str, str]] = {
    "cv-v1": {
        "fullName": "full_name",
        "phoneNumber": "phone_number",
        "desiredRole": "desired_role",
        "yearsExperience": "years_experience",
    },
    "probation-contract-v1": {
        "contractNumber": "contract_number",
        "contractSignDate": "contract_sign_date",
        "employeeName": "employee_name",
        "employeeId": "employee_id_number",
        "employeeIdNumber": "employee_id_number",
        "jobTitle": "job_title",
        "salary": "probation_salary_monthly",
        "probationSalaryMonthly": "probation_salary_monthly",
        "effectiveDate": "effective_date",
        "probationEndDate": "probation_end_date",
        "employerName": "employer_name",
        "employerRepresentative": "employer_representative",
        "weeklyHours": "weekly_hours",
        "allowancesSummary": "allowances_summary",
        "salaryPaymentSchedule": "salary_payment_schedule",
    },
    "ielts-certificate-v1": {
        "recipientName": "recipient_name",
        "credentialId": "credential_id",
        "credentialType": "credential_type",
        "overallScore": "overall_score",
        "issueDate": "issue_date",
    },
}


def canonical_template_id(template_id: str) -> str:
    """Return the active v2 id while accepting a historical v1 id."""

    return CANONICAL_TEMPLATE_IDS.get(template_id, template_id)


def canonical_field_name(template_id: str, field_name: str) -> str:
    """Map one legacy field name without touching unrelated fields."""

    return LEGACY_FIELD_MAP.get(template_id, {}).get(field_name, field_name)


def canonicalize_template_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a stored result envelope to the active v2 field contract.

    This is deliberately a pure, metadata-preserving projection.  It does
    not read a source file, recompute a prediction, or persist the projection.
    """

    result = _copy_mapping(payload)
    legacy_id = str(result.get("templateId", ""))
    target_id = canonical_template_id(legacy_id)
    if target_id == legacy_id:
        return result

    result["templateId"] = target_id
    result["templateVersion"] = CANONICAL_TEMPLATE_VERSIONS[target_id]
    result["schemaVersion"] = CANONICAL_SCHEMA_VERSIONS[target_id]
    result["data"] = _canonicalize_data(result.get("data"), legacy_id)
    result["quality"] = _canonicalize_quality(result.get("quality"), legacy_id)
    result["detection"] = _canonicalize_detection(result.get("detection"), target_id)
    result["camundaVariables"] = _canonicalize_camunda(
        result.get("camundaVariables"), target_id
    )
    return result


def canonicalize_corrections(
    template_id: str, corrections: Mapping[str, Any]
) -> dict[str, Any]:
    """Map corrections submitted against a historical v1 result."""

    return {
        canonical_field_name(template_id, str(key)): value
        for key, value in corrections.items()
    }


def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()}


def _canonicalize_data(value: object, legacy_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    mapping = LEGACY_FIELD_MAP.get(legacy_id, {})
    canonical = {
        mapping.get(str(key), str(key)): item
        for key, item in value.items()
    }
    for field_name in CANONICAL_FIELDS[canonical_template_id(legacy_id)]:
        canonical.setdefault(field_name, None)
    return canonical


def _canonicalize_quality(value: object, legacy_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    mapping = LEGACY_FIELD_MAP.get(legacy_id, {})
    quality = _copy_mapping(value)
    missing = quality.get("missingFields")
    if isinstance(missing, list):
        quality["missingFields"] = [mapping.get(str(item), str(item)) for item in missing]
    errors = quality.get("validationErrors")
    if isinstance(errors, list):
        quality["validationErrors"] = [
            _map_error(str(item), mapping) for item in errors
        ]
    return quality


def _canonicalize_detection(value: object, target_id: str) -> dict[str, Any]:
    detection = _copy_mapping(value) if isinstance(value, Mapping) else {}
    if "templateId" in detection:
        detection["templateId"] = target_id
    if target_id in CANONICAL_TEMPLATE_VERSIONS:
        detection["templateVersion"] = CANONICAL_TEMPLATE_VERSIONS[target_id]
    return detection


def _canonicalize_camunda(value: object, target_id: str) -> dict[str, Any]:
    variables = _copy_mapping(value) if isinstance(value, Mapping) else {}
    if "templateId" in variables:
        variables["templateId"] = target_id
    if target_id in CANONICAL_TEMPLATE_VERSIONS:
        variables["templateVersion"] = CANONICAL_TEMPLATE_VERSIONS[target_id]
    return variables


def _map_error(value: str, mapping: Mapping[str, str]) -> str:
    prefix, separator, field = value.partition(":")
    if separator:
        return f"{prefix}:{mapping.get(field, field)}"
    return value
