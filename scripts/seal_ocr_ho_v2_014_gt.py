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
    if len(records) != 15 or len(store.get("documents", {})) != len(records):
        raise SystemExit("Expected 15 complete eligible documents")
    if output.is_file():
        existing = json.loads(output.read_text(encoding="utf-8"))
        existing_digest = existing.get("manifestSha256")
        unsigned = {key: value for key, value in existing.items() if key != "manifestSha256"}
        if existing_digest != digest(unsigned):
            raise SystemExit("Sealed manifest is corrupt or was modified")
        print(json.dumps({"status": "ALREADY_SEALED", "manifestSha256": existing_digest}))
        return 0
    documents: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        review = store["documents"].get(record["documentId"])
        assertions = review.get("assertions", {}) if isinstance(review, dict) else {}
        if not isinstance(review, dict) or review.get("draft") is not False or not all(
            assertions.get(key) is True for key in ("comparedWithSource", "allTextChecked", "linesChecked")
        ):
            raise SystemExit(f"Document {record['documentId']} is not fully checked")
        detail = _record(root, record["documentId"])
        result = json.loads((detail["sessionDir"] / "result.json").read_text(encoding="utf-8"))
        line_count = len((result.get("phase11", {}).get("pages") or [{}])[0].get("recognizedBoxes", []))
        fields: dict[str, Any] = {}
        for name, maximum in FIELDS.items():
            field = review.get("fields", {}).get(name) or {}
            value = str(field.get("value") or "").strip()
            line_ids = field.get("lineIds")
            if not value or not isinstance(line_ids, list) or not 1 <= len(line_ids) <= maximum:
                raise SystemExit(f"Invalid sealed field {record['documentId']}:{name}")
            if any(not isinstance(line_id, int) or line_id < 0 or line_id >= line_count for line_id in line_ids):
                raise SystemExit(f"Invalid line ID {record['documentId']}:{name}")
            fields[name] = {"value": value, "lineIds": line_ids}
            # recognizedBoxes are indexed; keep this validation independent of OCR text.
            if any(line_id >= line_count for line_id in line_ids):
                raise SystemExit(f"Line ID out of range {record['documentId']}:{name}")
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
