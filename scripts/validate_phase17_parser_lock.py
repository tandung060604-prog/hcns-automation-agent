#!/usr/bin/env python3
"""Validate the frozen Phase 17 parser, table contract and safety policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = REPOSITORY_ROOT / "config" / "phase17_parser_lock.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Expected a JSON object")
    return value


def validate_lock(lock_path: Path = LOCK_PATH) -> dict[str, Any]:
    lock = read_json(lock_path)
    if lock.get("parserVersion") != "phase17-structured-hr-parser/2.0.0":
        raise ValueError("Unexpected Phase 17 parser version")
    if lock.get("mode") != "SHADOW_REVIEW_ONLY":
        raise ValueError("Phase 17 parser must remain review-only")
    if lock.get("sensitiveOcrAutoAccept") is not False:
        raise ValueError("Sensitive OCR auto-accept must remain disabled")
    artifacts = lock.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Parser lock has no artifacts")
    for artifact in artifacts:
        relative = Path(str(artifact["path"]))
        candidate = (REPOSITORY_ROOT / relative).resolve()
        if REPOSITORY_ROOT not in candidate.parents:
            raise ValueError("Locked artifact escaped the repository")
        if not candidate.is_file():
            raise FileNotFoundError(f"Locked artifact is missing: {relative}")
        actual = sha256_file(candidate)
        if actual != artifact.get("sha256"):
            raise ValueError(f"Locked artifact changed: {relative}")
    return lock


def main() -> int:
    lock = validate_lock()
    print(
        "Phase 17 parser lock verified: "
        f"artifacts={len(lock['artifacts'])}, "
        f"parser={lock['parserVersion']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
