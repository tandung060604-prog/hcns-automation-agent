"""Native-text helpers used by the two approved templates."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.domain.content import TextObservation, iter_text_observations

_DATE_SLASH_RE = re.compile(r"(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})")
_DATE_WORD_RE = re.compile(
    r"ngày\s+(?P<day>\d{1,2})\s+tháng\s+(?P<month>\d{1,2})\s+năm\s+(?P<year>\d{4})",
    flags=re.IGNORECASE,
)


def normalize_for_match(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def normalize_for_ocr_match(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value).casefold()
    without_marks = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(without_marks.replace("đ", "d").split())


def fuzzy_ocr_contains(text: str, anchor: str, *, threshold: float = 0.78) -> bool:
    """Match short fixed labels after OCR drops Vietnamese characters."""

    normalized_text = normalize_for_ocr_match(text)
    normalized_anchor = normalize_for_ocr_match(anchor)
    if normalized_anchor in normalized_text:
        return True
    words = normalized_text.split()
    anchor_words = normalized_anchor.split()
    for size in range(max(1, len(anchor_words) - 1), len(anchor_words) + 2):
        for start in range(0, len(words) - size + 1):
            candidate = " ".join(words[start : start + size])
            if SequenceMatcher(None, candidate, normalized_anchor).ratio() >= threshold:
                return True
    return False


def document_text(document: CanonicalDocument) -> str:
    return "\n".join(
        unicodedata.normalize("NFC", observation.text).strip()
        for observation in iter_text_observations(document)
        if observation.text.strip()
    )


def ocr_lines(document: CanonicalDocument) -> tuple[TextObservation, ...]:
    """Return text observations that carry OCR geometry when available."""
    return tuple(iter_text_observations(document))


def ocr_roi_evidence(
    document: CanonicalDocument,
    field_name: str | None = None,
) -> tuple[dict[str, object], ...]:
    """Read adapter-produced ROI evidence without making it a data source.

    Evidence is provenance only: parsers still validate and only use a candidate
    when the corresponding field is absent from the primary parse.
    """
    for provenance in reversed(document.provenance):
        raw = provenance.metadata.get("ocrRoiEvidence")
        if not isinstance(raw, str):
            continue
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return ()
        if not isinstance(decoded, list):
            return ()
        values = tuple(
            item
            for item in decoded
            if isinstance(item, dict)
            and (field_name is None or item.get("field") == field_name)
        )
        return values
    return ()


def ocr_line_value(
    text: str,
    labels: tuple[str, ...],
    *,
    stop_labels: tuple[str, ...] = (),
) -> str | None:
    """Extract the value portion of an OCR line after a fixed label.

    OCR frequently keeps the colon but drops Vietnamese marks. The helper uses a
    tolerant label check and never invents a value when no label is present.
    """
    if not any(fuzzy_ocr_contains(text, label, threshold=0.62) for label in labels):
        return None
    value = text
    if ":" in value:
        value = value.split(":", 1)[1]
    else:
        # Normalization removes combining marks and can change the number of
        # code points, so slicing the original string with the normalized
        # offset is unsafe. Locate the label by word spans instead.
        original_words = list(re.finditer(r"\S+", value))
        normalized_words = [
            normalize_for_ocr_match(match.group(0)) for match in original_words
        ]
        best_match: tuple[float, int, int] | None = None
        for label in labels:
            anchor_words = normalize_for_ocr_match(label).split()
            if not anchor_words:
                continue
            for start in range(len(normalized_words)):
                for size in range(max(1, len(anchor_words) - 1), len(anchor_words) + 2):
                    end = start + size
                    if end > len(normalized_words):
                        continue
                    candidate = " ".join(normalized_words[start:end])
                    score = SequenceMatcher(
                        None, candidate, " ".join(anchor_words)
                    ).ratio()
                    if score >= 0.62 and (
                        best_match is None or score > best_match[0]
                    ):
                        best_match = (score, start, end)
        if best_match is not None:
            _, start, end = best_match
            value = value[original_words[end - 1].end() :]
    for stop_label in stop_labels:
        match = re.search(
            re.escape(stop_label),
            value,
            flags=re.IGNORECASE,
        )
        if match:
            value = value[: match.start()]
    return strip_terminal(value)


def repair_template_ocr_value(value: object, field_name: str) -> object:
    """Apply conservative vocabulary repairs to short HR fields.

    PP-OCRv5 latin occasionally drops Vietnamese code points in stable HR
    vocabulary (for example ``K sư`` or ``Cng ngh``). This is not a lookup of
    document data: only fixed vocabulary fragments are repaired, and unknown
    names/free text are returned unchanged for human review.
    """
    if field_name not in {"jobTitle", "department"} or not isinstance(value, str):
        return value
    replacements = (
        ("Tuyn dng", "Tuyển dụng"),
        ("K sư", "Kỹ sư"),
        ("K toán", "Kế toán"),
        ("Cng ngh", "Công nghệ"),
        ("Công ngh", "Công nghệ"),
        ("D liu", "Dữ liệu"),
        ("Nhân s", "Nhân sự"),
        ("nhân s", "nhân sự"),
    )
    repaired = value
    for source, target in replacements:
        repaired = repaired.replace(source, target)
    return repaired


def trim_ocr_commitment(value: str | None) -> str | None:
    """Drop boilerplate after a free-text template field.

    The commitment/signature block is not part of ``reason`` or
    ``workContent``. OCR often joins it to the preceding line, so the parser
    needs a conservative boundary that is independent of document values.
    """
    if value is None:
        return None
    markers = (
        r"\b(?:tôi|toi|ti)\s+cam\s+k\w{0,4}t\b",
        r"\b(?:kính|kinh)\s+mong\b",
        r"\bngu(?:ờ|o|ò)?i\s+lam\s+don\b",
    )
    cut = len(value)
    for marker in markers:
        match = re.search(marker, value, flags=re.IGNORECASE)
        if match:
            cut = min(cut, match.start())
    return strip_terminal(value[:cut])


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
    cleaned = " ".join(value.split()).rstrip(" .;,")
    return cleaned or None


def _clean_value(value: str) -> str:
    return " ".join(value.strip().split())
