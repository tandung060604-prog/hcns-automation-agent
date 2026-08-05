#!/usr/bin/env python3
"""Render private, text-free line/ROI overlays for OCR-HO-V2 diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2

COLORS = {
    "fullName": (255, 180, 0),
    "placeOfOrigin": (0, 200, 255),
    "placeOfResidence": (0, 0, 255),
}


def _box(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        left, top, right, bottom = (int(round(float(item))) for item in value)
    except (TypeError, ValueError):
        return None
    return left, top, right, bottom


def _draw_box(
    image: Any,
    box: tuple[int, int, int, int],
    color: tuple[int, int, int],
    thickness: int,
    label: str = "",
) -> None:
    left, top, right, bottom = box
    cv2.rectangle(image, (left, top), (right, bottom), color, thickness)
    if label:
        cv2.putText(
            image,
            label,
            (left, max(15, top - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )


def render_overlay(session: Path, output: Path, document_index: int) -> dict[str, Any]:
    page_path = next(
        iter(sorted((session / "phase11" / "pages").glob("page_*.png"))),
        None,
    )
    if page_path is None:
        page_path = next(
            iter(sorted((session / "phase11" / "canonical").glob("page_*.png"))),
            None,
        )
    if not page_path.is_file():
        page_path = session / "pages" / "page_000.png"
    image = cv2.imread(str(page_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Cannot read selected page: {page_path}")
    evidence = json.loads(
        (session / "phase11_10_v2" / "field_consensus.json").read_text(encoding="utf-8")
    )
    regions = evidence.get("regions", {})
    summary: dict[str, Any] = {"documentIndex": document_index, "fields": {}}
    for field_name, color in COLORS.items():
        region = regions.get(field_name) or {}
        broad = _box(region.get("bbox"))
        lines = [_box(item) for item in region.get("lineBboxes") or []]
        lines = [item for item in lines if item is not None]
        line_ids = [item for item in region.get("lineIds") or [] if isinstance(item, int)]
        if broad:
            _draw_box(image, broad, color, 2, f"{field_name} ROI")
        for position, line in enumerate(lines):
            line_id = line_ids[position] if position < len(line_ids) else "?"
            _draw_box(image, line, color, 3, f"line {line_id}")
        summary["fields"][field_name] = {
            "regionSource": region.get("regionSource"),
            "lineCount": len(lines),
            "lineIds": line_ids,
            "hasBroadRoi": broad is not None,
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), image):
        raise OSError(f"Cannot write overlay: {output}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output_root.exists() and not args.overwrite:
        raise SystemExit("Overlay output exists; pass --overwrite")
    sessions = args.data_root / "user_uploads-sessions"
    records = json.loads(args.manifest.read_text(encoding="utf-8")).get("records", [])
    rows = []
    for record in records:
        document_index = int(record["documentIndex"])
        session = sessions / str(record["sessionId"])
        rows.append(
            render_overlay(
                session,
                args.output_root / f"document_{document_index:03d}.png",
                document_index,
            )
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "SUMMARY.json").write_text(
        json.dumps(
            {
                "schemaVersion": "ocr-ho-v2-014-overlays/1.0.0",
                "containsRawPII": False,
                "documents": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "documentCount": len(rows),
                "outputRoot": str(args.output_root),
                "containsRawPII": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
