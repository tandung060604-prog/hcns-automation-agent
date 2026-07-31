"""Validate the public weekly-report artifact without opening private document data."""

from __future__ import annotations

import json
from pathlib import Path

REPORT_ROOT = Path("docs/weekly-reports/2026-W31")
REQUIRED = (
    REPORT_ROOT / "AUDIT_NOTES.md",
    REPORT_ROOT / "WEEKLY_REPORT.md",
    REPORT_ROOT / "WEEKLY_REPORT.html",
    REPORT_ROOT / "EVIDENCE_MANIFEST.json",
    REPORT_ROOT / "assets" / "cccd" / "selection.json",
    REPORT_ROOT / "assets" / "website" / "local-overview.png",
    REPORT_ROOT / "assets" / "website" / "local-product.png",
)


def main() -> int:
    missing = [str(path) for path in REQUIRED if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing weekly-report artifacts: {', '.join(missing)}")
    selection = json.loads((REPORT_ROOT / "assets" / "cccd" / "selection.json").read_text("utf-8"))
    if selection.get("privacy", {}).get("containsPII") is not False:
        raise SystemExit("CCCD selection must declare containsPII=false")
    if not 3 <= len(selection.get("selected", [])) <= 4:
        raise SystemExit("CCCD selection must contain 3 or 4 samples")
    report_text = (REPORT_ROOT / "WEEKLY_REPORT.md").read_text("utf-8")
    forbidden = ("identityNumber", "fullName", "dateOfBirth", "placeOfResidence")
    found = [token for token in forbidden if token in report_text]
    if found:
        raise SystemExit(f"Report contains disallowed CCCD field names: {', '.join(found)}")
    manifest = json.loads((REPORT_ROOT / "EVIDENCE_MANIFEST.json").read_text("utf-8"))
    for artifact in manifest.get("artifacts", []):
        relative_path = artifact.get("path")
        if relative_path and not (REPORT_ROOT / relative_path).is_file():
            raise SystemExit(f"Manifest file missing: {relative_path}")
    print("weekly-report validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
