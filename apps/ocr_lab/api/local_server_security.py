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


def require_local_host_header(host_header: str) -> str:
    """Accept only loopback Host values, with an optional valid port."""

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
    require_loopback_host(host)
    return normalized
