"""Prediction-blind, local-only annotations for OCR-HO-V2 development diagnostics."""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from phase11_8_shadow_uat import _record, _session_records

FIELDS = {"fullName": 1, "placeOfOrigin": 2, "placeOfResidence": 2}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _path(root: Path) -> Path:
    return root / "OCR_HO_V2_014_DIAGNOSTIC_GT_PRIVATE.json"


def _load(root: Path) -> dict[str, Any]:
    path = _path(root)
    if not path.is_file():
        return {
            "schemaVersion": "ocr-ho-v2-014-diagnostic/1.0.0",
            "localOnly": True,
            "predictionOpened": False,
            "documents": {},
        }
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("documents"), dict):
        raise ValueError("Diagnostic Ground Truth store is invalid")
    return value


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary)


def summary(root: Path) -> dict[str, Any]:
    store = _load(root)
    records = _session_records(root)
    reviewed = {
        document_id
        for document_id, review in store["documents"].items()
        if isinstance(review, dict) and review.get("assertions", {}).get("linesChecked") is True
    }
    return {
        "localOnly": True,
        "predictionLoaded": False,
        "predictionOpened": False,
        "promotionEligible": False,
        "documentCount": len(records),
        "reviewedDocumentCount": len(reviewed),
        "documents": [
            {
                "documentId": item["documentId"],
                "documentIndex": item["documentIndex"],
                "sourceFile": item["sourceFile"],
                "reviewed": item["documentId"] in reviewed,
            }
            for item in records
        ],
    }


def preview(root: Path, document_id: str) -> Path:
    """Return the source-only page whose coordinates match detector boxes."""

    record = _record(root, document_id)
    canonical = record["sessionDir"] / "phase11" / "pages" / "page_000.png"
    return canonical if canonical.is_file() else record["sourcePath"]


def document(root: Path, document_id: str) -> dict[str, Any]:
    record = _record(root, document_id)
    result = json.loads((record["sessionDir"] / "result.json").read_text(encoding="utf-8"))
    page = (result.get("phase11", {}).get("pages") or [{}])[0]
    lines = [
        {"lineId": index, "box": box} for index, box in enumerate(page.get("recognizedBoxes", []))
    ]
    image_size = None
    with Image.open(preview(root, document_id)) as image:
        image_size = [image.width, image.height]
    return {
        "localOnly": True,
        "predictionLoaded": False,
        "predictionOpened": False,
        "documentId": document_id,
        "sourceFile": record["sourceFile"],
        "imageSize": image_size,
        "fields": FIELDS,
        "lines": lines,
        "review": _load(root)["documents"].get(document_id),
    }


def save(root: Path, document_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("predictionOpened") is True:
        raise ValueError("Prediction-blind diagnostic payload cannot open prediction")
    item = document(root, document_id)
    fields = payload.get("fields")
    assertions = payload.get("assertions")
    if (
        not isinstance(fields, dict)
        or not isinstance(assertions, dict)
        or not all(
            assertions.get(key) is True
            for key in ("comparedWithSource", "allTextChecked", "linesChecked")
        )
    ):
        raise ValueError("All fields and source assertions are required")
    valid_ids = {line["lineId"] for line in item["lines"]}
    saved: dict[str, Any] = {}
    for name, maximum in FIELDS.items():
        field = fields.get(name)
        if not isinstance(field, dict):
            raise ValueError(f"Missing diagnostic field: {name}")
        value = str(field.get("value", "")).strip()
        line_ids = field.get("lineIds")
        if not value or len(value) > 500 or _CONTROL.search(value):
            raise ValueError(f"Invalid diagnostic value: {name}")
        if (
            not isinstance(line_ids, list)
            or not 1 <= len(line_ids) <= maximum
            or any(not isinstance(line_id, int) or line_id not in valid_ids for line_id in line_ids)
        ):
            raise ValueError(f"Invalid diagnostic line IDs: {name}")
        saved[name] = {"value": value, "lineIds": line_ids}
    store = _load(root)
    store["documents"][document_id] = {
        "fields": saved,
        "assertions": {"comparedWithSource": True, "allTextChecked": True, "linesChecked": True},
        "predictionOpened": False,
        "reviewedAt": datetime.now(timezone.utc).isoformat(),
    }
    _write(_path(root), store)
    return {"saved": True, "documentId": document_id, "promotionEligible": False}
