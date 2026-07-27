"""Stable error taxonomy for document intake and orchestration."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorKind(str, Enum):
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"


class IntakeErrorCode(str, Enum):
    INVALID_SOURCE = "INVALID_SOURCE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    CONVERSION_REQUIRED = "CONVERSION_REQUIRED"
    CORRUPTED_FILE = "CORRUPTED_FILE"
    ENCRYPTED_DOCUMENT = "ENCRYPTED_DOCUMENT"
    PDF_PAGE_LIMIT_EXCEEDED = "PDF_PAGE_LIMIT_EXCEEDED"
    DANGEROUS_ARCHIVE_PATH = "DANGEROUS_ARCHIVE_PATH"
    ARCHIVE_LIMIT_EXCEEDED = "ARCHIVE_LIMIT_EXCEEDED"
    MACRO_ENABLED_DOCUMENT = "MACRO_ENABLED_DOCUMENT"
    FORMAT_MISMATCH = "FORMAT_MISMATCH"
    NO_PARSER = "NO_PARSER"
    PARSE_FAILED = "PARSE_FAILED"
    TIMEOUT = "TIMEOUT"
    STORAGE_FAILED = "STORAGE_FAILED"


class DocumentIntakeError(Exception):
    def __init__(
        self,
        code: IntakeErrorCode,
        message: str,
        *,
        kind: ErrorKind = ErrorKind.BUSINESS,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.kind = kind
        self.retryable = retryable
        self.details = details or {}
