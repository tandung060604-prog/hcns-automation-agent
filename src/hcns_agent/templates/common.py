"""Native-text helpers used by the two approved templates."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.domain.content import iter_text_observations

_DATE_SLASH_RE = re.compile(r"(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})")
_DATE_WORD_RE = re.compile(
    r"ngày\s+(?P<day>\d{1,2})\s+tháng\s+(?P<month>\d{1,2})\s+năm\s+(?P<year>\d{4})",
    flags=re.IGNORECASE,
)


def normalize_for_match(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def document_text(document: CanonicalDocument) -> str:
    return "\n".join(
        unicodedata.normalize("NFC", observation.text).strip()
        for observation in iter_text_observations(document)
        if observation.text.strip()
    )


def extract_unique(
    text: str,
    pattern: str,
    *,
    flags: int = re.IGNORECASE,
) -> tuple[str | None, bool]:
    values = [
        _clean_value(match.group(1))
        for match in re.finditer(pattern, text, flags=flags)
        if _clean_value(match.group(1))
    ]
    distinct: list[str] = []
    normalized: set[str] = set()
    for value in values:
        key = normalize_for_match(value)
        if key in normalized:
            continue
        normalized.add(key)
        distinct.append(value)
    if not distinct:
        return None, False
    if len(distinct) > 1:
        return None, True
    return distinct[0], False


def extract_all(text: str, pattern: str, *, flags: int = re.IGNORECASE) -> tuple[str, ...]:
    return tuple(_clean_value(match.group(1)) for match in re.finditer(pattern, text, flags))


def iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    match = _DATE_SLASH_RE.search(value) or _DATE_WORD_RE.search(value)
    if match is None:
        return None
    try:
        parsed = date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError:
        return None
    return parsed.isoformat()


def named_dates(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in _DATE_WORD_RE.finditer(text):
        parsed = iso_date(match.group(0))
        if parsed is not None:
            values.append(parsed)
    return tuple(values)


def number_value(value: str | None) -> int | float | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value.strip().replace(",", "."))
    except InvalidOperation:
        return None
    if parsed == parsed.to_integral_value():
        return int(parsed)
    return float(parsed)


def clock_time(hour: str | None, minute: str | None) -> str | None:
    if hour is None:
        return None
    try:
        parsed_hour = int(hour)
        parsed_minute = int(minute or "0")
    except ValueError:
        return None
    if not 0 <= parsed_hour <= 23 or not 0 <= parsed_minute <= 59:
        return None
    return f"{parsed_hour:02d}:{parsed_minute:02d}"


def strip_terminal(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().rstrip(" .;,")
    return cleaned or None


def _clean_value(value: str) -> str:
    return " ".join(value.strip().split())
