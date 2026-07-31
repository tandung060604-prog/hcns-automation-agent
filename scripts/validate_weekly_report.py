"""Validate the public weekly-report artifact without opening private document data."""

from __future__ import annotations

import json
from html.parser import HTMLParser
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
    if evidence.get("containsPII") is not False or len(evidence.get("artifacts", [])) != 16:
        raise SystemExit("Redacted visual evidence must declare no PII and contain 16 artifacts")
    if evidence.get("hcnsDataClassification") != "synthetic-ai-generated":
        raise SystemExit("HCNS evidence must be classified as synthetic AI-generated data")
    identity_artifacts = [
        row for row in evidence["artifacts"] if row["kind"] == "redacted-identity-source"
    ]
    synthetic_artifacts = [
        row for row in evidence["artifacts"] if row["kind"].startswith("synthetic-")
    ]
    if len(identity_artifacts) != 4 or len(synthetic_artifacts) != 12:
        raise SystemExit("Expected 4 redacted CCCD and 12 synthetic HCNS artifacts")
    for artifact in evidence["artifacts"]:
        if not (REPORT_ROOT / "assets" / artifact["path"]).is_file():
            raise SystemExit(f"Redacted evidence missing: {artifact['path']}")
    report_text = (REPORT_ROOT / "WEEKLY_REPORT.md").read_text("utf-8")
    forbidden = (
        "identityNumber",
        "fullName",
        "dateOfBirth",
        "placeOfResidence",
        "TF-P",
        "Phase 11",
    )
    found = [token for token in forbidden if token in report_text]
    if found:
        raise SystemExit(f"Report contains disallowed CCCD field names: {', '.join(found)}")
    html_text = (REPORT_ROOT / "WEEKLY_REPORT.html").read_text("utf-8")
    found_html = [token for token in forbidden if token in html_text]
    if found_html:
        raise SystemExit(
            f"HTML report contains internal or sensitive terms: {', '.join(found_html)}"
        )
    parser = ImageSourceParser()
    parser.feed(html_text)
    missing_images = [source for source in parser.sources if not (REPORT_ROOT / source).is_file()]
    if missing_images:
        raise SystemExit(f"HTML report has missing images: {', '.join(missing_images)}")
    if len(parser.sources) != 18:
        raise SystemExit("HTML report must render 18 evidence images")
    manifest = json.loads((REPORT_ROOT / "EVIDENCE_MANIFEST.json").read_text("utf-8"))
    for artifact in manifest.get("artifacts", []):
        relative_path = artifact.get("path")
        if relative_path and not (REPORT_ROOT / relative_path).is_file():
            raise SystemExit(f"Manifest file missing: {relative_path}")
    print("weekly-report validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
