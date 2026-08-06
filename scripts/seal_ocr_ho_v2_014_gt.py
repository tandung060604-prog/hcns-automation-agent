#!/usr/bin/env python3
"""Seal the prediction-blind OCR-HO-V2 development line mapping locally."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))
from ocr_ho_v2_diagnostic import FIELDS, _load, _record  # noqa: E402
from phase11_8_shadow_uat import _session_records  # noqa: E402


def digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Private output path; defaults to the archive root seal marker.",
    )
    args = parser.parse_args()
    root = args.data_root.resolve()
    output = (args.output or root / "OCR_HO_V2_014_GT_SEALED_PRIVATE.json").resolve()
    store = _load(root)
    records = _session_records(root)
    if len(records) != 15:
        raise SystemExit(f"Expected 15 eligible documents, found {len(records)}")
    if len(store.get("documents", {})) != len(records):
        raise SystemExit("Ground Truth is not complete for every eligible document")

    documents: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        review = store["documents"].get(record["documentId"])
        if not isinstance(review, dict) or review.get("draft") is not False:
            raise SystemExit(f"Document {record['documentId']} is not final")
        assertions = review.get("assertions") or {}
        if not all(assertions.get(key) is True for key in (
            "comparedWithSource", "allTextChecked", "linesChecked"
        )):
            raise SystemExit(f"Document {record['documentId']} is not fully checked")
        detail = _record(root, record["documentId"])
        line_count = len(json.loads(
            (detail["sessionDir"] / "result.json").read_text(encoding="utf-8")
        ).get("phase11", {}).get("pages", [{}])[0].get("recognizedBoxes", []))
        fields: dict[str, Any] = {}
        for field_name, maximum in FIELDS.items():
            field = review.get("fields", {}).get(field_name) or {}
            value = str(field.get("value") or "").strip()
            line_ids = field.get("lineIds")
            if not value or not isinstance(line_ids, list) or not 1 <= len(line_ids) <= maximum:
                raise SystemExit(f"Invalid sealed field {record['documentId']}:{field_name}")
            if any(not isinstance(line_id, int) or line_id < 0 for line_id in line_ids):
                raise SystemExit(f"Invalid line ID {record['documentId']}:{field_name}")
            # recognizedBoxes are indexed; keep this validation independent of OCR text.
            if any(line_id >= line_count for line_id in line_ids):
                raise SystemExit(f"Line ID out of range {record['documentId']}:{field_name}")
            fields[field_name] = {"value": value, "lineIds": line_ids}
        documents.append({
            "documentIndex": index,
            "documentId": record["documentId"],
            "sessionId": record["documentId"],
            "sourceFile": record["sourceFile"],
            "selectedRotationDegrees": 0,
            "fields": fields,
        })

    payload: dict[str, Any] = {
        "schemaVersion": "ocr-ho-v2-014-gt-sealed/1.0.0",
        "datasetRole": "DEVELOPMENT_GROUND_TRUTH",
        "localOnly": True,
        "containsRawPII": True,
        "predictionOpened": False,
        "sealed": True,
        "immutable": True,
        "sealedAt": datetime.now(timezone.utc).isoformat(),
        "documentCount": len(documents),
        "fieldCount": sum(len(item["fields"]) for item in documents),
        "documents": documents,
    }
    manifest_sha = digest(payload)
    payload["manifestSha256"] = manifest_sha
    if output.is_file():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing.get("manifestSha256") != manifest_sha:
            raise SystemExit("Sealed manifest already exists with a different digest")
        print(json.dumps({"status": "ALREADY_SEALED", "manifestSha256": manifest_sha}))
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({
        "status": "SEALED",
        "documentCount": len(documents),
        "fieldCount": payload["fieldCount"],
        "manifestSha256": manifest_sha,
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
