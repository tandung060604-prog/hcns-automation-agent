#!/usr/bin/env python3
"""Fail-closed validation for the private DATA-22 development/held-out split."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

FAMILIES = ("contract", "cv", "ielts")
SCAN_FORMATS = {"IMAGE", "PDF_SCAN"}


class SplitValidationError(ValueError):
    """Raised when a split cannot be accepted."""


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SplitValidationError(f"{name} must be an object")
    return value


def _cases(payload: dict[str, Any], name: str) -> list[dict[str, Any]]:
    value = payload.get("cases")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SplitValidationError(f"{name}.cases must be an object list")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SplitValidationError(f"Invalid JSON: {path}") from error
    return _object(value, str(path))


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _safe_source(root: Path, relative: str) -> Path:
    parsed = PurePosixPath(relative)
    if (
        not relative
        or parsed.is_absolute()
        or ".." in parsed.parts
        or "\\" in relative
    ):
        raise SplitValidationError(f"Unsafe source path: {relative}")
    source = (root / Path(*parsed.parts)).resolve(strict=True)
    if not source.is_file() or not source.is_relative_to(root):
        raise SplitValidationError(f"Source path escapes root: {relative}")
    return source


def _root(policy: dict[str, Any], split: str) -> Path:
    roots = _object(policy.get("roots"), "policy.roots")
    value = roots.get(split)
    if not isinstance(value, str) or not value.strip():
        raise SplitValidationError(f"policy.roots.{split} is required")
    return Path(value).expanduser().resolve(strict=True)


def _expected(policy: dict[str, Any], split: str) -> dict[str, int]:
    values = _object(policy.get(split), f"policy.{split}")
    expected: dict[str, int] = {}
    for family in FAMILIES:
        value = values.get(family)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SplitValidationError(f"policy.{split}.{family} must be a non-negative integer")
        expected[family] = value
    return expected


def _metadata_checks(
    payload: dict[str, Any], name: str, *, require_approved: bool = True
) -> None:
    dataset = _object(payload.get("dataset"), f"{name}.dataset")
    if require_approved and dataset.get("authorizationStatus") != "APPROVED":
        raise SplitValidationError(f"{name} authorizationStatus is not APPROVED")
    retention = dataset.get("retentionUntil")
    try:
        retention_date = date.fromisoformat(str(retention))
    except ValueError as error:
        raise SplitValidationError(f"{name} retentionUntil is invalid") from error
    if retention_date < date.today():
        raise SplitValidationError(f"{name} retentionUntil has expired")


def _validate_cases(
    payload: dict[str, Any],
    name: str,
    root: Path,
) -> tuple[set[str], set[str], Counter[str], int]:
    cases = _cases(payload, name)
    hashes: set[str] = set()
    lineages: set[str] = set()
    counts: Counter[str] = Counter()
    scan_count = 0
    for case in cases:
        case_id = str(case.get("caseId", "")).strip()
        family = str(case.get("category", "")).strip()
        digest = str(case.get("sourceSha256", "")).strip()
        if not case_id or family not in FAMILIES or not digest.startswith("sha256:"):
            raise SplitValidationError(f"{name} contains an invalid case identity")
        if digest in hashes:
            raise SplitValidationError(f"{name} contains duplicate SHA: {digest}")
        hashes.add(digest)
        lineage = str(case.get("lineageId") or digest)
        derivative = case.get("derivativeOf")
        if derivative is not None and not isinstance(derivative, str):
            raise SplitValidationError(f"{name} derivativeOf must be a string or null")
        if lineage in lineages:
            raise SplitValidationError(f"{name} contains duplicate lineage: {lineage}")
        lineages.add(lineage)
        counts[family] += 1
        if str(case.get("sourceFormat", "")) in SCAN_FORMATS:
            scan_count += 1
        relative = str(case.get("sourceRelativePath", ""))
        source = _safe_source(root, relative)
        if _sha256(source) != digest:
            raise SplitValidationError(f"{name} source digest mismatch: {case_id}")
    return hashes, lineages, counts, scan_count


def validate_splits(
    development_inventory: Path,
    heldout_inventory: Path,
    policy_path: Path,
    report_path: Path | None = None,
) -> dict[str, Any]:
    policy = _read_json(policy_path)
    development = _read_json(development_inventory)
    heldout = _read_json(heldout_inventory)
    _metadata_checks(development, "development")
    _metadata_checks(heldout, "heldout")
    dev_root = _root(policy, "development")
    heldout_root = _root(policy, "heldout")
    dev_hashes, dev_lineages, dev_counts, dev_scans = _validate_cases(
        development, "development", dev_root
    )
    heldout_hashes, heldout_lineages, heldout_counts, heldout_scans = _validate_cases(
        heldout, "heldout", heldout_root
    )
    expected_dev = _expected(policy, "development")
    expected_heldout = _expected(policy, "heldout")
    if dict(dev_counts) != expected_dev:
        raise SplitValidationError(f"development counts {dict(dev_counts)} != {expected_dev}")
    if dict(heldout_counts) != expected_heldout:
        raise SplitValidationError(
            f"heldout counts {dict(heldout_counts)} != {expected_heldout}"
        )
    if dev_hashes & heldout_hashes:
        raise SplitValidationError("development and heldout SHA overlap")
    if dev_lineages & heldout_lineages:
        raise SplitValidationError("development and heldout lineage overlap")

    history_hashes: set[str] = set()
    history_lineages: set[str] = set()
    history = policy.get("history", [])
    if not isinstance(history, list):
        raise SplitValidationError("policy.history must be a list")
    for index, entry in enumerate(history):
        item = _object(entry, f"policy.history[{index}]")
        inventory = item.get("inventory")
        root_value = item.get("root")
        if not isinstance(inventory, str) or not isinstance(root_value, str):
            raise SplitValidationError(f"policy.history[{index}] requires inventory and root")
        history_payload = _read_json(Path(inventory))
        _metadata_checks(history_payload, f"history[{index}]", require_approved=False)
        hashes, lineages, _, _ = _validate_cases(
            history_payload, f"history[{index}]", Path(root_value).expanduser().resolve(strict=True)
        )
        history_hashes |= hashes
        history_lineages |= lineages
    if (dev_hashes | heldout_hashes) & history_hashes:
        raise SplitValidationError("split overlaps historical SHA")
    if (dev_lineages | heldout_lineages) & history_lineages:
        raise SplitValidationError("split overlaps historical lineage")

    total = {family: dev_counts[family] + heldout_counts[family] for family in FAMILIES}
    report: dict[str, Any] = {
        "schemaVersion": "data22-split-report/1.0.0",
        "decision": "PASS",
        "development": {
            "counts": dict(sorted(dev_counts.items())),
            "documentCount": sum(dev_counts.values()),
            "scanCount": dev_scans,
        },
        "heldout": {
            "counts": dict(sorted(heldout_counts.items())),
            "documentCount": sum(heldout_counts.values()),
            "scanCount": heldout_scans,
        },
        "totalByFamily": total,
        "overlap": {"sha256": 0, "lineage": 0, "history": 0},
        "policy": {
            "scanReviewAction": "MANUAL_REVIEW",
            "rawArtifactsTracked": False,
        },
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-inventory", type=Path, required=True)
    parser.add_argument("--heldout-inventory", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = validate_splits(
            args.development_inventory,
            args.heldout_inventory,
            args.policy,
            args.report,
        )
    except SplitValidationError as error:
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(
                    {
                        "schemaVersion": "data22-split-report/1.0.0",
                        "decision": "HOLD",
                        "reason": str(error),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        raise SystemExit(f"DATA-22 split HOLD: {error}") from error
    print(
        "DATA-22 split PASS: "
        f"development={report['development']['documentCount']} "
        f"heldout={report['heldout']['documentCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
