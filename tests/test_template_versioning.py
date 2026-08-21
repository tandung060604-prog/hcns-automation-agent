from __future__ import annotations

import json
from pathlib import Path

import pytest

from hcns_agent.templates.registry import build_default_template_registry
from hcns_agent.templates.versioning import (
    TemplateVersionGovernanceError,
    validate_template_version_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/template_version_manifest.json"


def test_frozen_template_manifest_matches_registry_and_schemas() -> None:
    manifest = validate_template_version_manifest(
        root=ROOT,
        registry=build_default_template_registry(),
        manifest_path=MANIFEST,
    )

    assert manifest["lifecycle"] == "FROZEN_V2"
    assert manifest["uat"]["reportContainsRawFieldValues"] is False


def test_template_version_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["templates"][0]["parserVersion"] = "9.9.9"
    mutated = tmp_path / "template_version_manifest.json"
    mutated.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(TemplateVersionGovernanceError, match="parserVersion"):
        validate_template_version_manifest(
            root=ROOT,
            registry=build_default_template_registry(),
            manifest_path=mutated,
        )


def test_template_parser_id_mismatch_fails_closed(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["templates"][0]["parserId"] = "legacy/parser"
    mutated = tmp_path / "template_version_manifest.json"
    mutated.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(TemplateVersionGovernanceError, match="parserId"):
        validate_template_version_manifest(
            root=ROOT,
            registry=build_default_template_registry(),
            manifest_path=mutated,
        )


def test_schema_version_mismatch_fails_closed(tmp_path: Path) -> None:
    schema_path = ROOT / "schemas/templates/cv_v2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["properties"]["templateVersion"]["const"] = "9.9"
    isolated_schema = tmp_path / "schemas/templates/cv_v2.schema.json"
    isolated_schema.parent.mkdir(parents=True)
    isolated_schema.write_text(json.dumps(schema), encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["templates"] = [
        {
            **row,
            "schemaRef": (
                "schemas/templates/cv_v2.schema.json"
                if row["templateId"] == "cv-v2"
                else row["schemaRef"]
            ),
        }
        for row in manifest["templates"]
    ]
    isolated_manifest = tmp_path / "template_version_manifest.json"
    isolated_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(TemplateVersionGovernanceError, match="Schema version"):
        validate_template_version_manifest(
            root=tmp_path,
            registry=build_default_template_registry(),
            manifest_path=isolated_manifest,
        )


def test_v2_business_fields_match_the_benchmark_contract() -> None:
    registry = {
        row["templateId"]: row
        for row in build_default_template_registry().list_templates()
    }
    assert registry["cv-v2"]["requiredFields"] == [
        "full_name", "headline", "email", "phone_number", "address",
        "desired_role", "years_experience", "experience", "skills", "education",
    ]
    assert registry["probation-contract-v2"]["requiredFields"] == [
        "contract_number", "contract_sign_date", "effective_date", "probation_end_date",
        "employer_name", "employer_representative", "employee_name", "employee_id_number",
        "job_title", "workplace", "weekly_hours", "probation_salary_monthly",
        "allowances_summary", "salary_payment_schedule",
    ]
    assert registry["probation-contract-v2"]["optionalFields"] == [
        "professional_title", "role_title",
    ]
    assert registry["probation-contract-v2"]["version"] == "2.1"
    assert registry["probation-contract-v2"]["schemaVersion"] == "2.1.0"
    assert registry["ielts-certificate-v2"]["requiredFields"] == [
        "recipient_name", "credential_id", "credential_type", "overall_score", "issue_date",
    ]
