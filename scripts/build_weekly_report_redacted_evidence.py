"""Create public-safe visual evidence from authorized local HR/CCCD sources.

Every source image is fully blurred and darkened before it is written.  Result
cards use only safe operational metadata; no field values, OCR text, source
names, face image or original document is copied to the report directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import textwrap
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import fitz
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.templates.service import build_local_template_processing_service

CANVAS_SIZE = (1200, 760)
FONT_PATH = Path("C:/Windows/Fonts/arial.ttf")
FONT = ImageFont.truetype(str(FONT_PATH), 18) if FONT_PATH.is_file() else ImageFont.load_default()
SMALL_FONT = (
    ImageFont.truetype(str(FONT_PATH), 15) if FONT_PATH.is_file() else ImageFont.load_default()
)
PALETTE = {"ink": "#17382e", "accent": "#0a6c50", "soft": "#e7f2ec", "line": "#b9d4c8"}


def opaque_id(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:10].upper()
    return f"CCCD-EV-{digest}"


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, fill: str) -> None:
    draw.text(xy, value, fill=fill, font=FONT)


def redacted_source(source: Image.Image, title: str, output: Path) -> None:
    source = source.convert("RGB")
    source.thumbnail((1120, 600))
    canvas = Image.new("RGB", CANVAS_SIZE, "#f7faf8")
    x = (CANVAS_SIZE[0] - source.width) // 2
    y = 90 + (600 - source.height) // 2
    safe = source.filter(ImageFilter.GaussianBlur(radius=60))
    safe = ImageEnhance.Brightness(safe).enhance(0.28)
    canvas.paste(safe, (x, y))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle((40, 28, 1160, 710), radius=18, outline=PALETTE["line"], width=3)
    draw.rectangle((40, 28, 1160, 84), fill=PALETTE["ink"])
    draw_text(draw, (62, 49), title, "#ffffff")
    draw.rounded_rectangle((355, 330, 845, 414), radius=12, fill=(255, 255, 255, 238))
    draw_text(draw, (408, 356), "ALL SOURCE CONTENT REDACTED", PALETTE["ink"])
    draw_text(draw, (470, 379), "Layout evidence only", PALETTE["accent"])
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def synthetic_source(source: Image.Image, title: str, output: Path) -> None:
    source = source.convert("RGB")
    source.thumbnail((1080, 600))
    canvas = Image.new("RGB", CANVAS_SIZE, "#f7faf8")
    x = (CANVAS_SIZE[0] - source.width) // 2
    y = 105 + (585 - source.height) // 2
    canvas.paste(source, (x, y))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle((40, 28, 1160, 720), radius=18, outline=PALETTE["line"], width=3)
    draw.rectangle((40, 28, 1160, 88), fill=PALETTE["ink"])
    draw_text(draw, (62, 50), f"SYNTHETIC / AI-GENERATED - {title}", "#ffffff")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines: list[str] = []
    for paragraph in root.iter(namespace + "p"):
        value = "".join(node.text or "" for node in paragraph.iter(namespace + "t")).strip()
        if value:
            lines.append(value)
    return "\n".join(lines)


def docx_source(path: Path, title: str, output: Path) -> None:
    canvas = Image.new("RGB", CANVAS_SIZE, "#f7faf8")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (90, 28, 1110, 720), radius=18, fill="#ffffff", outline=PALETTE["line"], width=3
    )
    draw.rectangle((90, 28, 1110, 88), fill=PALETTE["ink"])
    draw_text(draw, (112, 50), f"SYNTHETIC / AI-GENERATED - {title}", "#ffffff")
    y = 125
    for raw_line in docx_text(path).splitlines():
        for line in textwrap.wrap(raw_line, width=88) or [""]:
            draw.text((145, y), line, fill=PALETTE["ink"], font=SMALL_FONT)
            y += 25
            if y > 680:
                break
        if y > 680:
            break
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def result_card(
    title: str,
    source_format: str,
    result: dict[str, Any],
    output: Path,
) -> None:
    canvas = Image.new("RGB", CANVAS_SIZE, "#f7faf8")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (70, 55, 1130, 705), radius=18, fill="#ffffff", outline=PALETTE["line"], width=3
    )
    draw.rectangle((70, 55, 1130, 118), fill=PALETTE["ink"])
    draw_text(draw, (96, 80), f"SYNTHETIC ENGINE OUTPUT - {title}", "#ffffff")
    draw_text(draw, (120, 170), "Input format", PALETTE["accent"])
    draw_text(draw, (120, 200), source_format, PALETTE["ink"])
    draw_text(draw, (120, 265), "Processing path", PALETTE["accent"])
    processing = result.get("processing", {})
    uses_ocr = bool(processing.get("usesOcr"))
    draw_text(draw, (120, 295), "Local OCR" if uses_ocr else "Native extraction", PALETTE["ink"])
    draw_text(draw, (120, 350), "Extracted fields", PALETTE["accent"])
    data = result.get("data", {})
    excluded = {"sourceFile", "missingFields", "validationErrors", "recommendedAction"}
    fields = [
        (key, value)
        for key, value in data.items()
        if key not in excluded and value is not None
    ]
    y = 385
    for key, value in fields[:8]:
        rendered = str(value).replace("\n", " ")
        if len(rendered) > 62:
            rendered = rendered[:59] + "..."
        draw.text((140, y), key, fill=PALETTE["accent"], font=SMALL_FONT)
        draw.text((410, y), rendered, fill=PALETTE["ink"], font=SMALL_FONT)
        y += 30
    quality = result.get("quality", {})
    action = quality.get("recommendedAction")
    decision = "Automatic route" if action == "AUTO_CONTINUE" else "Human review required"
    draw.rounded_rectangle((120, 635, 500, 690), radius=10, fill="#eaf7ef")
    draw.text((145, 654), f"Decision: {decision}", fill=PALETTE["accent"], font=SMALL_FONT)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def image_from_pdf(path: Path) -> Image.Image:
    document = fitz.open(path)
    try:
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    finally:
        document.close()


def choose_hr_sources(root: Path) -> list[tuple[str, str, Path]]:
    matrix = (("leave", "leave_requests"), ("overtime", "overtime_requests"))
    formats = (("DOCX", "*.docx"), ("PDF", "*.pdf"), ("IMAGE", "*.png"))
    selected: list[tuple[str, str, Path]] = []
    for label, folder in matrix:
        for source_format, pattern in formats:
            paths = sorted((root / folder).rglob(pattern))
            if not paths:
                raise FileNotFoundError(f"Missing {source_format} evidence for {label}")
            selected.append((label, source_format, paths[0]))
    return selected


def selected_cccd_sources(data_root: Path, selection_path: Path) -> list[tuple[str, Path]]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    wanted = {row["sampleId"] for row in selection["selected"]}
    found: list[tuple[str, Path]] = []
    for result_path in (data_root / "user_uploads" / "sessions").glob("*/result.json"):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("document", {}).get("documentType") != "IDENTITY_DOCUMENT":
            continue
        sample_id = opaque_id(str(result.get("sessionId", "")))
        if sample_id not in wanted:
            continue
        source_paths = sorted((result_path.parent / "input").glob("document.*"))
        if len(source_paths) == 1:
            found.append((sample_id, source_paths[0]))
    if len(found) != len(wanted):
        raise RuntimeError("Unable to resolve every selected CCCD source")
    return sorted(found)


def build(data_root: Path, hr_root: Path, output_root: Path) -> dict[str, Any]:
    entries: list[dict[str, str]] = []
    service = build_local_template_processing_service()
    for label, source_format, path in choose_hr_sources(hr_root):
        key = f"{label}-{source_format.lower()}"
        source_output = output_root / "hr" / f"{key}-source-synthetic.png"
        if source_format == "DOCX":
            docx_source(path, f"{label.upper()} REQUEST / DOCX", source_output)
        elif source_format == "PDF":
            synthetic_source(image_from_pdf(path), f"{label.upper()} REQUEST / PDF", source_output)
        else:
            with Image.open(path) as image:
                synthetic_source(image.copy(), f"{label.upper()} REQUEST / IMAGE", source_output)
        result = service.process(
            DocumentSource(
                document_id=f"weekly-report-{key}",
                filename=path.name,
                content=path.read_bytes(),
            )
        ).public_dict()
        result_output = output_root / "hr" / f"{key}-result-synthetic.png"
        result_card(label.upper() + " REQUEST", source_format, result, result_output)
        entries.extend(
            (
                {
                    "path": source_output.relative_to(output_root).as_posix(),
                    "kind": "synthetic-source",
                },
                {
                    "path": result_output.relative_to(output_root).as_posix(),
                    "kind": "synthetic-result",
                },
            )
        )
    selection_path = output_root / "cccd" / "selection.json"
    for sample_id, path in selected_cccd_sources(data_root, selection_path):
        output = output_root / "cccd" / f"{sample_id.lower()}-source-redacted.png"
        with Image.open(path) as image:
            redacted_source(image.copy(), "IDENTITY CARD / REDACTED", output)
        entries.append(
            {
                "path": output.relative_to(output_root).as_posix(),
                "kind": "redacted-identity-source",
            }
        )
    evidence = {
        "schemaVersion": "weekly-report-redacted-evidence/1.0",
        "redaction": "CCCD: full-frame blur and darkening; HCNS: unredacted AI-generated data",
        "containsPII": False,
        "hcnsDataClassification": "synthetic-ai-generated",
        "artifacts": entries,
    }
    (output_root / "evidence-index.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--hr-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    evidence = build(args.data_root, args.hr_root, args.output_root)
    print(f"redacted-artifacts={len(evidence['artifacts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
