"""Canonical Contract, CV and IELTS field parser shared by runtime and evidence."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.domain.content import iter_text_observations
from hcns_agent.domain.documents import DocumentType, SourceFormat
from hcns_agent.templates.model import ParsedTemplate, TemplateDetection

STRUCTURED_HR_PARSER_ID = "structured-hr/family-layout"
STRUCTURED_HR_PARSER_VERSION = "2.2.8"

_LIST_PREFIX = re.compile(r"^\s*(?:(?:\d{1,3}[.)])|[-–—•▪◦])\s*")

_SECTION_HEADINGS = frozenset(
    {
        "muc tieu nghe nghiep",
        "hoc van",
        "kinh nghiem",
        "kinh nghiem lam viec",
        "ky nang",
        "chung chi",
        "du an",
        "so thich",
        "nguoi tham chieu",
    }
)


class StructuredHrParser:
    """Parse the three DATA-29 families from the canonical document model."""

    version = STRUCTURED_HR_PARSER_VERSION

    def parse(
        self,
        document: CanonicalDocument,
        detection: TemplateDetection,
    ) -> ParsedTemplate:
        category = {
            DocumentType.CV: "cv",
            DocumentType.EMPLOYMENT_CONTRACT: "contract",
            DocumentType.CERTIFICATE: "ielts",
        }.get(detection.definition.document_type)
        if category is None:
            raise ValueError("Structured HR parser received an unsupported document type")
        fields = extract_structured_hr_fields(
            _legacy_document(document),
            category,
            ocr=document.source_format in {SourceFormat.IMAGE, SourceFormat.PDF_SCAN},
        )
        data: dict[str, object] = {
            "documentId": document.document_id,
            "documentType": detection.definition.document_type.value,
            "templateId": detection.definition.template_id,
            "templateVersion": detection.definition.version,
            "schemaVersion": detection.definition.schema_version,
            "sourceFile": document.source.filename,
        }
        for name, field in fields.items():
            value = field.get("normalizedValue")
            data[name] = field.get("value") if value is None else value
        return ParsedTemplate(data=data)


def extract_structured_hr_fields(
    canonical: Mapping[str, Any],
    category: str,
    *,
    ocr: bool,
) -> dict[str, dict[str, Any]]:
    """Return the field contract used by both DATA-29 and Template-first runtime."""

    if category == "cv":
        return _cv_fields(canonical, ocr=ocr)
    if category == "contract":
        return _contract_fields(canonical, ocr=ocr)
    if category == "ielts":
        return _ielts_fields(canonical, review=ocr)
    raise ValueError(f"Unsupported structured HR category: {category}")


def _legacy_document(document: CanonicalDocument) -> dict[str, Any]:
    pages: dict[int, list[dict[str, Any]]] = {}
    source_kind = (
        "ocr" if document.source_format in {SourceFormat.IMAGE, SourceFormat.PDF_SCAN} else "native"
    )
    for observation in iter_text_observations(document):
        location = observation.source
        page_index = location.page_index or 0
        box = location.bounding_box
        evidence: dict[str, Any] = {
            "pageIndex": page_index,
            "sourceRef": location.source_reference,
        }
        if box is not None:
            evidence["bbox"] = [
                [box.x0, box.y0],
                [box.x1, box.y0],
                [box.x1, box.y1],
                [box.x0, box.y1],
            ]
        texts = (
            observation.text.splitlines()
            if document.source_format is SourceFormat.PDF_TEXT
            else (observation.text,)
        )
        pages.setdefault(page_index, []).extend(
            {
                "text": text,
                "sourceKind": source_kind,
                "confidence": None,
                "evidence": evidence,
            }
            for text in texts
            if text.strip()
        )
    return {
        "plainText": "\n".join(
            str(block["text"]) for page_index in sorted(pages) for block in pages[page_index]
        ),
        "pages": [
            {"pageIndex": page_index, "blocks": pages[page_index]} for page_index in sorted(pages)
        ],
    }


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).casefold()
    decomposed = unicodedata.normalize("NFD", text)
    plain = "".join(
        "d" if character == "đ" else character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def _blocks(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    pages = canonical.get("pages")
    if not isinstance(pages, list):
        return []
    output: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, Mapping):
            continue
        blocks = page.get("blocks")
        if not isinstance(blocks, list):
            continue
        output.extend(
            dict(block)
            for block in blocks
            if isinstance(block, Mapping) and str(block.get("text") or "").strip()
        )
    return output


def _field(
    value: object,
    *,
    method: str,
    block: Mapping[str, Any] | None,
    review: bool,
    normalized: object | None = None,
) -> dict[str, Any]:
    cleaned = " ".join(str(value).split()).strip() if value not in (None, "") else None
    normalized_value = cleaned if normalized is None else normalized
    output_value = normalized_value if normalized is not None else cleaned
    evidence = block.get("evidence") if block else None
    confidence = block.get("confidence") if block else None
    return {
        "value": output_value,
        "normalizedValue": normalized_value,
        "status": (
            "needs_review"
            if review and cleaned is not None
            else "accepted"
            if cleaned is not None
            else "not_found"
        ),
        "confidence": (
            round(float(confidence), 6)
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
            else None
        ),
        "evidence": evidence,
        "sourceSpan": evidence,
        "method": method,
        "extractor": STRUCTURED_HR_PARSER_ID,
        "reviewReason": "ocr_requires_human_review" if review and cleaned is not None else None,
    }


def _missing(method: str, *, review: bool) -> dict[str, Any]:
    return _field(None, method=method, block=None, review=review)


def _without_list_prefix(text: str) -> str:
    return _LIST_PREFIX.sub("", text, count=1).strip()


def _starts_with_label(text: str, labels: tuple[str, ...]) -> bool:
    key = _fold(_without_list_prefix(text))
    return any(key == label or key.startswith(f"{label} ") for label in map(_fold, labels))


def _label_value(
    canonical: Mapping[str, Any],
    labels: tuple[str, ...],
    *,
    stops: tuple[str, ...] = (),
    method: str,
    review: bool,
    normalizer: Any = None,
) -> dict[str, Any]:
    blocks = _blocks(canonical)
    folded_labels = tuple(_fold(label) for label in labels)
    folded_stops = tuple(_fold(label) for label in (*labels, *stops))
    for index, block in enumerate(blocks):
        text = _without_list_prefix(str(block.get("text") or ""))
        key = _fold(text)
        matched = next(
            (label for label in folded_labels if key == label or key.startswith(f"{label} ")),
            None,
        )
        if matched is None:
            continue
        value = _value_after_label(text, len(matched.split()))
        evidence: Mapping[str, Any] = block
        if not value and index + 1 < len(blocks):
            candidate = str(blocks[index + 1].get("text") or "").strip()
            if candidate and not _starts_with_label(candidate, (*labels, *stops)):
                value = candidate
                evidence = blocks[index + 1]
        value = _cut_following_label(value, folded_stops)
        if not value:
            continue
        normalized = normalizer(value) if normalizer else value
        if normalizer is not None and normalized is None:
            continue
        return _field(
            value,
            method=method,
            block=evidence,
            review=review,
            normalized=normalized,
        )
    return _missing(method, review=review)


def _value_after_label(text: str, label_word_count: int) -> str:
    if ":" in text:
        return text.split(":", 1)[1].strip(" :|-–—")
    parts = re.split(r"\s+", text.strip())
    return " ".join(parts[label_word_count:]).strip(" :|-–—")


def _cut_following_label(value: str, folded_stops: tuple[str, ...]) -> str:
    if not value:
        return value
    segments = re.split(r"\s+[|;/]\s+|\s{2,}", value)
    kept: list[str] = []
    for segment in segments:
        key = _fold(_without_list_prefix(segment))
        if kept and any(key == stop or key.startswith(f"{stop} ") for stop in folded_stops):
            break
        kept.append(segment)
    return " ".join(kept).strip(" :|-–—")


def _regex_value(
    canonical: Mapping[str, Any],
    patterns: tuple[str, ...],
    *,
    method: str,
    review: bool,
    normalizer: Any = None,
    join_next: bool = False,
) -> dict[str, Any]:
    blocks = _blocks(canonical)
    for index, block in enumerate(blocks):
        text = str(block.get("text") or "")
        candidates: list[tuple[str, Mapping[str, Any], int]] = [(text, block, len(text))]
        if join_next and index + 1 < len(blocks):
            next_block = blocks[index + 1]
            candidates.append(
                (f"{text} {str(next_block.get('text') or '')}", next_block, len(text))
            )
        for candidate, candidate_evidence, boundary in candidates:
            for pattern in patterns:
                match = re.search(pattern, candidate, re.IGNORECASE)
                if match is None:
                    continue
                value = match.group(1).strip(" .,:;-–—")
                normalized = normalizer(value) if normalizer else value
                if normalizer is not None and normalized is None:
                    continue
                evidence = candidate_evidence if match.start(1) > boundary else block
                return _field(
                    value,
                    method=method,
                    block=evidence,
                    review=review,
                    normalized=normalized,
                )
    return _missing(method, review=review)


def _narrative_value(
    canonical: Mapping[str, Any],
    pattern: str,
    *,
    method: str,
    review: bool,
    normalizer: Any = None,
) -> dict[str, Any]:
    blocks = _blocks(canonical)
    compiled = re.compile(pattern, re.IGNORECASE)
    for index, block in enumerate(blocks):
        text = str(block.get("text") or "").strip()
        match = compiled.search(text)
        if match is None:
            continue
        raw_value = match.group(1).strip()
        ended = raw_value.endswith(".")
        value = raw_value.strip(" .;:-")
        cursor = index + 1
        can_continue = match.end() >= len(text.rstrip())
        while (
            can_continue
            and value
            and not ended
            and cursor < len(blocks)
            and len(value) < 320
        ):
            candidate = str(blocks[cursor].get("text") or "").strip()
            if not candidate or re.match(
                r"^(?:\d+\.\s*|Điều\s+\d+|BÊN\s+[AB])",
                candidate,
                re.IGNORECASE,
            ):
                break
            ended = candidate.endswith(".")
            value = f"{value} {candidate}".strip(" .;:-")
            cursor += 1
        normalized = normalizer(value) if normalizer else value
        if normalizer is not None and normalized is None:
            continue
        return _field(
            value,
            method=method,
            block=block,
            review=review,
            normalized=normalized,
        )
    return _missing(method, review=review)


def _date(value: str | None) -> str | None:
    if not value:
        return None
    words = re.search(
        r"(?:ngày\s+)?(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
        value,
        re.IGNORECASE,
    )
    if words:
        return f"{int(words.group(1)):02d}/{int(words.group(2)):02d}/{words.group(3)}"
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", value)
    return (
        f"{int(match.group(1)):02d}/{int(match.group(2)):02d}/{match.group(3)}"
        if match
        else value.strip()
    )


def _identifier_digits(value: str | None) -> str | None:
    compact = re.sub(r"\s+", "", value or "")
    return compact if compact.isdigit() and 9 <= len(compact) <= 12 else None


def _role_title(value: str | None) -> str | None:
    if not value:
        return None
    return re.split(r"\s*;\s*", value, maxsplit=1)[0].strip(" .;:-") or None


def _monthly_amount(value: str | None) -> str | None:
    amount = "".join((value or "").split()).strip(".,")
    return f"{amount} đồng/tháng" if amount and re.fullmatch(r"\d[\d.]*", amount) else None


def _repair_monthly_units(value: str | None) -> str | None:
    if not value:
        return None
    repaired = re.sub(
        r"đồng\s*(?:\[\s*)?[il]?\s*tháng",
        "đồng/tháng",
        value,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(r"\s+[’']\s*", " ", repaired).strip()
    return repaired if repaired.endswith(".") else f"{repaired}."


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.replace("–", "-").split()).upper()
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%d/%b/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(cleaned, pattern).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _is_section_heading(value: object) -> bool:
    key = _fold(value)
    return key in _SECTION_HEADINGS or any(
        key.startswith(f"{heading} ") for heading in _SECTION_HEADINGS
    )


def _section_lines(
    canonical: Mapping[str, Any],
    headings: tuple[str, ...],
) -> tuple[list[str], Mapping[str, Any] | None]:
    folded = tuple(_fold(heading) for heading in headings)
    blocks = _blocks(canonical)
    for index, heading in enumerate(blocks):
        key = _fold(heading.get("text"))
        if not any(key == item or key.startswith(f"{item} ") for item in folded):
            continue
        values: list[str] = []
        evidence: Mapping[str, Any] | None = None
        for candidate in blocks[index + 1 :]:
            if _is_section_heading(candidate.get("text")):
                break
            text = str(candidate.get("text") or "").strip()
            if text:
                evidence = evidence or candidate
                values.append(text)
        if values:
            return values, evidence
    return [], None


def _cv_name_candidate(value: str) -> bool:
    words = value.split()
    letters = [character for character in value if character.isalpha()]
    return (
        2 <= len(words) <= 6
        and len(letters) >= 6
        and "@" not in value
        and not any(character.isdigit() for character in value)
        and _fold(value) not in {"curriculum vitae", "ky nang", "hoc van", "kinh nghiem lam viec"}
    )


def _split_cv_header_text(text: str) -> tuple[str, str] | None:
    for index in range(len(text) - 2, 0, -1):
        prefix = text[:index].strip()
        suffix = text[index:].strip()
        if (
            not text[index - 1].isspace()
            and not text[index].isspace()
            and suffix
            and suffix[0].isupper()
            and len(suffix) > 1
            and suffix[1].islower()
            and _cv_name_candidate(prefix)
        ):
            return prefix, suffix
    return None


def _cv_header(
    canonical: Mapping[str, Any],
    *,
    review: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    blocks = _blocks(canonical)
    for index, block in enumerate(blocks[:6]):
        text = str(block.get("text") or "").strip(" •")
        if not text or "@" in text or "|" in text or _fold(text) == "curriculum vitae":
            continue
        parts = re.split(r"(?<=[a-zà-ỹ])(?=[A-ZĐ])", text, maxsplit=1)
        glued = _split_cv_header_text(text)
        if glued is not None:
            parts = list(glued)
        if len(parts) == 2 and _cv_name_candidate(parts[0].strip()):
            return (
                _field(parts[0], method="cv_header_name", block=block, review=review),
                _field(parts[1], method="cv_header_headline", block=block, review=review),
            )
        if _cv_name_candidate(text):
            for candidate in blocks[index + 1 : index + 4]:
                candidate_text = str(candidate.get("text") or "").strip(" •")
                if candidate_text and "|" not in candidate_text and "@" not in candidate_text:
                    return (
                        _field(text, method="cv_header_name", block=block, review=review),
                        _field(
                            candidate_text,
                            method="cv_header_headline",
                            block=candidate,
                            review=review,
                        ),
                    )
            return (
                _field(text, method="cv_header_name", block=block, review=review),
                _missing("cv_header_headline", review=review),
            )
    return _missing("cv_header_name", review=review), _missing("cv_header_headline", review=review)


def _cv_contact_address(canonical: Mapping[str, Any], *, review: bool) -> dict[str, Any]:
    for block in _blocks(canonical)[:6]:
        text = str(block.get("text") or "")
        if "|" not in text:
            continue
        for part in reversed([item.strip() for item in text.split("|")]):
            if (
                part
                and "@" not in part
                and "linkedin" not in part.casefold()
                and not re.search(r"\d", part)
            ):
                return _field(part, method="cv_contact_layout", block=block, review=review)
    return _missing("cv_contact_layout", review=review)


def _cv_email(canonical: Mapping[str, Any], *, review: bool) -> dict[str, Any]:
    for block in _blocks(canonical)[:8]:
        text = str(block.get("text") or "")
        match = re.search(
            r"([A-Z0-9._%+-]+(?:\s+[A-Z0-9._%+-]+)?)\s*@\s*"
            r"([A-Z0-9.-]+)\s*(?:\.|\s+)?(com|vn|net|org)\b",
            text,
            re.IGNORECASE,
        )
        if match is None:
            continue
        local = re.sub(r"\s+", ".", match.group(1).strip(" ."))
        domain = re.sub(r"\s+", "", match.group(2)).strip(".")
        return _field(
            f"{local}@{domain}.{match.group(3).lower()}",
            method="cv_email_ocr_layout",
            block=block,
            review=review,
        )
    return _missing("cv_email_ocr_layout", review=review)


def _cv_section(
    canonical: Mapping[str, Any],
    headings: tuple[str, ...],
    *,
    method: str,
    review: bool,
) -> dict[str, Any]:
    lines, evidence = _section_lines(canonical, headings)
    return _field("\n".join(lines) if lines else None, method=method, block=evidence, review=review)


def _same_cv_column(
    box: tuple[float, float, float, float],
    heading_box: tuple[float, float, float, float],
    *,
    heading_full_width: bool,
    page_width: float,
) -> bool:
    if heading_full_width:
        return True
    box_x0, _, box_x1, _ = box
    heading_x0, _, heading_x1, _ = heading_box
    overlap = min(heading_x1, box_x1) - max(heading_x0, box_x0)
    return overlap > 0 or abs(((box_x0 + box_x1) / 2) - ((heading_x0 + heading_x1) / 2)) <= max(
        80.0, page_width * 0.18
    )


def _cv_section_bounds(
    heading_box: tuple[float, float, float, float],
    heading_full_width: bool,
    nearby_headings: list[tuple[float, float, float, float]],
    section_boxes: list[tuple[float, float, float, float]],
    page_width: float,
) -> tuple[float, float]:
    if heading_full_width:
        return 0.0, page_width
    heading_x0, _, heading_x1, _ = heading_box
    heading_center = (heading_x0 + heading_x1) / 2
    left = 0.0
    right = max((box[2] for box in section_boxes), default=page_width)
    for other_box in nearby_headings:
        other_center = (other_box[0] + other_box[2]) / 2
        boundary = (heading_center + other_center) / 2
        if other_center < heading_center:
            left = max(left, boundary)
        elif other_center > heading_center:
            right = min(right, boundary)
    return left, right


def _cv_ocr_section(
    canonical: Mapping[str, Any],
    headings: tuple[str, ...],
    *,
    review: bool,
    method: str,
) -> dict[str, Any]:
    normalized_headings = tuple(_fold(item) for item in headings)
    pages = canonical.get("pages")
    if not isinstance(pages, list):
        return _missing(method, review=review)
    for page in pages:
        if not isinstance(page, Mapping):
            continue
        raw_blocks = page.get("blocks")
        if not isinstance(raw_blocks, list):
            continue
        blocks = [
            dict(block)
            for block in raw_blocks
            if isinstance(block, Mapping) and str(block.get("text") or "").strip()
        ]
        positioned = [(block, _ocr_bbox(block)) for block in blocks]
        boxes = [box for _, box in positioned if box is not None]
        if not boxes:
            continue
        page_width = max(box[2] for box in boxes)
        for heading, heading_box in positioned:
            if heading_box is None:
                continue
            heading_key = _fold(heading.get("text"))
            if not any(
                heading_key == item or heading_key.startswith(f"{item} ")
                for item in normalized_headings
            ):
                continue
            heading_x0, heading_y0, heading_x1, heading_y1 = heading_box
            heading_full_width = heading_x1 - heading_x0 >= page_width * 0.6
            heading_height = max(1.0, heading_y1 - heading_y0)
            nearby_headings = [
                other_box
                for other, other_box in positioned
                if other_box is not None
                and other is not heading
                and _is_section_heading(other.get("text"))
                and abs(((other_box[1] + other_box[3]) / 2) - ((heading_y0 + heading_y1) / 2))
                <= max(36.0, heading_height * 1.5)
            ]
            next_heading_y = min(
                (
                    other_box[1]
                    for other, other_box in positioned
                    if other_box is not None
                    and other_box[1] > heading_y0
                    and _same_cv_column(
                        other_box,
                        heading_box,
                        heading_full_width=heading_full_width,
                        page_width=page_width,
                    )
                    and _is_section_heading(other.get("text"))
                ),
                default=None,
            )
            section_boxes = [
                box
                for _, box in positioned
                if box is not None
                and box[1] >= heading_y1 - 4
                and (next_heading_y is None or box[1] < next_heading_y)
            ]
            if (
                not heading_full_width
                and not nearby_headings
                and heading_x0 <= page_width * 0.15
                and max((box[2] for box in section_boxes), default=0.0) >= page_width * 0.75
            ):
                heading_full_width = True
            left_bound, right_bound = _cv_section_bounds(
                heading_box,
                heading_full_width,
                nearby_headings,
                section_boxes,
                page_width,
            )
            selected = [
                (box, block)
                for block, box in positioned
                if box is not None
                and block is not heading
                and box[1] >= heading_y1 - 4
                and (next_heading_y is None or box[1] < next_heading_y)
                and box[2] > left_bound
                and box[0] < right_bound
                and not _is_section_heading(block.get("text"))
            ]
            if not selected:
                continue
            median_height = sorted(box[3] - box[1] for box, _ in selected)[len(selected) // 2]
            line_tolerance = max(18.0, median_height * 0.65)
            lines: list[list[tuple[tuple[float, float, float, float], dict[str, Any]]]] = []
            for item in sorted(
                selected,
                key=lambda value: (
                    (value[0][1] + value[0][3]) / 2,
                    value[0][0],
                ),
            ):
                center_y = (item[0][1] + item[0][3]) / 2
                if lines:
                    last_box = lines[-1][-1][0]
                    last_center = (last_box[1] + last_box[3]) / 2
                    if center_y - last_center <= line_tolerance:
                        lines[-1].append(item)
                        continue
                lines.append([item])
            ordered = [
                item for line in lines for item in sorted(line, key=lambda value: value[0][0])
            ]
            return _field(
                "\n".join(str(block.get("text") or "").strip() for _, block in ordered),
                method=method,
                block=ordered[0][1],
                review=review,
            )
    return _missing(method, review=review)


def _cv_skills(canonical: Mapping[str, Any], *, review: bool) -> dict[str, Any]:
    lines, evidence = _section_lines(canonical, ("ky nang",))
    cleaned: list[str] = []
    for line in lines:
        value = re.sub(r"^[\s•·▪–—-]+", "", line).strip()
        if ":" in value:
            label, remainder = value.split(":", 1)
            if 1 <= len(label.split()) <= 5:
                value = remainder.strip(" ;")
        if re.search(r"[À-žẠ-ỹ]", value):
            value = re.sub(r"(?<!\w)\s*&\s*(?!\w)", "và", value)
        if value:
            cleaned.append(value)
    return _field(
        "\n".join(cleaned) if cleaned else None,
        method="cv_skills_native_section",
        block=evidence,
        review=review,
    )


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    left, right = left.casefold(), right.casefold()
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    left_index = right_index = differences = 0
    while left_index < len(left) and right_index < len(right):
        if left[left_index] == right[right_index]:
            left_index += 1
            right_index += 1
            continue
        differences += 1
        if differences > 1:
            return False
        if len(left) == len(right):
            left_index += 1
        right_index += 1
    return differences + (len(right) - right_index) <= 1


def _cv_ocr_skill_repair(
    canonical: Mapping[str, Any],
    field: dict[str, Any],
    *,
    review: bool,
) -> dict[str, Any]:
    value = field.get("value")
    if not isinstance(value, str) or not value:
        return field
    experience = _cv_ocr_section(
        canonical,
        ("kinh nghiem lam viec", "kinh nghiem"),
        method="cv_experience_ocr_anchor",
        review=review,
    )
    anchors = set(re.findall(r"[^\W_]+", str(experience.get("value") or ""), flags=re.UNICODE))
    folded_anchors = {candidate.casefold() for candidate in anchors}
    replacements: dict[str, str] = {}
    for token in re.findall(r"[^\W_]+", value, flags=re.UNICODE):
        if token.casefold() in folded_anchors:
            continue
        candidates = [
            candidate
            for candidate in anchors
            if len(candidate) >= 6 and _edit_distance_at_most_one(token, candidate)
        ]
        if len(candidates) == 1:
            replacements[token] = candidates[0]
    if not replacements:
        return field
    repaired = value
    for source, target in replacements.items():
        repaired = re.sub(
            rf"(?<!\w){re.escape(source)}(?!\w)",
            target,
            repaired,
            flags=re.IGNORECASE,
        )
    return _field(
        repaired,
        method="cv_skills_ocr_document_anchor",
        block=field,
        review=review,
    )


def _cv_desired_role(canonical: Mapping[str, Any], *, review: bool) -> dict[str, Any]:
    in_objective = False
    objective_blocks: list[Mapping[str, Any]] = []
    for block in _blocks(canonical):
        text = str(block.get("text") or "").strip()
        key = _fold(text)
        if "muc tieu nghe nghiep" in key or key == "objective":
            in_objective = True
            continue
        if in_objective and _is_section_heading(text):
            break
        if not in_objective or not text:
            continue
        objective_blocks.append(block)

    if objective_blocks:
        narrative = " ".join(
            str(block.get("text") or "").strip() for block in objective_blocks
        ).strip()
        if len(objective_blocks) > 1 and re.search(
            r"\b(?:kinh nghiệm|định hướng|trở thành|phát triển)\b",
            narrative,
            re.IGNORECASE,
        ):
            return _field(
                narrative,
                method="cv_objective_narrative_layout",
                block=objective_blocks[0],
                review=review,
            )

    for objective_block in objective_blocks:
        text = str(objective_block.get("text") or "").strip()
        for pattern in (
            r"\b(?:vị trí|trở thành|theo hướng)\s+"
            r"(.+?)(?=\s+(?:cho|trong|với|có)\b|[.;]|$)",
            r"^\s*[•-]?\s*([^,.;]+?)(?=\s+với\b)",
        ):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .;,-")
                return _field(
                    value,
                    method="cv_objective_role_layout",
                    block=objective_block,
                    review=review,
                )
    return _missing("cv_objective_role_layout", review=review)


def _cv_years(canonical: Mapping[str, Any], *, review: bool) -> dict[str, Any]:
    result = _regex_value(
        canonical,
        (
            r"((?:hơn|trên|ít nhất)\s+\d+\s+năm)",
            r"(\d+\s+năm\s+kinh\s+nghiệm)",
            r"(\d+\s+năm)",
        ),
        method="cv_years_pattern",
        review=review,
    )
    if result["value"] is not None or not review:
        return result
    for block in _blocks(canonical):
        match = re.search(r"(\d+)\s+nam", _fold(block.get("text")))
        if match:
            return _field(
                f"{match.group(1)} năm",
                method="cv_years_ocr_layout",
                block=block,
                review=review,
            )
    return result


def _cv_fields(canonical: Mapping[str, Any], *, ocr: bool) -> dict[str, dict[str, Any]]:
    name, headline = _cv_header(canonical, review=ocr)
    labeled_name = _label_value(
        canonical,
        ("Họ và tên", "Họ tên", "Full name"),
        method="cv_name_label",
        review=ocr,
    )
    if labeled_name["value"] is not None:
        name = labeled_name
    labeled_headline = _label_value(
        canonical,
        ("Vị trí ứng tuyển", "Chức danh", "Vị trí", "Headline"),
        stops=("Địa chỉ", "Học vấn", "Kinh nghiệm", "Kỹ năng"),
        method="cv_headline_label",
        review=ocr,
    )
    if labeled_headline["value"] is not None:
        headline = labeled_headline
    email = _regex_value(
        canonical,
        (r"\b([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\b",),
        method="email_pattern",
        review=ocr,
    )
    if ocr:
        layout_email = _cv_email(canonical, review=ocr)
        if layout_email["value"] is not None:
            email = layout_email
    phone = _regex_value(
        canonical,
        (r"((?:\+?84|0)(?:[\s.-]?\d){8,10})",),
        method="phone_pattern",
        review=ocr,
    )
    address = _label_value(
        canonical,
        ("Địa chỉ", "Address"),
        stops=("Mục tiêu nghề nghiệp", "Kinh nghiệm", "Kỹ năng", "Học vấn"),
        method="cv_address_label",
        review=ocr,
    )
    if address["value"] is None:
        address = _cv_contact_address(canonical, review=ocr)
    experience = _cv_section(
        canonical,
        ("kinh nghiem lam viec", "kinh nghiem"),
        method="cv_experience_section",
        review=ocr,
    )
    education = _cv_section(
        canonical,
        ("hoc van",),
        method="cv_education_section",
        review=ocr,
    )
    skills = _cv_skills(canonical, review=ocr)
    if ocr:
        geometry_experience = _cv_ocr_section(
            canonical,
            ("Kinh nghiệm làm việc", "Kinh nghiệm"),
            method="cv_experience_ocr_geometry",
            review=ocr,
        )
        if geometry_experience["value"] is not None:
            experience = geometry_experience
        geometry_education = _cv_ocr_section(
            canonical,
            ("Học vấn",),
            method="cv_education_ocr_geometry",
            review=ocr,
        )
        if geometry_education["value"] is not None:
            education = geometry_education
        geometry_skills = _cv_ocr_section(
            canonical,
            ("Kỹ năng",),
            method="cv_skills_ocr_geometry",
            review=ocr,
        )
        if geometry_skills["value"] is not None:
            skills = geometry_skills
        skills = _cv_ocr_skill_repair(canonical, skills, review=ocr)
    return {
        "full_name": name,
        "headline": headline,
        "email": email,
        "phone_number": phone,
        "address": address,
        "desired_role": _cv_desired_role(canonical, review=ocr),
        "years_experience": _cv_years(canonical, review=ocr),
        "experience": experience,
        "skills": skills,
        "education": education,
    }


def _party_lines(
    canonical: Mapping[str, Any],
    start_markers: tuple[str, ...],
    end_markers: tuple[str, ...],
) -> dict[str, Any]:
    blocks = _blocks(canonical)
    start = next(
        (
            index
            for index, block in enumerate(blocks)
            if _starts_with_label(str(block.get("text") or ""), start_markers)
        ),
        None,
    )
    if start is None:
        return dict(canonical)
    end = next(
        (
            index
            for index, block in enumerate(blocks[start + 1 :], start + 1)
            if _starts_with_label(str(block.get("text") or ""), end_markers)
        ),
        len(blocks),
    )
    selected = blocks[start:end]
    return {
        "plainText": "\n".join(str(block.get("text") or "") for block in selected),
        "pages": [{"blocks": selected}],
    }


def _person_value(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"^(?:Ông|Bà|Ông/bà)\s+", "", value.strip(), flags=re.IGNORECASE)
    value = re.split(
        r"\s+(?:Chức vụ|Chức danh|Giới tính|Ngày sinh|CMND/CCCD số|CCCD số)\s*(?::|[-–—])?\s*",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    repaired = re.sub(r"(?i)\bNguyển\b", "Nguyễn", value)
    repaired = re.sub(r"(?i)\bQuõc\b", "Quốc", repaired)
    return repaired.strip(" .;:-")


def _employer_value(value: str | None) -> str | None:
    if not value:
        return None
    repaired = re.sub(r"(?i)\bCông\s+Ly\b", "Công ty", value)
    repaired = re.sub(r"(?i)\bxuẩt\b", "xuất", repaired)
    return repaired.strip(" .;:-")


def _weekly_hours(canonical: Mapping[str, Any], *, review: bool) -> dict[str, Any]:
    for block in _blocks(canonical):
        text = str(block.get("text") or "")
        folded = _fold(text)
        explicit = re.search(r"\b(\d{1,3})\s+(?:gio\s+tuan|gioltuan)\b", folded)
        if explicit is not None:
            return _field(
                f"{int(explicit.group(1))} giờ/tuần",
                method="weekly_hours_explicit",
                block=block,
                review=review,
            )
        if "thoi gio lam viec" not in folded:
            continue
        times = [
            (int(hour), int(minute or 0))
            for hour, minute in re.findall(r"(\d{1,2})h(\d{2})?", text, re.IGNORECASE)
        ]
        if len(times) < 4:
            continue
        daily = float(
            sum(
                (
                    float(times[index + 1][0] + times[index + 1][1] / 60)
                    - float(times[index][0] + times[index][1] / 60)
                )
                for index in (0, 2)
                if index + 1 < len(times)
            )
        )
        weekly = daily * 5

        def fmt(value: float) -> str:
            return str(int(value)) if value.is_integer() else str(value).replace(".", ",")

        result = f"{fmt(weekly)} giờ/tuần"
        if not daily.is_integer():
            result += f" — {fmt(daily)} giờ/ngày × 5 ngày"
        return _field(result, method="weekly_hours_schedule", block=block, review=review)
    return _missing("weekly_hours_schedule", review=review)


def _contract_fields(canonical: Mapping[str, Any], *, ocr: bool) -> dict[str, dict[str, Any]]:
    labels = (
        "Số hợp đồng",
        "Số",
        "Ngày ký",
        "Hiệu lực từ",
            "Bắt đầu từ",
            "Effective Date",
        "Kết thúc thử việc",
            "Hết hạn thử việc",
            "Probation End",
        "Đại diện cho",
            "Công ty",
            "Employer",
        "Đại diện",
        "Người lao động",
        "Ông/bà",
            "Họ và tên",
            "Employee Name",
        "CCCD số",
            "CCCD sỗ",
            "CMND số",
        "Employee ID",
        "Công việc/Chức danh",
        "Chức vụ/Vị trí",
        "Chức danh",
            "Vị trí công việc",
            "Job Title",
        "Địa điểm làm việc",
        "Mức lương thử việc",
            "Lương thử việc",
            "Salary",
        "Phụ cấp",
            "Phụ cấp và hỗ trợ",
        "Thanh toán",
        "Trả lương",
            "Hình thức trả lương",
        "Số giờ/tuần",
        "Giờ/tuần",
    )
    date_pattern = r"((?:\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}))"
    sign_date = _regex_value(
        canonical,
        (rf"ngày\s+{date_pattern}",),
        method="sign_date_narrative",
        review=ocr,
        normalizer=_date,
    )
    if sign_date["value"] is None:
        sign_date = _label_value(
            canonical,
            ("Ngày ký",),
            stops=labels,
            method="sign_date_label",
            review=ocr,
            normalizer=_date,
        )
    effective = _regex_value(
        canonical,
        (rf"(?:kể\s+)?từ ngày\s+{date_pattern}",),
        method="effective_date_narrative",
        review=ocr,
        normalizer=_date,
        join_next=True,
    )
    if effective["value"] is None:
        effective = _label_value(
            canonical,
            ("Hiệu lực từ", "Bắt đầu từ", "Effective Date"),
            stops=labels,
            method="effective_date_label",
            review=ocr,
            normalizer=_date,
        )
    probation_end = _regex_value(
        canonical,
        (rf"đến(?:\s+hết)?\s+ngày\s+{date_pattern}",),
        method="probation_end_narrative",
        review=ocr,
        normalizer=_date,
        join_next=True,
    )
    if probation_end["value"] is None:
        probation_end = _label_value(
            canonical,
            ("Kết thúc thử việc", "Hết hạn thử việc", "Probation End"),
            stops=labels,
            method="probation_end_label",
            review=ocr,
            normalizer=_date,
        )
    employer = _regex_value(
        canonical, (r"Tên\s+công\s+ty\s*:\s*(.+)",), method="employer_name_label", review=ocr
    )
    if employer["value"] is None:
        employer = _label_value(
            canonical,
            ("Đại diện cho", "Employer"),
            stops=labels,
            method="employer_label",
            review=ocr,
            normalizer=_employer_value,
        )
    if employer["value"] is None:
        employer = _label_value(
            canonical,
            ("Công ty",),
            stops=labels,
            method="employer_label",
            review=ocr,
            normalizer=_employer_value,
        )
    party_a = _party_lines(canonical, ("Bên A",), ("Bên B",))
    representative = _regex_value(
        party_a,
        (
            r"Đại\s+diện\s+(?:bởi|cho)\s*:\s*(?:Ông|Bà)\s+(.+?)(?=\s+Chức\s+(?:vụ|danh)\s*(?::|[-–—])|$)",
        ),
        method="representative_name_label",
        review=ocr,
        normalizer=_person_value,
    )
    if representative["value"] is None:
        representative = _label_value(
            party_a,
            ("Đại diện bởi", "Đại diện cho", "Đại diện"),
            stops=labels,
            method="representative_label",
            review=ocr,
            normalizer=_person_value,
        )
    party_b = _party_lines(canonical, ("Bên B",), ("Hai bên thỏa thuận", "Điều 1"))
    employee = _regex_value(
        party_b,
        (r"Họ\s+và\s+tên\s*:\s*(.+?)(?=\s+Giới\s+tính\s*:|\s+Ngày\s+sinh\s*:|$)",),
        method="employee_name_label",
        review=ocr,
        normalizer=_person_value,
    )
    if employee["value"] is None:
        employee = _label_value(
            party_b,
            ("Người lao động", "Ông/bà", "ÔngJBà", "Họ và tên", "Employee Name"),
            stops=labels,
            method="employee_label",
            review=ocr,
            normalizer=_person_value,
        )
    employee_id = _label_value(
        canonical,
        ("CCCD số", "CCCD sỗ", "CMND số", "Employee ID"),
        stops=labels,
        method="employee_id_label",
        review=ocr,
        normalizer=_identifier_digits,
    )
    if employee_id["value"] is None:
        employee_id = _regex_value(
            canonical,
            (
                r"(?:CCCD\s+s(?:ố|ỗ|õ|o)|CMND\s+số)\s*[:\-]?\s*"
                r"((?:[0-9][ \t]*){9,12})(?![ \t]*[0-9])",
                r"Employee\s+ID\s*[:\-]?\s*((?:[0-9][ \t]*){9,12})(?![ \t]*[0-9])",
            ),
            method="employee_id_pattern",
            review=ocr,
            normalizer=_identifier_digits,
        )
    professional_title = _narrative_value(
        canonical,
        r"Chức\s+danh\s+công\s+việc\s*:\s*(.+?)(?:\.\s*$|$)",
        method="professional_title_narrative",
        review=ocr,
    )
    if professional_title["value"] is None:
        professional_title = _label_value(
            canonical,
            (
                "Công việc/Chức danh",
                "Chức danh chuyên môn",
                "Chức danh",
                "Vị trí công việc",
                "Job Title",
            ),
            stops=labels,
            method="professional_title_label",
            review=ocr,
        )
    has_employee_party = any(
        _starts_with_label(str(block.get("text") or ""), ("Bên B",))
        for block in _blocks(canonical)
    )
    employee_role_section = _party_lines(canonical, ("Bên B",), ())
    role_title = _label_value(
        employee_role_section,
        ("Chức vụ/Vị trí", "Chức vụ", "Vị trí", "Job Title"),
        stops=labels,
        method="role_title_label",
        review=ocr,
        normalizer=_role_title,
    )
    if role_title["value"] is None and not has_employee_party:
        role_title = _label_value(
            canonical,
            ("Chức vụ/Vị trí", "Chức vụ", "Vị trí", "Job Title"),
            stops=labels,
            method="role_title_label",
            review=ocr,
            normalizer=_role_title,
        )
    job_title = role_title
    if job_title["value"] is None and professional_title["value"] is not None:
        job_title = _field(
            professional_title["value"],
            method="job_title_professional_title_fallback",
            block=professional_title,
            review=ocr,
        )
    workplace = _narrative_value(
        canonical,
        r"(?:Nơi|Địa\s+điểm)\s+làm\s+việc\s*:\s*(.+?)(?:\.\s*$|$)",
        method="workplace_narrative",
        review=ocr,
    )
    if workplace["value"] is None:
        workplace = _label_value(
            canonical, ("Địa điểm làm việc",), stops=labels, method="workplace_label", review=ocr
        )
    salary = _regex_value(
        canonical,
        (
            r"Mức\s+lương\s+thử\s+việc\s*:\s*"
            r"((?:[0-9][0-9.\s]*[0-9]))\s*đồng\s*/?\s*tháng",
        ),
        method="salary_monthly_amount",
        review=ocr,
        normalizer=_monthly_amount,
    )
    if salary["value"] is None:
        salary = _label_value(
            canonical,
            ("Mức lương thử việc", "Lương thử việc", "Salary"),
            stops=labels,
            method="salary_label",
            review=ocr,
        )
    allowances = _narrative_value(
        canonical,
        r"Phụ\s+c[ấãẩậa]p(?:\s+và\s+hỗ\s+\S+)?\s*:\s*(.+?)(?:\.\s*$|$)",
        method="allowances_narrative",
        review=ocr,
        normalizer=_repair_monthly_units,
    )
    if allowances["value"] is None:
        allowances = _label_value(
            canonical,
            ("Phụ cấp và hỗ trợ", "Phụ cấp"),
            stops=labels,
            method="allowances_label",
            review=ocr,
        )
    payment = _label_value(
        canonical,
        ("Hình thức trả lương", "Trả lương", "Thanh toán"),
        stops=labels,
        method="payment_label",
        review=ocr,
    )
    return {
        "contract_number": _label_value(
            canonical,
            ("Số hợp đồng", "Số", "Contract number"),
            stops=labels,
            method="contract_number_label",
            review=ocr,
        ),
        "contract_sign_date": sign_date,
        "effective_date": effective,
        "probation_end_date": probation_end,
        "employer_name": employer,
        "employer_representative": representative,
        "employee_name": employee,
        "employee_id_number": employee_id,
        "professional_title": professional_title,
        "role_title": role_title,
        "job_title": job_title,
        "workplace": workplace,
        "weekly_hours": _weekly_hours(canonical, review=ocr),
        "probation_salary_monthly": salary,
        "allowances_summary": allowances,
        "salary_payment_schedule": payment,
    }


def _box_bounds(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) < 2:
        return None
    try:
        xs = [float(point[0]) for point in value]
        ys = [float(point[1]) for point in value]
    except (TypeError, ValueError, IndexError):
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _ocr_bbox(block: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    evidence = block.get("evidence")
    return _box_bounds(evidence.get("bbox")) if isinstance(evidence, Mapping) else None


def _ocr_value_after_label(
    blocks: list[dict[str, Any]],
    labels: tuple[str, ...],
    *,
    predicate: Any,
    method: str,
    review: bool,
) -> dict[str, Any]:
    keys = tuple(_fold(label) for label in labels)
    for index, block in enumerate(blocks):
        text = str(block.get("text") or "").strip()
        folded = _fold(text)
        matched = next(
            (
                label
                for label in keys
                if folded == label or folded.startswith(f"{label} ")
            ),
            None,
        )
        if matched is None:
            continue
        matched_label = next(label for label in labels if _fold(label) == matched)
        inline = _value_after_label(text, len(matched_label.split()))
        if inline and predicate(inline):
            return _field(inline, method=method, block=block, review=review)
        label_box = _ocr_bbox(block)
        candidates: list[tuple[float, dict[str, Any]]] = []
        for candidate_index, candidate in enumerate(blocks[index + 1 : index + 5], index + 1):
            text = str(candidate.get("text") or "").strip()
            candidate_key = _fold(text)
            if any(
                marker in candidate_key
                for marker in (
                    "first name",
                    "candidate",
                    "date",
                    "sex",
                    "scheme",
                    "country",
                    "nationality",
                    "test results",
                    "overall",
                )
            ):
                break
            if not text or not predicate(text):
                continue
            distance = float(candidate_index - index)
            candidate_box = _ocr_bbox(candidate)
            if label_box and candidate_box:
                distance += (
                    abs(
                        (candidate_box[1] + candidate_box[3]) / 2
                        - (label_box[1] + label_box[3]) / 2
                    )
                    / 1000
                )
                if candidate_box[0] >= label_box[2] - 30:
                    distance -= 1
            candidates.append((distance, candidate))
        if candidates:
            selected = min(candidates, key=lambda item: item[0])[1]
            return _field(str(selected.get("text")), method=method, block=selected, review=review)
    return _missing(method, review=review)


def _ielts_fields(canonical: Mapping[str, Any], *, review: bool) -> dict[str, dict[str, Any]]:
    blocks = _blocks(canonical)

    def person(value: str) -> bool:
        return (
            1 <= len(value.split()) <= 5
            and len(re.sub(r"[^A-Za-zÀ-ỹ]", "", value)) >= 2
            and not re.search(
                r"\d|candidate|family|first|date|number",
                value,
                re.IGNORECASE,
            )
        )

    def family_person(value: str) -> bool:
        return (
            1 <= len(value.split()) <= 3
            and len(re.sub(r"[^A-Za-zÀ-ỹ]", "", value)) >= 2
            and not re.search(
                r"\d|candidate|family|first|date|number",
                value,
                re.IGNORECASE,
            )
        )

    family = _ocr_value_after_label(
        blocks,
        ("Family Name",),
        predicate=family_person,
        method="ielts_family_name_layout",
        review=review,
    )
    first = _ocr_value_after_label(
        blocks,
        ("First Name(s)", "First Name"),
        predicate=person,
        method="ielts_first_name_layout",
        review=review,
    )
    recipient_value = (
        " ".join(str(item["value"]).strip() for item in (family, first) if item.get("value"))
        or None
    )
    recipient = _field(
        recipient_value,
        method="ielts_family_first_layout",
        block=family if family.get("value") else first,
        review=review,
    )
    credential = next(
        (block for block in blocks if re.search(r"\bacademic\b", _fold(block.get("text")))),
        None,
    )
    credential_type_text = None
    if credential:
        raw_credential_type = " ".join(str(credential.get("text") or "").split())
        type_match = re.search(
            r"\b(academic|general\s+training|life\s+skills)\b",
            raw_credential_type,
            re.IGNORECASE,
        )
        credential_type_text = type_match.group(1).upper() if type_match else raw_credential_type
    credential_type = _field(
        credential_type_text,
        method="ielts_credential_type_layout",
        block=credential,
        review=review,
    )

    def candidate_number_from_blocks() -> str | None:
        for idx, block in enumerate(blocks):
            text = str(block.get("text") or "").strip()
            m = re.search(
                r"\bcandidate\s+(?:number|no|num)\b[:\s#-]*([0-9]{6})(?![0-9A-Za-z])",
                text,
                re.IGNORECASE,
            )
            if m:
                return m.group(1)
            if re.search(r"\bcandidate\s+(?:number|no|num)\b", text, re.IGNORECASE):
                for next_idx in (idx + 1, idx + 2):
                    if next_idx < len(blocks):
                        next_text = str(blocks[next_idx].get("text") or "").strip()
                        if re.fullmatch(r"[0-9]{6}", next_text):
                            return next_text
        return None

    candidate_num = candidate_number_from_blocks()
    digit_positions = frozenset({0, 1, 4, 5, 6, 7, 8, 9, 14, 15, 16})
    ocr_digit_replacements = {"O": "0", "I": "1", "L": "1", "S": "5", "Z": "2"}
    standard_trf_pattern = re.compile(r"^[0-9]{2}[A-Z]{2}[0-9]{6}[A-Z]{3,4}[0-9]{3}[A-Z]$")

    def repair_trf_token(token: str, cand_num: str | None) -> str | None:
        if len(token) != 18 or not cand_num or len(cand_num) != 6:
            return None
        chars = list(token.upper())
        for pos in digit_positions:
            if chars[pos] in ocr_digit_replacements:
                chars[pos] = ocr_digit_replacements[chars[pos]]
        repaired = "".join(chars)
        if (
            repaired[4:10] == cand_num
            and standard_trf_pattern.fullmatch(repaired) is not None
        ):
            return repaired
        return None

    def form_number(value: str) -> bool:
        compact = re.sub(r"\s+", "", value).upper()
        if not re.fullmatch(r"[0-9A-Z]{18}", compact):
            return False
        if (
            sum(char.isalpha() for char in compact) < 3
            or sum(char.isdigit() for char in compact) < 2
        ):
            return False
        return not any(
            keyword in compact
            for keyword in (
                "LISTENING",
                "READING",
                "WRITING",
                "SPEAKING",
                "OVERALL",
                "BANDSCORE",
                "VALIDITY",
                "REPORTFORM",
                "ASSESSMENT",
                "CAMBRIDGE",
            )
        )

    def form_numbers_from_block(text: str) -> list[tuple[str, bool]]:
        results: list[tuple[str, bool]] = []
        label_match = re.search(
            r"(?:trf\s*(?:number|no|#)?|form\s*(?:number|no|#)?|(?:test\s+report\s+form\s+(?:number|no|#)?)|certificate\s*(?:number|no|#)?)\s*[:#-]*",
            text,
            re.IGNORECASE,
        )
        candidates_to_check: list[tuple[str, bool]] = []
        if label_match:
            after = text[label_match.end() :]
            candidates_to_check.append((after, True))
        candidates_to_check.append((text, False))

        for candidate_text, is_explicit in candidates_to_check:
            compact = re.sub(r"[^0-9A-Za-z]", "", candidate_text).upper()
            for start in range(max(0, len(compact) - 17)):
                sub = compact[start : start + 18]
                if candidate_num:
                    repaired = repair_trf_token(sub, candidate_num)
                    if repaired:
                        results.append((repaired, is_explicit))
                        continue
                if standard_trf_pattern.fullmatch(sub) or (
                    candidate_num is None and is_explicit and form_number(sub)
                ):
                    results.append((sub, is_explicit))
        return results

    form_anchors = {
        index
        for index, block in enumerate(blocks)
        if re.search(
            r"(?:form|trf)\s*(?:number|no|#)?",
            str(block.get("text") or ""),
            re.IGNORECASE,
        )
    }
    for index in range(len(blocks) - 1):
        if _fold(blocks[index].get("text")) in {"form", "trf"} and _fold(
            blocks[index + 1].get("text")
        ) == "number":
            form_anchors.update((index, index + 1))

    candidates: list[tuple[int, dict[str, Any], str, int]] = []
    for index, block in enumerate(blocks):
        block_text = str(block.get("text") or "")
        found = form_numbers_from_block(block_text)
        for token, is_form_labelled in found:
            is_cand_labelled = bool(
                re.search(r"candidate\s+(?:number|no|num)", block_text, re.IGNORECASE)
                and not is_form_labelled
            )
            is_near_form_anchor = any(abs(index - anchor) <= 2 for anchor in form_anchors)
            if is_form_labelled:
                priority = 3
            elif is_near_form_anchor and not is_cand_labelled:
                priority = 2
            elif not is_cand_labelled:
                priority = 1
            else:
                priority = 0
            candidates.append((index, block, token, priority))

    if candidates:
        max_priority = max(item[3] for item in candidates)
        top_candidates = [item for item in candidates if item[3] == max_priority]
        selected = max(
            top_candidates,
            key=lambda item: (_ocr_bbox(item[1]) or (0, 0, 0, 0))[1],
        )
    else:
        selected = None

    credential_id = _field(
        selected[2] if selected else None,
        method="ielts_form_number_layout",
        block=selected[1] if selected else None,
        review=review,
    )

    def band_score(value: str) -> bool:
        return bool(re.fullmatch(r"(?:[0-9]|10)(?:\.0|\.5)?", value.strip()))

    def inline_band_score(value: str) -> str | None:
        marker = re.search(
            r"(?:overall\s+band\s+(?:score|band)?|overall\s+(?:score|band)?|band\s+score)",
            value,
            re.IGNORECASE,
        )
        if marker is None:
            return None
        match = re.search(
            r"(?<!\d)(?:10|[0-9])(?:[.,][05])?(?!\d)",
            value[marker.end() :],
        )
        return match.group(0).replace(",", ".") if match else None

    def grouped_band_score(value: str) -> str | None:
        if not re.search(r"listening|reading|writing|speaking", value, re.IGNORECASE):
            return None
        score_matches = list(
            re.finditer(r"(?<![\d.])(?:10|[0-9])(?:[.,][05])?(?![\d.])", value)
        )
        overall_match = re.search(
            r"overall(?:\s+band)?(?:\s+score)?\s*[:#-]?\s*"
            r"(?P<score>(?:10|[0-9])(?:[.,][05])?)",
            value,
            re.IGNORECASE,
        )
        if overall_match:
            return overall_match.group("score").replace(",", ".")
        if len(score_matches) >= 5:
            return score_matches[4].group(0).replace(",", ".")
        return None

    score = _missing("ielts_overall_band_layout", review=review)
    for block in blocks:
        inline = inline_band_score(str(block.get("text") or ""))
        if inline is not None and band_score(inline):
            score = _field(
                inline,
                method="ielts_overall_band_layout",
                block=block,
                review=review,
            )
            break
        grouped = grouped_band_score(str(block.get("text") or ""))
        if grouped is not None and band_score(grouped):
            score = _field(
                grouped,
                method="ielts_overall_band_layout",
                block=block,
                review=review,
            )
            break
        key = _fold(block.get("text"))
        if "overall" not in key and key not in {"bvnral", "overall band"}:
            continue
        label_box = _ocr_bbox(block)
        nearby: list[tuple[float, dict[str, Any], str]] = []
        for candidate in blocks:
            value = str(candidate.get("text") or "").strip().replace(",", ".")
            box = _ocr_bbox(candidate)
            if not box or not label_box or not band_score(value):
                continue
            if box[0] >= label_box[2] - 20 and label_box[1] - 35 <= box[1] <= label_box[3] + 90:
                nearby.append(
                    (abs(box[0] - label_box[2]) + abs(box[1] - label_box[1]), candidate, value)
                )
        if nearby:
            _, selected_score, value = min(nearby, key=lambda item: item[0])
            score = _field(
                value, method="ielts_overall_band_layout", block=selected_score, review=review
            )
            break
    if score["value"] is None:
        score = _ocr_value_after_label(
            blocks,
            ("Overall", "Band"),
            predicate=band_score,
            method="ielts_overall_band_layout",
            review=review,
        )
    date_blocks = [
        block
        for block in blocks
        if re.search(
            r"\b\d{1,2}(?:/|-)[A-Za-z0-9]{2,3}(?:/|-)\d{4}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b",
            str(block.get("text") or ""),
        )
    ]
    issue = _missing("ielts_issue_date_layout", review=review)
    if date_blocks:
        selected_date = max(date_blocks, key=lambda block: (_ocr_bbox(block) or (0, 0, 0, 0))[1])
        raw = str(selected_date.get("text") or "")
        date_match = re.search(
            r"\b\d{1,2}[./-](?:\d{1,2}|[A-Za-z]{2,3})[./-]\d{4}\b",
            raw,
        )
        date_value = date_match.group(0) if date_match else raw
        issue = _field(
            _iso_date(date_value) or date_value,
            method="ielts_issue_date_layout",
            block=selected_date,
            review=review,
            normalized=_iso_date(date_value) or date_value,
        )
    return {
        "recipient_name": recipient,
        "credential_id": credential_id,
        "credential_type": credential_type,
        "overall_score": score,
        "issue_date": issue,
    }
