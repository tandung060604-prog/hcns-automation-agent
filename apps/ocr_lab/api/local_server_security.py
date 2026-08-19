"""Network boundary checks for the local OCR API."""

from __future__ import annotations

import ipaddress
import os


def _extra_allowed_hosts() -> set[str]:
    raw = os.getenv("HCNS_API_ALLOWED_HOSTS", "").strip()
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _host_allowed(host: str) -> bool:
    for pattern in _extra_allowed_hosts():
        if pattern.startswith("*."):
            suffix = pattern[1:]
            if host.endswith(suffix):
                return True
        elif host == pattern:
            return True
    return False


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


def require_local_host_header(host_header: str) -> str:
    """Accept loopback Host values (plus an optional env allowlist)."""

    normalized = host_header.strip().lower()
    if not normalized:
        raise ValueError("OCR Lab API Host header is required")

    if normalized.startswith("["):
        closing = normalized.find("]")
        if closing < 0:
            raise ValueError("OCR Lab API Host header is invalid")
        host = normalized[1:closing]
        port = normalized[closing + 1 :]
    elif normalized.count(":") > 1:
        host = normalized
        port = ""
    else:
        host, separator, port_number = normalized.partition(":")
        port = f":{port_number}" if separator else ""

    if port:
        if not port.startswith(":") or not port[1:].isdigit():
            raise ValueError("OCR Lab API Host header port is invalid")
        if not 1 <= int(port[1:]) <= 65535:
            raise ValueError("OCR Lab API Host header port is invalid")

    extra = _extra_allowed_hosts()
    if extra and _host_allowed(host):
        return normalized

    require_loopback_host(host)
    return normalized
