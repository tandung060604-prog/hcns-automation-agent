#!/usr/bin/env python3
"""Validate the immutable prediction-blind DATA-23 held-out locks."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_COUNTS = {"contract": 10, "cv": 10, "ielts": 5}
SCAN_FORMATS = {"IMAGE", "PDF_SCAN"}


class HeldoutLockError(ValueError):
    """Raised when a DATA-23 lock is unsafe or incomplete."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HeldoutLockError(f"Invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise HeldoutLockError(f"{path} must contain an object")
    return value


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _cases(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise HeldoutLockError("held-out manifest cases must be an object list")
    return cases


def _validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    cases = _cases(manifest)
    counts: Counter[str] = Counter()
    hashes: set[str] = set()
    case_ids: set[str] = set()
    scan_count = 0
    for case in cases:
        case_id = str(case.get("caseId", "")).strip()
        category = str(case.get("category", "")).strip()
        digest = str(case.get("sourceSha256", "")).strip()
        if not case_id or not category or not digest.startswith("sha256:"):
            raise HeldoutLockError("held-out manifest has an invalid case")
        if case_id in case_ids:
            raise HeldoutLockError(f"duplicate held-out case ID: {case_id}")
        if digest in hashes:
            raise HeldoutLockError(f"duplicate held-out SHA: {digest}")
        case_ids.add(case_id)
        hashes.add(digest)
        counts[category] += 1
        if str(case.get("sourceFormat", "")) in SCAN_FORMATS:
            scan_count += 1
            if case.get("manualReviewRequired", True) is not True:
                raise HeldoutLockError(f"scan is not manual-review-only: {case_id}")
    if dict(counts) != EXPECTED_COUNTS:
        raise HeldoutLockError(f"held-out counts {dict(counts)} != {EXPECTED_COUNTS}")
    return {
        "caseCount": len(cases),
        "counts": dict(sorted(counts.items())),
        "sourceSha256": sorted(hashes),
        "scanCount": scan_count,
    }


def _check_lock(lock: dict[str, Any], name: str, manifest_sha: str) -> None:
    if lock.get("manifestSha256") != manifest_sha:
        raise HeldoutLockError(f"{name} manifest hash does not match")
    if lock.get("predictionsOpened") is not False:
        raise HeldoutLockError(f"{name} says predictions were opened")
    if lock.get("immutable") is not True:
        raise HeldoutLockError(f"{name} is not immutable")


def validate_heldout_lock(
    manifest_path: Path,
    prediction_lock_path: Path,
    ground_truth_lock_path: Path,
    report_path: Path | None = None,
) -> dict[str, Any]:
    manifest = _read(manifest_path)
    prediction_lock = _read(prediction_lock_path)
    ground_truth_lock = _read(ground_truth_lock_path)
    manifest_summary = _validate_manifest(manifest)
    manifest_sha = _canonical_sha256(manifest)
    _check_lock(prediction_lock, "prediction lock", manifest_sha)
    _check_lock(ground_truth_lock, "GroundTruth lock", manifest_sha)
    if prediction_lock.get("predictionSha256") is None:
        raise HeldoutLockError("prediction lock is missing predictionSha256")
    if ground_truth_lock.get("groundTruthSha256") is None:
        raise HeldoutLockError("GroundTruth lock is missing groundTruthSha256")
    if ground_truth_lock.get("groundTruthStatus") != "SEALED":
        raise HeldoutLockError("GroundTruth is not SEALED")
    if ground_truth_lock.get("reviewStatus") != "CONFIRMED":
        raise HeldoutLockError("GroundTruth review is not CONFIRMED")

    for lock, name, digest_key in (
        (prediction_lock, "prediction lock", "predictionSha256"),
        (ground_truth_lock, "GroundTruth lock", "groundTruthSha256"),
    ):
        path_value = lock.get("artifactPath")
        if path_value is not None:
            artifact_path = Path(str(path_value)).expanduser().resolve(strict=True)
            actual = _sha256(artifact_path)
            if actual != lock.get(digest_key):
                raise HeldoutLockError(f"{name} artifact hash does not match")

    report = {
        "schemaVersion": "data23-heldout-lock-report/1.0.0",
        "decision": "PASS",
        "manifestSha256": manifest_sha,
        "manifest": manifest_summary,
        "predictionsOpened": False,
        "predictionLockSha256": _sha256(prediction_lock_path),
        "groundTruthLockSha256": _sha256(ground_truth_lock_path),
        "metricsComputed": False,
        "scanPolicy": "MANUAL_REVIEW",
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
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prediction-lock", type=Path, required=True)
    parser.add_argument("--ground-truth-lock", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = validate_heldout_lock(
            args.manifest,
            args.prediction_lock,
            args.ground_truth_lock,
            args.report,
        )
    except HeldoutLockError as error:
        raise SystemExit(f"DATA-23 lock HOLD: {error}") from error
    print(
        "DATA-23 lock PASS: "
        f"heldout={report['manifest']['caseCount']} predictionsOpened=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
