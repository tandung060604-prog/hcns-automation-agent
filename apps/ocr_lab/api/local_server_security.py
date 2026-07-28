"""Network boundary checks for the local OCR API."""

from __future__ import annotations

import ipaddress


def require_loopback_host(host: str) -> str:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return normalized
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as error:
        raise ValueError("OCR Lab API host must be a loopback address") from error
    if not address.is_loopback:
        raise ValueError("OCR Lab API cannot bind outside the local machine")
    return normalized
