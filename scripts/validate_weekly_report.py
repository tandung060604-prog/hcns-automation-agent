"""Validate the weekly-report artifact without opening private document data."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

REPORT_ROOT = Path("docs/weekly-reports/2026-W31")
REQUIRED = (
    REPORT_ROOT / "AUDIT_NOTES.md",
    REPORT_ROOT / "WEEKLY_REPORT.md",
    REPORT_ROOT / "EVIDENCE_MANIFEST.json",
    REPORT_ROOT / "assets" / "cccd" / "selection.json",
    REPORT_ROOT / "assets" / "website" / "local-overview.png",
    REPORT_ROOT / "assets" / "website" / "local-product.png",
    REPORT_ROOT / "assets" / "evidence-index.json",
)


class ImageSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        attributes = dict(attrs)
        if source := attributes.get("src"):
            self.sources.append(source)


def main() -> int:
    missing = [str(path) for path in REQUIRED if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing weekly-report artifacts: {', '.join(missing)}")
    selection = json.loads((REPORT_ROOT / "assets" / "cccd" / "selection.json").read_text("utf-8"))
    if selection.get("privacy", {}).get("containsPII") is not False:
        raise SystemExit("CCCD selection must declare containsPII=false")
    if not 3 <= len(selection.get("selected", [])) <= 4:
        raise SystemExit("CCCD selection must contain 3 or 4 samples")
    evidence = json.loads((REPORT_ROOT / "assets" / "evidence-index.json").read_text("utf-8"))
    if evidence.get("containsPII") is not False or len(evidence.get("artifacts", [])) != 18:
        raise SystemExit("Synthetic visual evidence must declare no PII and contain 18 artifacts")
    if evidence.get("hcnsDataClassification") != "synthetic-ai-generated":
        raise SystemExit("HCNS evidence must be classified as synthetic AI-generated data")
    if evidence.get("cccdDataClassification") != "synthetic-ai-generated-user-declared":
        raise SystemExit(
            "CCCD evidence must be classified as user-declared synthetic AI-generated data"
        )
    identity_artifacts = [
        row for row in evidence["artifacts"] if row["kind"] == "synthetic-identity-ui"
    ]
    prediction_artifacts = [
        row
        for row in evidence["artifacts"]
        if row["kind"] == "synthetic-identity-prediction-json"
    ]
    synthetic_artifacts = [
        row for row in evidence["artifacts"] if row["kind"].startswith("synthetic-")
    ]
    if len(identity_artifacts) != 2 or len(prediction_artifacts) != 2:
        raise SystemExit("Expected 2 synthetic CCCD UI images and 2 Prediction JSON artifacts")
    if len(synthetic_artifacts) != 18:
        raise SystemExit("Expected 18 synthetic evidence artifacts")
    for artifact in evidence["artifacts"]:
        if not (REPORT_ROOT / "assets" / artifact["path"]).is_file():
            raise SystemExit(f"Redacted evidence missing: {artifact['path']}")
    report_text = (REPORT_ROOT / "WEEKLY_REPORT.md").read_text("utf-8")
    forbidden = (
        "TF-P",
        "Phase 11",
    )
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
