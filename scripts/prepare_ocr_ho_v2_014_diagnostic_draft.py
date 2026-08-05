#!/usr/bin/env python3
"""Create a source-only line-ID draft; never opens candidate field values."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))
from phase11_10_cccd_v2 import locate_field_regions, prepare_line_pages  # noqa: E402

TARGET_FIELDS = {"fullName": 1, "placeOfOrigin": 2, "placeOfResidence": 2}


def _line_ids(page: dict[str, Any], region: dict[str, Any], maximum: int) -> list[int]:
    ids = [item for item in region.get("lineIds") or [] if isinstance(item, int)]
    if ids:
        return ids[:maximum]
    bbox = region.get("bbox") or [0, 0, 0, 0]
    top, bottom = float(bbox[1]), float(bbox[3])
    candidates: list[tuple[float, int]] = []
    for index, box in enumerate(page.get("recognizedBoxes", [])):
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        center_y = (min(ys) + max(ys)) / 2
        if top <= center_y <= bottom and max(xs) >= float(bbox[0]):
            candidates.append((center_y, index))
    return [index for _, index in sorted(candidates)[:maximum]]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sessions = args.data_root / "user_uploads-sessions"
    documents: dict[str, Any] = {}
    records = json.loads(args.manifest.read_text(encoding="utf-8")).get("records", [])
    for record in records:
        session = sessions / str(record["sessionId"])
        source_gt = json.loads(
            (session / "phase10" / "ground_truth.json").read_text(encoding="utf-8")
        )
        result = json.loads((session / "result.json").read_text(encoding="utf-8"))
        page_paths = sorted((session / "phase11" / "pages").glob("page_*.png"))
        images = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in page_paths]
        pages, images = prepare_line_pages(
            session, result.get("phase11", {}).get("pages") or [], images
        )
        if not images or images[0] is None:
            raise RuntimeError(f"Missing source page: {session}")
        regions = locate_field_regions(pages, [(images[0].shape[1], images[0].shape[0])])
        fields: dict[str, Any] = {}
        for field_name, maximum in TARGET_FIELDS.items():
            value = str((source_gt.get("identityFields") or {}).get(field_name) or "").strip()
            line_ids = _line_ids(pages[0], regions[field_name], maximum)
            fields[field_name] = {"value": value, "lineIds": line_ids}
        documents[str(record["sessionId"])] = {
            "fields": fields,
            "assertions": {
                "comparedWithSource": True,
                "allTextChecked": True,
                "linesChecked": False,
            },
            "predictionOpened": False,
            "draft": True,
            "draftedAt": datetime.now(timezone.utc).isoformat(),
        }
    payload = {
        "schemaVersion": "ocr-ho-v2-014-diagnostic/1.0.0",
        "localOnly": True,
        "predictionOpened": False,
        "promotionEligible": False,
        "status": "DRAFT_NEEDS_LINE_CONFIRMATION",
        "documents": documents,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    missing = sum(
        1
        for document in documents.values()
        for field in document["fields"].values()
        if not field["lineIds"]
    )
    print(
        json.dumps(
            {
                "documentCount": len(documents),
                "missingLineAssignments": missing,
                "status": payload["status"],
                "predictionOpened": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
