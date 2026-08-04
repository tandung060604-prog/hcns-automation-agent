"""Private correction and reviewer-audit artifacts for the M4 shadow flow."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

from hcns_agent.adapters.camunda7.contract import ProcessValue

_CORRECTION_REFERENCE_PATTERN = re.compile(
    r"camunda-m4://correction/([0-9a-f]{64})"
)
_AUDIT_REFERENCE_PATTERN = re.compile(
    r"camunda-m4://review-audit/([0-9a-f]{64})"
)
_FIELD_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]{0,127}")
_PAYLOAD_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


class ReviewArtifactStoreError(RuntimeError):
    """A private correction or review-audit artifact is unavailable."""


@dataclass(frozen=True, slots=True)
class CorrectionArtifact:
    reference: str
    result_reference: str
    expected_payload_hash: str
    changes: dict[str, object]


class JsonFileCorrectionStore:
    """Content-addressed private correction artifacts written outside Camunda."""

    def __init__(self, root: Path) -> None:
        self._root = _prepare_directory(root, "corrections")

    def save(
        self,
        *,
        result_reference: str,
        expected_payload_hash: str,
        changes: Mapping[str, object],
    ) -> str:
        if not result_reference.strip():
            raise ValueError("Result reference is required")
        if _PAYLOAD_HASH_PATTERN.fullmatch(expected_payload_hash) is None:
            raise ValueError("Expected payload hash is invalid")
        _validate_changes(changes)
        payload: dict[str, object] = {
            "resultReference": result_reference,
            "expectedPayloadHash": expected_payload_hash,
            "changes": dict(changes),
        }
        digest = _payload_digest(payload)
        path = self._root / f"{digest}.json"
        try:
            if path.exists():
                if _read_json_object(path) != payload:
                    raise ReviewArtifactStoreError("Correction artifact hash collision")
            else:
                _atomic_write_json(path, payload)
        except OSError as error:
            raise ReviewArtifactStoreError("Correction artifact could not be persisted") from error
        return f"camunda-m4://correction/{digest}"

    def load(self, reference: str) -> CorrectionArtifact:
        match = _CORRECTION_REFERENCE_PATTERN.fullmatch(reference)
        if match is None:
            raise ReviewArtifactStoreError("Correction reference is invalid")
        digest = match.group(1)
        try:
            payload = _read_json_object(self._root / f"{digest}.json")
        except (OSError, json.JSONDecodeError) as error:
            raise ReviewArtifactStoreError("Correction artifact is unreadable") from error
        if _payload_digest(payload) != digest:
            raise ReviewArtifactStoreError("Correction artifact integrity check failed")
        result_reference = payload.get("resultReference")
        expected_payload_hash = payload.get("expectedPayloadHash")
        changes = payload.get("changes")
        if (
            not isinstance(result_reference, str)
            or _PAYLOAD_HASH_PATTERN.fullmatch(str(expected_payload_hash)) is None
            or not isinstance(changes, dict)
        ):
            raise ReviewArtifactStoreError("Correction artifact is inconsistent")
        try:
            _validate_changes(cast(Mapping[str, object], changes))
        except ValueError as error:
            raise ReviewArtifactStoreError("Correction artifact is inconsistent") from error
        return CorrectionArtifact(
            reference=reference,
            result_reference=result_reference,
            expected_payload_hash=str(expected_payload_hash),
            changes=cast(dict[str, object], changes),
        )


class JsonFileReviewAuditStore:
    """Append-only content-addressed reviewer audit records."""

    def __init__(self, root: Path) -> None:
        self._root = _prepare_directory(root, "review_audits")

    def record(self, event: Mapping[str, ProcessValue]) -> str:
        if not event or any(value is None for value in event.values()):
            raise ValueError("Review audit event must be complete")
        payload = dict(event)
        digest = _payload_digest(payload)
        path = self._root / f"{digest}.json"
        try:
            if path.exists():
                if _read_json_object(path) != payload:
                    raise ReviewArtifactStoreError("Review audit hash collision")
            else:
                _atomic_write_json(path, payload)
        except OSError as error:
            raise ReviewArtifactStoreError("Review audit could not be persisted") from error
        return f"camunda-m4://review-audit/{digest}"

    def load(self, reference: str) -> dict[str, object]:
        match = _AUDIT_REFERENCE_PATTERN.fullmatch(reference)
        if match is None:
            raise ReviewArtifactStoreError("Review audit reference is invalid")
        digest = match.group(1)
        try:
            payload = _read_json_object(self._root / f"{digest}.json")
        except (OSError, json.JSONDecodeError) as error:
            raise ReviewArtifactStoreError("Review audit is unreadable") from error
        if _payload_digest(payload) != digest:
            raise ReviewArtifactStoreError("Review audit integrity check failed")
        return payload


def _prepare_directory(root: Path, child: str) -> Path:
    if not root.is_absolute():
        raise ValueError("Review artifact store root must be absolute")
    directory = root.resolve() / child
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ReviewArtifactStoreError("Review artifact store is unavailable") from error
    return directory


def _validate_changes(changes: Mapping[str, object]) -> None:
    if not changes:
        raise ValueError("At least one correction is required")
    for name, value in changes.items():
        if _FIELD_NAME_PATTERN.fullmatch(name) is None:
            raise ValueError("Correction field name is invalid")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("Correction values must be scalar")
        if isinstance(value, str) and len(value) > 16_384:
            raise ValueError("Correction value is too long")


def _payload_digest(payload: Mapping[str, object]) -> str:
    return sha256(_canonical_json(payload)).hexdigest()


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("JSON object required", "", 0)
    return cast(dict[str, object], payload)


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=".write-",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_json(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
