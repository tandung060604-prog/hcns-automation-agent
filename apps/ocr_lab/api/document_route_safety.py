"""Pure routing safeguards shared by the local OCR pipeline."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def selected_orientations_are_identity(
    orientation_pages: list[dict[str, Any]],
) -> bool:
    """Route only when every selected page, not any rejected rotation, is ID-like."""
    return bool(orientation_pages) and all(
        page.get("selectedIdentityLikely") is True
        for page in orientation_pages
    )


def safe_existing_document_route(
    existing_route: str | None,
    plain_text: str,
) -> str | None:
    """Drop a stale identity route when independent CV sections contradict it."""
    if existing_route != "IDENTITY_DOCUMENT":
        return existing_route
    decomposed = unicodedata.normalize("NFD", str(plain_text).casefold())
    normalized = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    markers = (
        "kinh nghiem",
        "hoc van",
        "ky nang",
        "portfolio",
        "muc tieu nghe nghiep",
    )
    if sum(marker in normalized for marker in markers) >= 2:
        return None
    return existing_route
