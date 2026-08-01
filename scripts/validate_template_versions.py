"""Validate the frozen Template-first version and UAT contract."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcns_agent.templates.registry import build_default_template_registry  # noqa: E402
from hcns_agent.templates.versioning import (  # noqa: E402
    TemplateVersionGovernanceError,
    validate_template_version_manifest,
)

MANIFEST = ROOT / "config/template_version_manifest.json"


def main() -> int:
    try:
        validate_template_version_manifest(
            root=ROOT,
            registry=build_default_template_registry(),
            manifest_path=MANIFEST,
        )
    except (OSError, ValueError, TemplateVersionGovernanceError) as error:
        raise SystemExit(f"Template version governance failed: {error}") from error
    print("Template version governance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
