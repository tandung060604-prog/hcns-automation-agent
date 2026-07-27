"""Atomic local result store with opaque result references."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from hcns_agent.domain.canonical import ResultReference
from hcns_agent.domain.documents import (
    DocumentType,
    ParseStatus,
    SourceFormat,
)
from hcns_agent.domain.errors import (
    DocumentIntakeError,
    ErrorKind,
    IntakeErrorCode,
)
from hcns_agent.domain.understanding import IdpResult, QualityStatus
from hcns_agent.ports.orchestration import StoredDocumentResult


class JsonFileResultStore:
    """Persist IDP result JSON and a minimal idempotency index under an explicit root."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise ValueError("Result store root must be an absolute path")
        self._root = root.resolve()
        self._documents = self._root / "documents"
        self._index = self._root / "idempotency"
        self._documents.mkdir(parents=True, exist_ok=True)
        self._index.mkdir(parents=True, exist_ok=True)

    def find_by_idempotency_key(self, idempotency_key: str) -> StoredDocumentResult | None:
        index_path = self._index_path(idempotency_key)
        if not index_path.exists():
            return None
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            reference = ResultReference(
                uri=str(payload["uri"]),
                checksum_sha256=str(payload["checksumSha256"]),
                schema_version=str(payload["schemaVersion"]),
                storage_version=str(payload["storageVersion"]),
            )
            return StoredDocumentResult(
                reference=reference,
                document_id=str(payload["documentId"]),
                source_format=SourceFormat(str(payload["sourceFormat"])),
                parse_status=ParseStatus(str(payload["parseStatus"])),
                document_type=DocumentType(str(payload["documentType"])),
                quality_status=QualityStatus(str(payload["qualityStatus"])),
                review_required=bool(payload["reviewRequired"]),
                schema_version=str(payload["schemaVersion"]),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise DocumentIntakeError(
                IntakeErrorCode.STORAGE_FAILED,
                "Stored idempotency metadata is unreadable",
                kind=ErrorKind.TECHNICAL,
                retryable=False,
            ) from error

    def save(self, result: IdpResult, *, idempotency_key: str) -> StoredDocumentResult:
        existing = self.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        document = result.canonical_document
        storage_key = sha256(f"{document.document_id}:{idempotency_key}".encode()).hexdigest()
        document_path = self._documents / f"{storage_key}.json"
        document_payload = json.dumps(
            asdict(result),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        ).encode("utf-8")
        checksum = sha256(document_payload).hexdigest()
        reference = ResultReference(
            uri=f"document-store://{storage_key}",
            checksum_sha256=checksum,
            schema_version=result.schema_version,
            storage_version="json-v1",
        )
        index_payload = {
            "documentId": document.document_id,
            "sourceFormat": document.source_format.value,
            "parseStatus": document.parse_status.value,
            "documentType": result.classification.document_type.value,
            "qualityStatus": result.quality.status.value,
            "reviewRequired": result.quality.review_required,
            "schemaVersion": result.schema_version,
            "storageVersion": reference.storage_version,
            "uri": reference.uri,
            "checksumSha256": checksum,
        }
        try:
            _atomic_write(document_path, document_payload)
            _atomic_write(
                self._index_path(idempotency_key),
                json.dumps(
                    index_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
        except OSError as error:
            raise DocumentIntakeError(
                IntakeErrorCode.STORAGE_FAILED,
                "IDP result could not be persisted",
                kind=ErrorKind.TECHNICAL,
                retryable=True,
            ) from error

        return StoredDocumentResult(
            reference=reference,
            document_id=document.document_id,
            source_format=document.source_format,
            parse_status=document.parse_status,
            document_type=result.classification.document_type,
            quality_status=result.quality.status,
            review_required=result.quality.review_required,
            schema_version=result.schema_version,
        )

    def _index_path(self, idempotency_key: str) -> Path:
        key_hash = sha256(idempotency_key.encode("utf-8")).hexdigest()
        return self._index / f"{key_hash}.json"


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Unsupported canonical JSON value: {type(value).__name__}")
