"""Version-governance checks for the closed Template-first set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hcns_agent.templates.registry import TemplateRegistry


class TemplateVersionGovernanceError(ValueError):
    """Raised when the frozen template contract is internally inconsistent."""


def load_version_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TemplateVersionGovernanceError("Version manifest must be an object")
    return value


def validate_template_version_manifest(
    *,
    root: Path,
    registry: TemplateRegistry,
    manifest_path: Path,
) -> dict[str, Any]:
    """Validate registry, schema files and the tracked UAT policy together."""
    manifest = load_version_manifest(manifest_path)
    if manifest.get("schemaVersion") != "template-version-governance/1.0.0":
        raise TemplateVersionGovernanceError("Unsupported version manifest schema")
    if manifest.get("lifecycle") != "FROZEN_V1":
        raise TemplateVersionGovernanceError("Only the frozen v1 lifecycle is allowed")
    rows = manifest.get("templates")
    if not isinstance(rows, list) or not rows:
        raise TemplateVersionGovernanceError("Version manifest has no templates")
    registry_rows = {str(row["templateId"]): row for row in registry.list_templates()}
    manifest_rows = {
        str(row.get("templateId")): row
        for row in rows
        if isinstance(row, dict) and row.get("templateId")
    }
    if set(registry_rows) != set(manifest_rows):
        raise TemplateVersionGovernanceError(
            "Registry and version manifest template sets differ"
        )
    for template_id, registry_row in registry_rows.items():
        manifest_row = manifest_rows[template_id]
        for key in (
            "documentType",
            "version",
            "schemaRef",
            "parserVersion",
            "lifecycle",
            "supportedFileTypes",
            "requiredFields",
        ):
            if registry_row.get(key) != manifest_row.get(key):
                raise TemplateVersionGovernanceError(
                    f"Version mismatch for {template_id}: {key}"
                )
        schema_path = root / str(manifest_row["schemaRef"])
        if not schema_path.is_file():
            raise TemplateVersionGovernanceError(
                f"Schema file is missing for {template_id}: {schema_path}"
            )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise TemplateVersionGovernanceError(
                f"Schema properties are missing for {template_id}"
            )
        if properties.get("templateId", {}).get("const") != template_id:
            raise TemplateVersionGovernanceError(
                f"Schema templateId mismatch for {template_id}"
            )
        if properties.get("templateVersion", {}).get("const") != manifest_row["version"]:
            raise TemplateVersionGovernanceError(
                f"Schema version mismatch for {template_id}"
            )
    _validate_uat_policy(manifest)
    return manifest


def schema_paths_by_document_type(
    *,
    root: Path,
    manifest: dict[str, Any],
) -> dict[str, Path]:
    rows = manifest.get("templates", [])
    return {
        str(row["documentType"]): root / str(row["schemaRef"])
        for row in rows
        if isinstance(row, dict)
    }


def _validate_uat_policy(manifest: dict[str, Any]) -> None:
    uat = manifest.get("uat")
    if not isinstance(uat, dict):
        raise TemplateVersionGovernanceError("UAT policy is missing")
    if uat.get("formats") != ["docx", "pdf", "image", "scan_pdf"]:
        raise TemplateVersionGovernanceError("UAT format matrix is incomplete")
    gates = uat.get("gates")
    if not isinstance(gates, dict):
        raise TemplateVersionGovernanceError("UAT gates are missing")
    expected = {
        "classificationRate": 1.0,
        "nativeRequiredFieldExactMatch": 1.0,
        "ocrRequiredFieldExactMatch": 0.8,
        "schemaErrorCount": 0,
        "falseAutoContinueCount": 0,
        "ocrReviewRouting": "MANUAL_REVIEW",
    }
    if gates != expected:
        raise TemplateVersionGovernanceError("UAT gates differ from the approved policy")
    if uat.get("reportContainsRawFieldValues") is not False:
        raise TemplateVersionGovernanceError("UAT report must remain aggregate-only")
