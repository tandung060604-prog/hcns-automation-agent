"""Inventory, provenance and contract mapping for external document datasets.

The inventory is intentionally separate from benchmark Ground Truth.  It stores
source identities and aggregate metadata, while field values and OCR output stay
in the private staging root.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from hcns_agent.domain.documents import DocumentType, SourceFormat

SUPPORTED_SUFFIXES = frozenset({".txt", ".docx", ".png", ".jpg", ".jpeg", ".pdf", ".pptx"})
CATEGORY_DOCUMENT_TYPES = {
    "cv": DocumentType.CV,
    "contract": DocumentType.EMPLOYMENT_CONTRACT,
    "ielts": DocumentType.CERTIFICATE,
}
PageCounter = Callable[[Path, bytes], tuple[SourceFormat, int]]


class ExternalDatasetError(ValueError):
    """Raised when an external dataset cannot be safely inventoried or verified."""


def provisional_governance(*, today: date | None = None) -> dict[str, object]:
    """Return an explicit, fail-closed governance record for a new dataset."""

    effective_date = today or date.today()
    return {
        "purpose": "local HCNS intake and extraction pilot",
        "rightsBasis": "PENDING_OWNER_CONFIRMATION",
        "dataOwner": "UNCONFIRMED",
        "approvedBy": "UNCONFIRMED",
        "approvalReference": "PENDING_OWNER_CONFIRMATION",
        "approvedAt": effective_date.isoformat(),
        "retentionUntil": (effective_date + timedelta(days=365)).isoformat(),
        "authorizationStatus": "DRAFT",
        "storageProtection": "UNVERIFIED",
        "dataClassification": "CONFIDENTIAL",
    }


def inventory_dataset(
    root: Path,
    *,
    dataset_id: str,
    version: str,
    source_commit: str,
    governance: dict[str, object] | None = None,
    page_counter: PageCounter | None = None,
) -> dict[str, object]:
    root = root.resolve(strict=True)
    if (root / ".git").exists() or any((parent / ".git").exists() for parent in root.parents):
        raise ExternalDatasetError("Dataset root must be outside every Git repository")
    if not dataset_id.strip() or not version.strip() or not source_commit.strip():
        raise ExternalDatasetError("dataset_id, version and source_commit are required")
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ExternalDatasetError("source_commit must be a lowercase 40-character SHA")

    cases: list[dict[str, object]] = []
    category_counters: dict[str, int] = {}
    for source_path in _iter_source_files(root):
        relative = source_path.relative_to(root).as_posix()
        parts = PurePosixPath(relative).parts
        if not parts or parts[0] not in CATEGORY_DOCUMENT_TYPES:
            raise ExternalDatasetError(f"Unsupported dataset category: {relative}")
        category = parts[0]
        category_counters[category] = category_counters.get(category, 0) + 1
        case_id = f"{category}-{category_counters[category]:03d}"
        content = source_path.read_bytes()
        source_format, page_count = (page_counter or _format_and_page_count)(source_path, content)
        cases.append(
            {
                "caseId": case_id,
                "category": category,
                "sourceRelativePath": relative,
                "sourceSha256": _sha256(content),
                "sizeBytes": len(content),
                "sourceFormat": source_format.value,
                "documentType": CATEGORY_DOCUMENT_TYPES[category].value,
                "pageCount": page_count,
            }
        )

    if not cases:
        raise ExternalDatasetError("No supported document files were found")
    cases.sort(key=lambda item: str(item["caseId"]))
    dataset = {
        "datasetId": dataset_id,
        "version": version,
        "sourceCommit": source_commit,
        "contentDigest": _content_digest(dataset_id, version, cases),
        "documentCount": len(cases),
        "pageCount": sum(_integer(case, "pageCount") for case in cases),
        **(governance or provisional_governance()),
    }
    return {"schemaVersion": "1.0.0", "dataset": dataset, "cases": cases}


def validate_inventory(
    root: Path,
    inventory: dict[str, object],
    *,
    page_counter: PageCounter | None = None,
) -> None:
    root = root.resolve(strict=True)
    if (root / ".git").exists() or any((parent / ".git").exists() for parent in root.parents):
        raise ExternalDatasetError("Dataset root must be outside every Git repository")
    dataset = _object(inventory, "dataset")
    cases = _objects(inventory, "cases")
    if _integer(dataset, "documentCount") != len(cases):
        raise ExternalDatasetError("Inventory documentCount does not match cases")
    case_ids: set[str] = set()
    digests: set[str] = set()
    for case in cases:
        case_id = _string(case, "caseId")
        if case_id in case_ids:
            raise ExternalDatasetError("Inventory case IDs must be unique")
        case_ids.add(case_id)
        relative = _string(case, "sourceRelativePath")
        safe_path = PurePosixPath(relative)
        if (
            not relative
            or safe_path.is_absolute()
            or ".." in safe_path.parts
            or "\\" in relative
            or Path(relative).name == "README.md"
            or Path(relative).suffix.lower() not in SUPPORTED_SUFFIXES
        ):
            raise ExternalDatasetError(f"Unsafe or unsupported source path: {relative}")
        source_path = (root / Path(*safe_path.parts)).resolve(strict=True)
        if not source_path.is_file() or not source_path.is_relative_to(root):
            raise ExternalDatasetError(f"Source path escapes dataset root: {relative}")
        content = source_path.read_bytes()
        actual_digest = _sha256(content)
        if actual_digest != _string(case, "sourceSha256"):
            raise ExternalDatasetError(f"Source digest mismatch: {case_id}")
        if actual_digest in digests:
            raise ExternalDatasetError(f"Duplicate source digest: {case_id}")
        digests.add(actual_digest)
        detected_format, page_count = (page_counter or _format_and_page_count)(source_path, content)
        if detected_format.value != _string(case, "sourceFormat"):
            raise ExternalDatasetError(f"Source format drift: {case_id}")
        if page_count != _integer(case, "pageCount"):
            raise ExternalDatasetError(f"Page count drift: {case_id}")
    expected_digest = _content_digest(
        _string(dataset, "datasetId"),
        _string(dataset, "version"),
        cases,
    )
    if expected_digest != _string(dataset, "contentDigest"):
        raise ExternalDatasetError("Inventory contentDigest does not match cases")
    if _integer(dataset, "pageCount") != sum(_integer(case, "pageCount") for case in cases):
        raise ExternalDatasetError("Inventory pageCount does not match cases")


def write_inventory(path: Path, inventory: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_inventory(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExternalDatasetError("Inventory is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict) or payload.get("schemaVersion") != "1.0.0":
        raise ExternalDatasetError("Unsupported external dataset inventory schema")
    return payload


def validate_mapping(inventory: dict[str, object], mapping: dict[str, object]) -> None:
    """Fail closed when the contract mapping drifts from an inventory version."""

    dataset = _object(inventory, "dataset")
    for key in ("datasetId", "version", "sourceCommit"):
        if _string(mapping, "datasetVersion" if key == "version" else key) != _string(
            dataset,
            key,
        ):
            raise ExternalDatasetError(f"Mapping {key} does not match inventory")
    if mapping.get("promotionAllowed") is not False:
        raise ExternalDatasetError("External dataset mapping must keep promotion disabled")
    cases = _objects(inventory, "cases")
    expected = {
        str(case["category"]): str(case["documentType"])
        for case in cases
    }
    mappings = _objects(mapping, "mappings")
    seen: set[str] = set()
    for item in mappings:
        category = _string(item, "category")
        if category in seen or category not in expected:
            raise ExternalDatasetError(f"Mapping category is missing or duplicated: {category}")
        seen.add(category)
        if _string(item, "documentType") != expected[category]:
            raise ExternalDatasetError(f"Mapping documentType drift: {category}")
        if (
            _string(item, "route") != "GENERIC_IDP"
            or _string(item, "templateFirst") != "UNSUPPORTED"
        ):
            raise ExternalDatasetError(f"Mapping route is not fail-closed: {category}")
    if seen != set(expected):
        raise ExternalDatasetError("Mapping does not cover every inventory category")


def _iter_source_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in root.rglob("*")
                if path.is_file()
                and ".git" not in path.parts
                and path.name != "README.md"
                and path.suffix.lower() in SUPPORTED_SUFFIXES
            ),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    )


def _format_and_page_count(path: Path, content: bytes) -> tuple[SourceFormat, int]:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ExternalDatasetError(f"TXT source is not UTF-8: {path.name}") from error
        return SourceFormat.PLAIN_TEXT, 1
    if suffix == ".pdf":
        raise ExternalDatasetError(
            "PDF page counting requires the adapter page counter; "
            f"pass it explicitly for {path.name}"
        )
    if suffix in {".png", ".jpg", ".jpeg"}:
        raise ExternalDatasetError(
            "Image verification requires the adapter page counter; "
            f"pass it explicitly for {path.name}"
        )
    if suffix == ".pptx":
        try:
            with ZipFile(BytesIO(content)) as archive:
                slide_count = sum(
                    1
                    for name in archive.namelist()
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                )
        except (BadZipFile, OSError) as error:
            raise ExternalDatasetError(f"Invalid PPTX source: {path.name}") from error
        return SourceFormat.PPTX, max(1, slide_count)
    if suffix == ".docx":
        try:
            with ZipFile(BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ExternalDatasetError(f"Invalid DOCX source: {path.name}")
        except (BadZipFile, OSError) as error:
            raise ExternalDatasetError(f"Invalid DOCX source: {path.name}") from error
        return SourceFormat.DOCX, 1
    raise ExternalDatasetError(f"Unsupported dataset suffix: {suffix}")


def _content_digest(dataset_id: str, version: str, cases: list[dict[str, object]]) -> str:
    payload = {
        "datasetId": dataset_id,
        "version": version,
        "cases": [
            {
                key: case[key]
                for key in (
                    "caseId",
                    "sourceRelativePath",
                    "sourceSha256",
                    "pageCount",
                    "sourceFormat",
                    "documentType",
                )
            }
            for case in sorted(cases, key=lambda item: str(item["caseId"]))
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ExternalDatasetError(f"Inventory {key} must be an object")
    return value


def _objects(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ExternalDatasetError(f"Inventory {key} must be an object list")
    return value


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExternalDatasetError(f"Inventory {key} must be a non-empty string")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExternalDatasetError(f"Inventory {key} must be an integer")
    return value
