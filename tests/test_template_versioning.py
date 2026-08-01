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

    assert manifest["lifecycle"] == "FROZEN_V1"
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
