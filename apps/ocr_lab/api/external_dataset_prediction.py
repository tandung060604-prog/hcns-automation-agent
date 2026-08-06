"""Private prediction and aggregate comparison for DATA-12/DATA-13.

The runner reads the inventory and source files only. Ground Truth is loaded by
the evaluator after the prediction artifact exists, so model output cannot be
filled from the typed projection. Raw values stay outside Git under C:\\tmp.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .external_dataset_review import (
        ALLOWED_SUFFIXES,
        FIELD_SPECS,
        OUT_OF_SCOPE_REVIEW_FORMATS,
    )
    from .phase12_ingestion import ingest_document, ingest_image
    from .phase15_idp import (
        _SECTION_HEADINGS,
        _bounded_labeled,
        _box_bounds,
        _credential_type,
        _field_after_marker,
        _is_section_heading,
        _likely_person_name,
        _regex_field,
        classify_phase15_document,
        extract_phase15_document,
    )
except ImportError:  # Direct script execution used by the local OCR runner.
    from external_dataset_review import (
        ALLOWED_SUFFIXES,
        FIELD_SPECS,
        OUT_OF_SCOPE_REVIEW_FORMATS,
    )
    from phase12_ingestion import ingest_document, ingest_image
    from phase15_idp import (
        _SECTION_HEADINGS,
        _bounded_labeled,
        _box_bounds,
        _credential_type,
        _field_after_marker,
        _is_section_heading,
        _likely_person_name,
        _regex_field,
        classify_phase15_document,
        extract_phase15_document,
    )

PREDICTION_SCHEMA_VERSION = "external-dataset-predictions/1.0.0"
DATA13_PREDICTION_SCHEMA_VERSION = "external-dataset-predictions/data13/1.0.0"
REPORT_SCHEMA_VERSION = "external-dataset-data12-aggregate/1.0.0"
DATA13_REPORT_SCHEMA_VERSION = "external-dataset-data13-aggregate/1.0.0"
ACTIVE_CATEGORIES = frozenset(FIELD_SPECS)
# Long free-text sections may be abbreviated by OCR/layout parsing. Structured
# identifiers, dates, money and names remain strict to avoid false acceptance.
SOFT_TEXT_FIELDS = frozenset(
    {
        ("cv", "headline"),
        ("cv", "desired_role"),
        ("cv", "experience"),
        ("cv", "skills"),
        ("cv", "education"),
        ("contract", "job_title"),
        ("contract", "workplace"),
        ("contract", "allowances_summary"),
        ("contract", "salary_payment_schedule"),
    }
)
SOFT_TEXT_MIN_COVERAGE = 0.80
SEMANTIC_PERSON_FIELDS = frozenset(
    {
        ("contract", "employee_name"),
        ("contract", "employer_representative"),
    }
)


class PredictionArtifactError(ValueError):
    """Raised when a private DATA-12 artifact is missing or inconsistent."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PredictionArtifactError(f"Cannot read {path.name}") from exc
    if not isinstance(value, dict):
        raise PredictionArtifactError(f"Artifact {path.name} must be an object")
    return value


def resolve_prediction_paths(
    root: Path,
    *,
    prediction_path: Path | None = None,
    report_path: Path | None = None,
    evaluation_marker_path: Path | None = None,
    version: str = "data12",
) -> tuple[Path, Path, Path]:
    stem = root.expanduser().resolve().name
    suffix = "data13" if version == "data13" else "data12"
    return (
        prediction_path.expanduser().resolve()
        if prediction_path is not None
        else root.parent / f"{stem}-{suffix}-predictions-private.json",
        report_path.expanduser().resolve()
        if report_path is not None
        else root.parent / f"{stem}-{suffix}-aggregate-report.json",
        evaluation_marker_path.expanduser().resolve()
        if evaluation_marker_path is not None
        else root.parent / f"{stem}-{suffix}-evaluate-once.json",
    )


def _safe_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    if not resolved.is_dir() or (resolved / ".git").exists():
        raise PredictionArtifactError("DATA-12 requires a private staging root")
    if any((parent / ".git").exists() for parent in resolved.parents):
        raise PredictionArtifactError("DATA-12 cannot run inside a Git worktree")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_path(root: Path, record: dict[str, Any]) -> Path:
    relative = Path(str(record.get("sourceRelativePath", "")))
    source = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts:
        raise PredictionArtifactError("Unsafe source path in inventory")
    if root not in source.parents or not source.is_file():
        raise FileNotFoundError("External dataset source is unavailable")
    if source.suffix.casefold() not in ALLOWED_SUFFIXES:
        raise PredictionArtifactError("Unsupported external dataset source format")
    expected = str(record.get("sourceSha256", ""))
    if expected and expected != f"sha256:{_sha256(source)}":
        raise PredictionArtifactError(f"Source digest mismatch for {record.get('caseId')}")
    return source


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).casefold()
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(
        "d" if character == "đ" else character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )


def _field(
    value: str | None,
    *,
    method: str,
    block: dict[str, Any] | None,
    review: bool,
) -> dict[str, Any]:
    value = " ".join(value.split()).strip() if isinstance(value, str) and value.strip() else None
    evidence = block.get("evidence") if block else None
    source_span = (
        {
            key: evidence.get(key)
            for key in ("pageIndex", "sourceRef", "bbox")
            if key in evidence
        }
        if isinstance(evidence, dict)
        else None
    )
    return {
        "value": value,
        "normalizedValue": value,
        "status": "needs_review"
        if review and value is not None
        else "accepted"
        if value is not None
        else "not_found",
        "confidence": round(float(block.get("confidence", 0.0)), 6) if block else None,
        "evidence": evidence,
        "sourceSpan": source_span,
        "method": method,
        "extractor": "phase17-family-layout",
        "reviewReason": "ocr_requires_human_review" if review and value is not None else None,
    }


def _from_phase_field(
    field: dict[str, Any],
    *,
    review: bool,
    method: str,
) -> dict[str, Any]:
    """Adapt the shared family parser field without losing its evidence."""

    value = field.get("normalizedValue")
    if value is None:
        value = field.get("value")
    return _field(
        str(value) if value is not None else None,
        method=method,
        block=field if value is not None else None,
        review=review,
    )


def _bounded_external(
    canonical: dict[str, Any],
    labels: tuple[str, ...],
    *,
    stops: tuple[str, ...],
    review: bool,
    method: str,
    normalizer: Any = None,
) -> dict[str, Any]:
    return _from_phase_field(
        _bounded_labeled(
            canonical,
            labels,
            stop_labels=stops,
            normalizer=normalizer,
            method=method,
        ),
        review=review,
        method=method,
    )


def _regex_external(
    canonical: dict[str, Any],
    patterns: tuple[str, ...],
    *,
    review: bool,
    method: str,
    data_type: str = "string",
    normalizer: Any = None,
) -> dict[str, Any]:
    return _from_phase_field(
        _regex_field(
            canonical,
            patterns,
            data_type=data_type,
            normalizer=normalizer,
            method=method,
        ),
        review=review,
        method=method,
    )


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


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(str(value).replace("–", "-").split()).upper()
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%d/%b/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(cleaned, pattern).strftime("%Y-%m-%d")
        except ValueError:
            continue
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", cleaned)
    if match:
        try:
            return datetime(
                int(match.group(3)), int(match.group(2)), int(match.group(1))
            ).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def _canonical_blocks(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for page in canonical.get("pages", [])
        for block in page.get("blocks", [])
        if str(block.get("text") or "").strip()
    ]


def _cv_name_candidate(value: str) -> bool:
    words = value.split()
    letters = [character for character in value if character.isalpha()]
    key = _fold(value)
    return (
        2 <= len(words) <= 6
        and len(letters) >= 6
        and "@" not in value
        and not any(character.isdigit() for character in value)
        and key not in {"curriculum vitae", "ky nang", "hoc van", "kinh nghiem lam viec"}
    )


def _cv_header_fields(canonical: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    blocks = _canonical_blocks(canonical)
    empty = _field(None, method="cv_header_layout", block=None, review=False)
    for block in blocks[:5]:
        text = str(block.get("text") or "").strip(" •")
        if not text or "@" in text or "|" in text:
            continue
        parts = re.split(r"(?<=[a-zà-ỹ])(?=[A-ZĐ])", text, maxsplit=1)
        if len(parts) == 2 and _cv_name_candidate(parts[0].strip()):
            name = _field(parts[0].strip(), method="cv_header_name", block=block, review=False)
            headline = _field(parts[1].strip(), method="cv_header_headline", block=block, review=False)
            return name, headline
        if _cv_name_candidate(text):
            name = _field(text, method="cv_header_name", block=block, review=False)
            for candidate in blocks[blocks.index(block) + 1 : blocks.index(block) + 4]:
                candidate_text = str(candidate.get("text") or "").strip(" •")
                if candidate_text and "|" not in candidate_text and "@" not in candidate_text:
                    return name, _field(
                        candidate_text,
                        method="cv_header_headline",
                        block=candidate,
                        review=False,
                    )
            return name, empty
    return empty, empty


def _cv_contact_address(canonical: dict[str, Any], *, review: bool) -> dict[str, Any]:
    for block in _canonical_blocks(canonical)[:6]:
        text = str(block.get("text") or "")
        if "|" not in text:
            continue
        for part in reversed([item.strip() for item in text.split("|")]):
            if part and "@" not in part and "linkedin" not in part.casefold() and not re.search(r"\d", part):
                return _field(part, method="cv_contact_layout", block=block, review=review)
    return _field(None, method="cv_contact_layout", block=None, review=review)


def _cv_email(canonical: dict[str, Any], *, review: bool) -> dict[str, Any]:
    for block in _canonical_blocks(canonical)[:8]:
        text = str(block.get("text") or "")
        match = re.search(
            r"([A-Z0-9._%+-]+(?:\s+[A-Z0-9._%+-]+)?)\s*@\s*([A-Z0-9.-]+)\s*(?:\.|\s+)?(com|vn|net|org)\b",
            text,
            re.IGNORECASE,
        )
        if not match:
            continue
        local = re.sub(r"\s+", ".", match.group(1).strip(" ."))
        domain = re.sub(r"\s+", "", match.group(2)).strip(".")
        return _field(
            f"{local}@{domain}.{match.group(3).lower()}",
            block=block,
            method="cv_email_ocr_layout",
            review=review,
        )
    return _field(None, method="cv_email_ocr_layout", block=None, review=review)


def _cv_layout_headline(canonical: dict[str, Any], *, review: bool) -> dict[str, Any]:
    blocks = _canonical_blocks(canonical)
    for index, block in enumerate(blocks[:6]):
        if not _cv_name_candidate(str(block.get("text") or "").strip()):
            continue
        parts: list[str] = []
        evidence = None
        for candidate in blocks[index + 1 : index + 4]:
            text = str(candidate.get("text") or "").strip()
            if (
                not text
                or "|" in text
                or "@" in text
                or re.search(r"\d", text)
                or _fold(text) in {"muc tieu nghe nghiep", "objective"}
            ):
                break
            parts.append(text)
            evidence = evidence or candidate
            if sum(len(item.split()) for item in parts) >= 4:
                break
        if parts:
            return _field(" ".join(parts), method="cv_header_headline", block=evidence, review=review)
    return _field(None, method="cv_header_headline", block=None, review=review)


def _cv_years(canonical: dict[str, Any], *, review: bool) -> dict[str, Any]:
    for block in _canonical_blocks(canonical):
        match = re.search(r"(\d+)\s+nam", _fold(block.get("text")))
        if match:
            return _field(
                f"{match.group(1)} năm",
                method="cv_years_ocr_layout",
                block=block,
                review=review,
            )
    return _field(None, method="cv_years_ocr_layout", block=None, review=review)


def _cv_desired_role(canonical: dict[str, Any], *, review: bool) -> dict[str, Any]:
    blocks = _canonical_blocks(canonical)
    in_objective = False
    for block in blocks:
        text = str(block.get("text") or "").strip()
        key = _fold(text)
        if "muc tieu nghe nghiep" in key or key == "objective":
            in_objective = True
            continue
        if in_objective and any(
            key == marker or key.startswith(f"{marker} ") or key.startswith(f"{marker} &")
            for marker in ("hoc van", "kinh nghiem", "ky nang", "chung chi", "du an")
        ):
            break
        if not in_objective or not text:
            continue
        patterns = (
            r"\b(?:vị trí|trở thành|theo hướng)\s+(.+?)(?=\s+(?:cho|trong|với|có)\b|[.;]|$)",
            r"^\s*[•-]?\s*([^,.;]+?)(?=\s+với\b)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return _field(
                    match.group(1).strip(" .;,-"),
                    method="cv_objective_role_layout",
                    block=block,
                    review=review,
                )
    return _field(None, method="cv_objective_role_layout", block=None, review=review)


def _ocr_bbox(block: dict[str, Any]) -> tuple[float, float, float, float] | None:
    evidence = block.get("evidence")
    return _box_bounds(evidence.get("bbox")) if isinstance(evidence, dict) else None


def _same_cv_column(
    box: tuple[float, float, float, float],
    heading_box: tuple[float, float, float, float],
    *,
    heading_full_width: bool,
    page_width: float,
) -> bool:
    if heading_full_width:
        return True
    bx0, _, bx1, _ = box
    hx0, _, hx1, _ = heading_box
    overlap = min(hx1, bx1) - max(hx0, bx0)
    return overlap > 0 or abs(((bx0 + bx1) / 2) - ((hx0 + hx1) / 2)) <= max(
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
    hx0, hy0, hx1, hy1 = heading_box
    heading_center = (hx0 + hx1) / 2
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
    canonical: dict[str, Any],
    headings: tuple[str, ...],
    *,
    review: bool,
    method: str,
) -> dict[str, Any]:
    """Extract one CV section from OCR geometry without trusting engine order."""

    normalized_headings = tuple(_fold(item) for item in headings)
    for page in canonical.get("pages", []):
        blocks = [
            block for block in page.get("blocks", []) if str(block.get("text") or "").strip()
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
            hx0, hy0, hx1, hy1 = heading_box
            heading_full_width = hx1 - hx0 >= page_width * 0.6
            heading_height = max(1.0, hy1 - hy0)
            nearby_headings = [
                other_box
                for other, other_box in positioned
                if other_box is not None
                and other is not heading
                and _is_section_heading(_fold(other.get("text")))
                and abs(((other_box[1] + other_box[3]) / 2) - ((hy0 + hy1) / 2))
                <= max(36.0, heading_height * 1.5)
            ]

            next_heading_y = min(
                (
                    other_box[1]
                    for other, other_box in positioned
                    if other_box is not None
                    and other_box[1] > hy0
                    and _same_cv_column(
                        other_box,
                        heading_box,
                        heading_full_width=heading_full_width,
                        page_width=page_width,
                    )
                    and any(
                        _fold(other.get("text")) == item
                        or _fold(other.get("text")).startswith(f"{item} ")
                        for item in _SECTION_HEADINGS
                    )
                ),
                default=None,
            )
            section_boxes = [
                box
                for _, box in positioned
                if box is not None
                and box[1] >= hy1 - 4
                and (next_heading_y is None or box[1] < next_heading_y)
            ]
            left_bound, right_bound = _cv_section_bounds(
                heading_box,
                heading_full_width,
                nearby_headings,
                section_boxes,
                page_width,
            )
            selected: list[tuple[tuple[float, float, float, float], dict[str, Any]]] = []
            for block, box in positioned:
                if box is None or block is heading:
                    continue
                if box[1] < hy1 - 4 or (next_heading_y is not None and box[1] >= next_heading_y):
                    continue
                if (
                    box[2] > left_bound
                    and box[0] < right_bound
                    and not _is_section_heading(_fold(block.get("text")))
                ):
                    selected.append((box, block))
            if selected:
                median_height = sorted(
                    box[3] - box[1] for box, _ in selected
                )[len(selected) // 2]
                line_tolerance = max(18.0, median_height * 0.65)
                lines: list[list[tuple[tuple[float, float, float, float], dict[str, Any]]]] = []
                for item in sorted(
                    selected,
                    key=lambda value: ((value[0][1] + value[0][3]) / 2, value[0][0]),
                ):
                    center_y = (item[0][1] + item[0][3]) / 2
                    if lines:
                        last_center = (lines[-1][-1][0][1] + lines[-1][-1][0][3]) / 2
                        if center_y - last_center <= line_tolerance:
                            lines[-1].append(item)
                            continue
                    lines.append([item])
                selected = [
                    item
                    for line in lines
                    for item in sorted(line, key=lambda value: value[0][0])
                ]
                return _field(
                    "\n".join(str(block.get("text") or "").strip() for _, block in selected),
                    method=method,
                    block=selected[0][1],
                    review=review,
                )
    return _field(None, method=method, block=None, review=review)


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
        key = _fold(block.get("text"))
        if not any(label in key for label in keys):
            continue
        label_box = _ocr_bbox(block)
        candidates: list[tuple[float, dict[str, Any]]] = []
        for candidate_index, candidate in enumerate(blocks[index + 1 : index + 5], index + 1):
            text = str(candidate.get("text") or "").strip()
            candidate_key = _fold(text)
            if any(
                marker in candidate_key
                for marker in ("first name", "candidate", "date", "sex", "scheme", "country", "nationality", "test results", "overall")
            ):
                break
            if not text or not predicate(text):
                continue
            candidate_box = _ocr_bbox(candidate)
            distance = float(candidate_index - index)
            if label_box and candidate_box:
                lx0, ly0, lx1, ly1 = label_box
                cx0, cy0, cx1, cy1 = candidate_box
                if cy0 < ly0 - 80 or cy0 > ly1 + 100:
                    distance += 10
                if cx0 >= lx1 - 30:
                    distance -= 1
                distance += abs((cy0 + cy1) / 2 - (ly0 + ly1) / 2) / 1000
            candidates.append((distance, candidate))
        if candidates:
            selected = min(candidates, key=lambda item: item[0])[1]
            return _field(str(selected.get("text")), method=method, block=selected, review=review)
    return _field(None, method=method, block=None, review=review)


def _ielts_fields(canonical: dict[str, Any], *, review: bool) -> dict[str, dict[str, Any]]:
    blocks = _canonical_blocks(canonical)
    person = lambda value: (
        1 <= len(value.split()) <= 5
        and len(re.sub(r"[^A-Za-zÀ-ỹ]", "", value)) >= 3
        and not re.search(r"\d|candidate|family|first|date|number", value, re.IGNORECASE)
    )
    family_person = lambda value: (
        1 <= len(value.split()) <= 3
        and len(re.sub(r"[^A-Za-zÀ-ỹ]", "", value)) >= 2
        and not re.search(r"\d|candidate|family|first|date|number", value, re.IGNORECASE)
    )
    family = _ocr_value_after_label(
        blocks, ("Family Name",), predicate=family_person,
        method="ielts_family_name_layout", review=review,
    )
    first = _ocr_value_after_label(
        blocks, ("First Name(s)", "First Name"), predicate=person,
        method="ielts_first_name_layout", review=review,
    )
    recipient_value = " ".join(
        str(item["value"]).strip() for item in (family, first) if item.get("value")
    ) or None
    recipient = _field(
        recipient_value,
        block=family if family.get("value") is not None else first,
        method="ielts_family_first_layout",
        review=review,
    )

    credential = next(
        (block for block in blocks if _fold(block.get("text")) == "academic"),
        None,
    )
    credential_type = _field(
        "IELTS Academic" if credential else None,
        block=credential,
        method="ielts_credential_type_layout",
        review=review,
    )

    def form_number(value: str) -> bool:
        compact = re.sub(r"\s+", "", value).upper()
        return bool(re.fullmatch(r"[0-9A-Z]{18}", compact)) and sum(char.isalpha() for char in compact) >= 6

    def normalize_form_number(value: str) -> str:
        chars = list(re.sub(r"\s+", "", value).upper())
        digit_positions = set(range(0, 2)) | set(range(4, 10)) | set(range(14, 17))
        replacements = {"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"}
        for index in digit_positions:
            if index < len(chars):
                chars[index] = replacements.get(chars[index], chars[index])
        return "".join(chars)

    form_candidates = [block for block in blocks if form_number(str(block.get("text") or ""))]
    credential_id = _field(
        normalize_form_number(str(selected.get("text"))) if (selected := (max(form_candidates, key=lambda block: (_ocr_bbox(block) or (0, 0, 0, 0))[1]) if form_candidates else None)) else None,
        block=selected,
        method="ielts_form_number_layout",
        review=review,
    )
    if credential_id.get("value") is not None:
        credential_id["value"] = normalize_form_number(str(credential_id["value"]))
        credential_id["normalizedValue"] = credential_id["value"]

    def band_score(value: str) -> bool:
        return bool(re.fullmatch(r"(?:[0-9]|10)(?:\.0|\.5)?", value.strip()))

    score = _field(None, method="ielts_overall_band_layout", block=None, review=review)
    for block in blocks:
        key = _fold(block.get("text"))
        if "overall" not in key and key not in {"bvnral", "overall band"}:
            continue
        label_box = _ocr_bbox(block)
        candidates = []
        for candidate in blocks:
            value = str(candidate.get("text") or "").strip().replace(",", ".")
            box = _ocr_bbox(candidate)
            if not box or not label_box or not band_score(value):
                continue
            if box[0] < label_box[2] - 20 or box[1] < label_box[1] - 35 or box[1] > label_box[3] + 90:
                continue
            candidates.append((abs(box[0] - label_box[2]) + abs(box[1] - label_box[1]), candidate, value))
        if candidates:
            _, selected, value = min(candidates, key=lambda item: item[0])
            score = _field(value, block=selected, method="ielts_overall_band_layout", review=review)
            break
    if score["value"] is None:
        score = _ocr_value_after_label(
            blocks, ("Overall", "Band"), predicate=band_score,
            method="ielts_overall_band_layout", review=review,
        )

    date_blocks = [
        block for block in blocks
        if re.search(r"\b\d{1,2}(?:/|-)[A-Za-z0-9]{2,3}(?:/|-)\d{4}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b", str(block.get("text") or ""))
    ]
    issue = _field(None, method="ielts_issue_date_layout", block=None, review=review)
    if date_blocks:
        selected = max(
            date_blocks,
            key=lambda block: (_ocr_bbox(block) or (0, 0, 0, 0))[1],
        )
        raw = str(selected.get("text") or "")
        normalized = _iso_date(raw)
        issue = _field(normalized or raw, method="ielts_issue_date_layout", block=selected, review=review)
        issue["normalizedValue"] = normalized or issue["value"]
    return {
        "recipient_name": recipient,
        "credential_id": credential_id,
        "credential_type": credential_type,
        "overall_score": score,
        "issue_date": issue,
    }


def _narrative_label(
    canonical: dict[str, Any],
    pattern: str,
    *,
    method: str,
    review: bool,
    normalizer: Any = None,
    continue_lines: bool = True,
) -> dict[str, Any]:
    blocks = _canonical_blocks(canonical)
    compiled = re.compile(pattern, re.IGNORECASE)
    for index, block in enumerate(blocks):
        text = str(block.get("text") or "").strip()
        match = compiled.search(text)
        if not match:
            continue
        value = match.group(1).strip(" .;:-")
        evidence = block
        cursor = index + 1
        can_continue = continue_lines and match.end() >= len(text.rstrip())
        while can_continue and value and not value.endswith(".") and cursor < len(blocks) and len(value) < 320:
            candidate = str(blocks[cursor].get("text") or "").strip()
            if (
                not candidate
                or re.match(r"^(?:\d+\.\s*|Điều\s+\d+|BÊN\s+[AB])", candidate, re.IGNORECASE)
            ):
                break
            value = f"{value} {candidate}".strip(" .;:-")
            cursor += 1
        normalized = normalizer(value) if normalizer else value
        return _field(value, method=method, block=evidence, review=review) | {
            "normalizedValue": normalized,
        }
    return _field(None, method=method, block=None, review=review)


def _contract_party_view(
    canonical: dict[str, Any],
    start_markers: tuple[str, ...],
    end_markers: tuple[str, ...],
) -> dict[str, Any]:
    blocks = _canonical_blocks(canonical)
    start_keys = tuple(_fold(marker) for marker in start_markers)
    end_keys = tuple(_fold(marker) for marker in end_markers)

    def starts_with_marker(text: str, markers: tuple[str, ...]) -> bool:
        key = _fold(text)
        return any(
            key == marker
            or re.match(rf"^{re.escape(marker)}(?:\s*[:\-–—]|\s|$)", key)
            for marker in markers
        )

    start = next(
        (
            index
            for index, block in enumerate(blocks)
            if starts_with_marker(block.get("text", ""), start_keys)
        ),
        None,
    )
    if start is None:
        return canonical
    end = next(
        (
            index
            for index, block in enumerate(blocks[start + 1 :], start + 1)
            if starts_with_marker(block.get("text", ""), end_keys)
        ),
        len(blocks),
    )
    selected = blocks[start:end]
    if not selected:
        return canonical
    return {
        **canonical,
        "plainText": "\n".join(str(block.get("text") or "") for block in selected),
        "pages": [{"blocks": selected, "ocrBlocks": selected}],
    }


def _normalize_party_person(value: str) -> str:
    value = re.sub(r"^(?:Ông|Bà|Ông/bà)\s+", "", value.strip(), flags=re.IGNORECASE)
    value = re.split(
        r"\s+(?:Chức vụ|Chức danh|Giới tính|Ngày sinh|CMND/CCCD số|CCCD số)"
        r"\s*(?::|[-–—])?\s*",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return value.strip(" .;:-")


def _contract_party_person(
    canonical: dict[str, Any],
    *,
    start_markers: tuple[str, ...],
    end_markers: tuple[str, ...],
    narrative_pattern: str,
    labels: tuple[str, ...],
    stops: tuple[str, ...],
    method: str,
    fallback_method: str,
    review: bool,
) -> dict[str, Any]:
    party = _contract_party_view(canonical, start_markers, end_markers)
    result = _narrative_label(
        party,
        narrative_pattern,
        method=method,
        review=review,
        normalizer=_normalize_party_person,
        continue_lines=False,
    )
    if result["value"] is not None:
        return result
    return _bounded_external(
        party,
        labels,
        stops=stops,
        review=review,
        method=fallback_method,
        normalizer=_normalize_party_person,
    )


def _weekly_hours(canonical: dict[str, Any], *, review: bool) -> dict[str, Any]:
    for block in _canonical_blocks(canonical):
        text = str(block.get("text") or "")
        if "thời giờ làm việc" not in text.casefold() and "thoi gio lam viec" not in _fold(text):
            continue
        times = [
            (int(hour), int(minute or 0))
            for hour, minute in re.findall(r"(\d{1,2})h(\d{2})?", text, re.IGNORECASE)
        ]
        if len(times) < 4:
            continue
        daily = sum(
            (times[index + 1][0] + times[index + 1][1] / 60)
            - (times[index][0] + times[index][1] / 60)
            for index in (0, 2)
        )
        weekly = daily * 5
        def fmt(value: float) -> str:
            return str(int(value)) if value.is_integer() else str(value).replace(".", ",")
        result = f"{fmt(weekly)} giờ/tuần"
        if not daily.is_integer():
            result += f" — {fmt(daily)} giờ/ngày × 5 ngày"
        return _field(result, method="weekly_hours_schedule", block=block, review=review)
    return _field(None, method="weekly_hours_schedule", block=None, review=review)


def _external_fields(
    category: str,
    canonical: dict[str, Any],
    extraction: dict[str, Any],
    *,
    ocr: bool,
) -> dict[str, dict[str, Any]]:
    phase_fields = extraction.get("fields", {})

    def direct(name: str, aliases: tuple[str, ...] = ()) -> dict[str, Any]:
        for candidate in (name, *aliases):
            item = phase_fields.get(candidate)
            if isinstance(item, dict) and item.get("value") is not None:
                return _from_phase_field(
                    item,
                    method="phase15_family_alias",
                    review=ocr,
                )
        return _field(None, method="phase15_family_alias", block=None, review=ocr)

    if category == "cv":
        name = direct("fullName")
        layout_name, layout_headline = _cv_header_fields(canonical)
        if name["value"] is None or not _cv_name_candidate(str(name["value"])):
            if layout_name.get("value") is not None:
                name = _field(
                    str(layout_name["value"]),
                    method=str(layout_name.get("method") or "cv_header_name"),
                    block=layout_name,
                    review=ocr,
                )
        if ocr:
            combined_headline = _cv_layout_headline(canonical, review=ocr)
            if combined_headline["value"] is not None:
                layout_headline = combined_headline
        headline = direct("headline")
        if headline["value"] is None and layout_headline.get("value") is not None:
            headline = _field(
                str(layout_headline["value"]),
                method=str(layout_headline.get("method") or "cv_header_headline"),
                block=layout_headline,
                review=ocr,
            )
        if headline["value"] is None:
            headline = _bounded_external(
                canonical,
                ("Vị trí ứng tuyển", "Chức danh", "Vị trí", "Headline"),
                stops=("Địa chỉ", "Học vấn", "Kinh nghiệm", "Kỹ năng"),
                review=ocr,
                method="cv_headline_label",
            )
        email = direct("email")
        if email["value"] is None:
            email = _regex_external(
                canonical,
                (r"\b([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\b",),
                method="email_pattern",
                review=ocr,
            )
        if email["value"] is None and ocr:
            email = _cv_email(canonical, review=ocr)
        elif ocr:
            layout_email = _cv_email(canonical, review=ocr)
            if layout_email["value"] is not None:
                email = layout_email
        phone = direct("phoneNumber")
        if phone["value"] is None:
            phone = _regex_external(
                canonical,
                (r"((?:\+?84|0)(?:[\s.-]?\d){8,10})",),
                method="phone_pattern",
                review=ocr,
            )
        address = direct("address")
        if address["value"] is None:
            address = _bounded_external(
                canonical,
                ("Địa chỉ", "Address"),
                stops=("Mục tiêu nghề nghiệp", "Kinh nghiệm", "Kỹ năng", "Học vấn"),
                review=ocr,
                method="cv_address_label",
            )
        if address["value"] is None:
            address = _cv_contact_address(canonical, review=ocr)
        education = direct("education")
        if ocr:
            geometry_education = _cv_ocr_section(
                canonical, ("Học vấn",), review=ocr, method="cv_education_ocr_geometry"
            )
            if geometry_education["value"] is not None:
                education = geometry_education
        if education["value"] is None:
            education = _from_phase_field(
                extraction.get("fields", {}).get("education", {"value": None}),
                method="section",
                review=ocr,
            )
        experience = direct("experience")
        if ocr:
            geometry_experience = _cv_ocr_section(
                canonical,
                ("Kinh nghiệm làm việc", "Kinh nghiệm"),
                review=ocr,
                method="cv_experience_ocr_geometry",
            )
            if geometry_experience["value"] is not None:
                experience = geometry_experience
        if experience["value"] is None:
            experience = _from_phase_field(
                extraction.get("fields", {}).get("experience", {"value": None}),
                method="section",
                review=ocr,
            )
        skills = direct("skills")
        if ocr:
            geometry_skills = _cv_ocr_section(
                canonical, ("Kỹ năng",), review=ocr, method="cv_skills_ocr_geometry"
            )
            if geometry_skills["value"] is not None:
                skills = geometry_skills
        if skills["value"] is None:
            skills = _from_phase_field(
                extraction.get("fields", {}).get("skills", {"value": None}),
                method="section",
                review=ocr,
            )
        desired = _cv_desired_role(canonical, review=ocr)
        if desired["value"] is None:
            desired = _bounded_external(
                canonical,
                ("Mục tiêu nghề nghiệp", "Desired role", "Vị trí mong muốn"),
                stops=("Học vấn", "Kinh nghiệm", "Kỹ năng"),
                review=ocr,
                method="cv_desired_role_section",
            )
        years = _regex_external(
            canonical,
            (r"((?:hơn|trên|ít nhất)\s+\d+\s+năm)", r"(\d+\s+năm\s+kinh\s+nghiệm)", r"(\d+\s+năm)"),
            method="years_experience_pattern",
            review=ocr,
        )
        if years["value"] is None and ocr:
            years = _cv_years(canonical, review=ocr)
        return {
            "full_name": name,
            "headline": headline,
            "email": email,
            "phone_number": phone,
            "address": address,
            "desired_role": desired,
            "years_experience": years,
            "experience": experience,
            "skills": skills,
            "education": education,
        }

    if category == "contract":
        labels = (
            "Số hợp đồng", "Số", "Ngày ký", "Hiệu lực từ", "Bắt đầu từ",
            "Kết thúc thử việc", "Hết hạn thử việc", "Đại diện cho", "Công ty",
            "Đại diện", "Người lao động", "Ông/bà", "Họ và tên", "CCCD số",
            "CMND số", "Công việc/Chức danh", "Chức danh", "Vị trí công việc",
            "Địa điểm làm việc", "Mức lương thử việc", "Lương thử việc", "Phụ cấp",
            "Thanh toán", "Trả lương", "Số giờ/tuần", "Giờ/tuần",
        )
        contract_number = _bounded_external(
            canonical,
            ("Số hợp đồng", "Số", "Contract number"),
            stops=labels,
            review=ocr,
            method="contract_number_label",
        )
        date_pattern = (
            r"((?:\d{1,2}[./-]\d{1,2}[./-]\d{4}|"
            r"\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}))"
        )
        sign_date = _regex_external(
            canonical,
            (rf"ngày\s+{date_pattern}",),
            method="sign_date_narrative",
            normalizer=_date,
            review=ocr,
        )
        if sign_date["value"] is None:
            sign_date = _bounded_external(
                canonical,
                ("Ngày ký", "Ngay ky"),
                stops=labels,
                method="sign_date_label",
                normalizer=_date,
                review=ocr,
            )
        effective = _regex_external(
            canonical,
            (rf"kể từ ngày\s+{date_pattern}",),
            method="effective_date_narrative",
            normalizer=_date,
            review=ocr,
        )
        if effective["value"] is None:
            effective = _bounded_external(
                canonical,
                ("Hiệu lực từ", "Hieu luc tu", "Bắt đầu từ", "Bat dau tu"),
                stops=labels,
                method="effective_date_label",
                normalizer=_date,
                review=ocr,
            )
        probation_end = _regex_external(
            canonical,
            (rf"đến ngày\s+{date_pattern}",),
            method="probation_end_narrative",
            normalizer=_date,
            review=ocr,
        )
        if probation_end["value"] is None:
            probation_end = _bounded_external(
                canonical,
                ("Kết thúc thử việc", "Ket thuc thu viec", "Hết hạn thử việc"),
                stops=labels,
                method="probation_end_label",
                normalizer=_date,
                review=ocr,
            )
        employer = _regex_external(
            canonical,
            (r"Tên\s+công\s+ty\s*:\s*(.+)",),
            method="employer_name_label",
            review=ocr,
        )
        if employer["value"] is None:
            employer = _bounded_external(
                canonical,
                ("Đại diện cho", "Công ty"),
                stops=labels,
                review=ocr,
                method="employer_label",
            )
        representative = _contract_party_person(
            canonical,
            start_markers=("Bên A", "Bên A: Người sử dụng lao động"),
            end_markers=("Bên B", "Bên B: Người lao động"),
            narrative_pattern=(
                r"Đại\s+diện\s+(?:bởi|cho)\s*:\s*(?:Ông|Bà)\s+"
                r"(.+?)(?=\s+Chức\s+vụ\s*(?::|[-–—])|"
                r"\s+Chức\s+danh\s*(?::|[-–—])|$)"
            ),
            labels=("Đại diện bởi", "Đại diện cho", "Đại diện"),
            stops=labels + ("Bên B", "Người lao động", "Họ và tên"),
            method="representative_name_label",
            fallback_method="representative_label",
            review=ocr,
        )
        employee = _contract_party_person(
            canonical,
            start_markers=("Bên B", "Bên B: Người lao động"),
            end_markers=("Hai bên thỏa thuận", "Điều 1"),
            narrative_pattern=(
                r"Họ\s+và\s+tên\s*:\s*(.+?)"
                r"(?=\s+Giới\s+tính\s*:|\s+Ngày\s+sinh\s*:|$)"
            ),
            labels=("Người lao động", "Ông/bà", "Họ và tên"),
            stops=labels + ("Giới tính", "Ngày sinh", "CMND/CCCD số"),
            method="employee_name_label",
            fallback_method="employee_label",
            review=ocr,
        )
        employee_id = _regex_external(
            canonical,
            (r"(?:CCCD số|CCCD so|CMND số|CMND so)\s*[:\-]?\s*([0-9]{9,12})",),
            method="employee_id_pattern", review=ocr,
        )
        job = _narrative_label(
            canonical,
            r"Chức\s+danh\s+công\s+việc\s*:\s*(.+?)(?:\.\s*$|$)",
            method="job_title_narrative",
            review=ocr,
        )
        if job["value"] is None:
            job = _bounded_external(
                canonical,
                ("Công việc/Chức danh", "Chức danh", "Vị trí công việc"),
                stops=labels,
                review=ocr,
                method="job_title_label",
            )
        workplace = _narrative_label(
            canonical,
            r"Nơi\s+làm\s+việc\s*:\s*(.+?)(?:\.\s*$|$)",
            method="workplace_narrative",
            review=ocr,
        )
        if workplace["value"] is None:
            workplace = _bounded_external(
                canonical,
                ("Địa điểm làm việc",),
                stops=labels,
                review=ocr,
                method="workplace_label",
            )
        weekly = _weekly_hours(canonical, review=ocr)
        salary = _bounded_external(
            canonical, ("Mức lương thử việc", "Lương thử việc"), stops=labels,
            review=ocr, method="salary_label",
        )
        allowances = _bounded_external(
            canonical, ("Phụ cấp",), stops=labels,
            review=ocr, method="allowances_label",
        )
        payment = _bounded_external(
            canonical, ("Thanh toán", "Trả lương"), stops=labels,
            review=ocr, method="payment_label",
        )
        return {
            "contract_number": contract_number,
            "contract_sign_date": sign_date,
            "effective_date": effective,
            "probation_end_date": probation_end,
            "employer_name": employer,
            "employer_representative": representative,
            "employee_name": employee,
            "employee_id_number": employee_id,
            "job_title": job,
            "workplace": workplace,
            "weekly_hours": weekly,
            "probation_salary_monthly": salary,
            "allowances_summary": allowances,
            "salary_payment_schedule": payment,
        }

    if category == "ielts":
        layout = _ielts_fields(canonical, review=ocr)
        for key, phase_name in (
            ("recipient_name", "recipientName"),
            ("credential_id", "credentialId"),
            ("credential_type", "credentialType"),
            ("overall_score", "overallScore"),
            ("issue_date", "issueDate"),
        ):
            if layout[key]["value"] is None:
                item = direct(phase_name)
                if item["value"] is not None:
                    layout[key] = item
        return layout

    credential = direct("credentialType")
    if credential["value"] is None:
        credential = _from_phase_field(
            _credential_type(canonical), review=ocr, method="credential_type_heading"
        )
    recipient = direct("recipientName")
    if recipient["value"] is None:
        recipient = _bounded_external(
            canonical,
            ("Candidate name", "Recipient", "Họ và tên", "Cấp cho", "Awarded to"),
            stops=("Candidate number", "Credential ID", "Overall", "Issue date", "Test date"),
            review=ocr,
            method="recipient_label",
        )
    if recipient["value"] is None:
        recipient = _from_phase_field(
            _field_after_marker(
                canonical,
                ("Trân trọng chứng nhận", "This certifies that", "Awarded to"),
                predicate=_likely_person_name,
                method="recipient_after_credential_marker",
            ),
            review=ocr,
            method="recipient_after_credential_marker",
        )
    credential_id = direct("credentialId")
    if credential_id["value"] is None:
        credential_id = _bounded_external(
            canonical,
            ("TRF No", "Test Report Form", "Candidate number", "Credential ID", "ID",
             "Số hiệu/Mã chứng nhận", "Mã chứng chỉ"),
            stops=("Overall", "Issue date", "Test date", "Candidate name"),
            review=ocr,
            method="credential_id_pattern",
        )
    score = direct("overallScore")
    if score["value"] is None:
        score = _regex_external(
            canonical,
            (r"(?:overall(?: band)?(?: score)?|overall)\s*[:\-]?\s*(\d(?:\.\d)?)",),
            method="overall_score_pattern", review=ocr,
        )
    issue = direct("issueDate")
    if issue["value"] is None:
        issue = _bounded_external(
            canonical,
            ("Issue date", "Test date", "Date of issue", "Ngày cấp", "Ngày thi"),
            stops=("Overall", "Candidate number", "Credential ID"),
            review=ocr,
            method="issue_date_pattern",
            normalizer=_date,
        )
    return {
        "recipient_name": recipient,
        "credential_id": credential_id,
        "credential_type": credential,
        "overall_score": score,
        "issue_date": issue,
    }


def _ocr_pages(paths: list[Path], ocr_engine: Any) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page_index, path in enumerate(paths):
        result = next(iter(ocr_engine.predict(str(path))))
        payload = result.json if hasattr(result, "json") else result
        if isinstance(payload, str):
            payload = json.loads(payload)
        payload = payload.get("res", payload) if isinstance(payload, dict) else {}
        texts = [str(value) for value in payload.get("rec_texts", [])]
        scores = [float(value) for value in payload.get("rec_scores", [])]
        polygons = payload.get("rec_polys", [])
        boxes = [
            polygon.tolist() if hasattr(polygon, "tolist") else polygon for polygon in polygons
        ]
        pages.append(
            {
                "pageIndex": page_index,
                "recognizedTexts": texts,
                "recognitionScores": scores,
                "recognizedBoxes": boxes,
            }
        )
    return pages


def _render_pages(source: Path, destination: Path) -> list[Path]:
    from PIL import Image, ImageOps

    destination.mkdir(parents=True, exist_ok=True)
    if source.suffix.casefold() == ".pdf":
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(source)
        try:
            paths: list[Path] = []
            for index in range(len(document)):
                page = document[index]
                try:
                    image = page.render(scale=200 / 72).to_pil().convert("RGB")
                finally:
                    page.close()
                path = destination / f"page_{index + 1:03d}.png"
                image.save(path, "PNG", optimize=True)
                paths.append(path)
            return paths
        finally:
            document.close()
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    path = destination / "page_001.png"
    image.save(path, "PNG", optimize=True)
    return [path]


def _docx_media(source: Path, destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with zipfile.ZipFile(source) as package:
        for name in package.namelist():
            if not name.startswith("word/media/"):
                continue
            path = destination / Path(name).name
            path.write_bytes(package.read(name))
            paths.append(path)
    return paths


def build_prediction_artifact(
    root: Path,
    inventory_path: Path,
    work_root: Path,
    *,
    ocr_engine: Any,
    scope_policy: str = "data12",
    ocr_engine_name: str | None = None,
) -> dict[str, Any]:
    root = _safe_root(root)
    inventory = _read_object(inventory_path)
    records = inventory.get("cases")
    if not isinstance(records, list):
        raise PredictionArtifactError("Inventory cases are missing")
    documents: list[dict[str, Any]] = []
    for record in records:
        category = str(record.get("category", ""))
        source_format = str(record.get("sourceFormat", ""))
        if category not in ACTIVE_CATEGORIES or source_format in OUT_OF_SCOPE_REVIEW_FORMATS.get(
            category, frozenset()
        ):
            continue
        source = _source_path(root, record)
        data13_scope = scope_policy == "data13"
        scan_input = source_format in {"IMAGE", "PDF_SCAN"}
        ocr_required = scan_input or (
            category == "ielts"
            and source_format == "DOCX"
            and bool(record.get("embeddedImageReview"))
        )
        canonical = ingest_document(source)
        ocr_required = ocr_required or (
            data13_scope
            and category == "ielts"
            and bool(canonical.get("metadata", {}).get("requiresImageOcr"))
        )
        if ocr_required or bool(canonical.get("metadata", {}).get("requiresImageOcr")):
            page_paths = (
                _render_pages(source, work_root / str(record["caseId"]))
                if source.suffix.casefold() != ".docx"
                else _docx_media(source, work_root / str(record["caseId"]))
            )
            pages = _ocr_pages(page_paths, ocr_engine)
            if source.suffix.casefold() == ".docx":
                ocr_canonical = ingest_image(source, pages)
                canonical["pages"][0]["ocrBlocks"] = ocr_canonical["pages"][0]["ocrBlocks"]
                canonical["pages"][0]["blocks"] = (
                    canonical["pages"][0]["blocks"] + ocr_canonical["pages"][0]["blocks"]
                )
                canonical["plainText"] += "\n" + ocr_canonical["plainText"]
            else:
                canonical = ingest_document(source, pages)
        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)
        predicted_category = {
            "CV": "cv",
            "CONTRACT_DECISION": "contract",
            "DEGREE_CERTIFICATE": "ielts",
        }.get(str(classification.get("documentFamily")), "unknown")
        if predicted_category == "unknown" and "ielts" in _fold(canonical.get("plainText")):
            predicted_category = "ielts"
        fields = _external_fields(category, canonical, extraction, ocr=ocr_required)
        documents.append(
            {
                "caseId": record["caseId"],
                "category": category,
                "sourceFormat": source_format,
                "sourceFile": source.name,
                "sourceSha256": record.get("sourceSha256"),
                "predictedCategory": predicted_category,
                "classification": {
                    "documentType": classification.get("documentType"),
                    "documentFamily": classification.get("documentFamily"),
                    "status": classification.get("status"),
                    "confidence": classification.get("confidence"),
                },
                "fields": fields,
                "evaluationIncluded": True,
                "processing": {
                    "usesOcr": ocr_required,
                    "ocrEngine": (
                        ocr_engine_name
                        or getattr(ocr_engine, "engine_name", "paddleocr/latin_pp-ocrv5")
                    ) if ocr_required else None,
                    "ocrScope": "OCR_ALLOWED" if ocr_required else "NATIVE_ONLY",
                    "recommendedAction": "MANUAL_REVIEW" if ocr_required else "USER_REVIEW",
                    "ingestionMode": canonical.get("ingestionMode"),
                    "parserVersion": extraction.get("parserVersion"),
                },
            }
        )
    return {
        "schemaVersion": (
            DATA13_PREDICTION_SCHEMA_VERSION
            if scope_policy == "data13"
            else PREDICTION_SCHEMA_VERSION
        ),
        "createdAt": utc_now(),
        "datasetId": inventory.get("dataset", {}).get("datasetId"),
        "datasetDigest": inventory.get("dataset", {}).get("contentDigest"),
        "documentCount": len(documents),
        "containsRealPII": True,
        "localOnly": True,
        "predictionBlindDuringGroundTruthReview": True,
        "ocrScopePolicy": ("all-active-families" if scope_policy == "data13" else "legacy"),
        "documents": documents,
    }


def _norm(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split())


def _semantic_key(category: str, name: str, value: Any) -> str:
    """Canonicalize only the two explicitly approved Contract person fields."""

    normalized = _norm(value)
    if (category, name) not in SEMANTIC_PERSON_FIELDS:
        return normalized
    normalized = re.sub(r"^(?:ông/bà|ông|bà)\s+", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"\s+(?:chức vụ|chức danh)\b(?:\s*[:\-–—]?\s*.*)?$",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+[\-–—]\s+.+$", "", normalized)
    return " ".join(normalized.casefold().split())


def _field_match(
    category: str,
    name: str,
    truth: Any,
    guess: Any,
) -> dict[str, Any]:
    """Return strict and policy-accepted matching without removing accents."""

    truth_norm, guess_norm = _norm(truth), _norm(guess)
    truth_semantic = _semantic_key(category, name, truth)
    guess_semantic = _semantic_key(category, name, guess)
    semantic_exact = truth_norm == guess_norm or bool(
        truth_norm
        and guess_norm
        and truth_semantic
        and guess_semantic
        and truth_semantic == guess_semantic
    )

    def result(**payload: Any) -> dict[str, Any]:
        payload["semanticExact"] = semantic_exact
        return payload

    if truth_norm == guess_norm:
        return result(
            exact=True,
            match=True,
            matchType="EXACT",
            coverage=1.0,
            diagnosis=None,
        )
    if not truth_norm:
        return result(
            exact=False,
            match=False,
            matchType="EXTRA_PREDICTION" if guess_norm else "EXACT",
            coverage=0.0,
            diagnosis="PREDICTION_FOR_ABSENT_FIELD" if guess_norm else None,
        )
    if not guess_norm:
        return result(
            exact=False,
            match=False,
            matchType="NOT_FOUND",
            coverage=0.0,
            diagnosis="OCR_NOT_RECOGNIZED",
        )
    if (category, name) not in SOFT_TEXT_FIELDS:
        return result(
            exact=False,
            match=False,
            matchType="MISMATCH",
            coverage=0.0,
            diagnosis="OCR_RECOGNIZED_PARSER_MISSED",
        )

    # Case differences are accepted, while NFC accents/diacritics remain part
    # of the comparison so missing or corrupted Vietnamese text is visible.
    truth_fold, guess_fold = truth_norm.casefold(), guess_norm.casefold()
    if truth_fold == guess_fold:
        return result(
            exact=False,
            match=True,
            matchType="CASE_INSENSITIVE",
            coverage=1.0,
            diagnosis=None,
        )
    truth_tokens = re.findall(r"[^\W_]+", truth_fold, flags=re.UNICODE)
    guess_tokens = re.findall(r"[^\W_]+", guess_fold, flags=re.UNICODE)
    overlap = sum((Counter(guess_tokens) & Counter(truth_tokens)).values())
    coverage = overlap / max(1, len(truth_tokens))
    if coverage >= SOFT_TEXT_MIN_COVERAGE:
        return result(
            exact=False,
            match=True,
            matchType="PARTIAL_80",
            coverage=round(coverage, 6),
            diagnosis=None,
        )
    return result(
        exact=False,
        match=False,
        matchType="PARTIAL_BELOW_80",
        coverage=round(coverage, 6),
        diagnosis="PARTIAL_TEXT_BELOW_80",
    )


def _included_documents(prediction: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(document.get("caseId")): document
        for document in prediction.get("documents", [])
        if document.get("evaluationIncluded", True) is not False
    }


def _parser_regression_summary(
    prediction: dict[str, Any],
    baseline_prediction: dict[str, Any] | None,
    ground_truth: dict[str, Any],
) -> tuple[int, int, dict[str, Any]]:
    if baseline_prediction is None:
        return 0, 0, {
            "baselineProvided": False,
            "sameEvaluationSet": None,
            "sameScanEvaluationSet": None,
            "baselineDocumentCount": 0,
            "candidateDocumentCount": len(_included_documents(prediction)),
            "overlapDocumentCount": 0,
            "baselineScanDocumentCount": 0,
            "candidateScanDocumentCount": sum(
                bool(document.get("processing", {}).get("usesOcr"))
                for document in _included_documents(prediction).values()
            ),
            "scanOverlapDocumentCount": 0,
        }
    candidate_by_id = _included_documents(prediction)
    baseline_by_id = _included_documents(baseline_prediction)
    candidate_ids, baseline_ids = set(candidate_by_id), set(baseline_by_id)
    overlap_ids = candidate_ids & baseline_ids
    candidate_scan_ids = {
        case_id
        for case_id, document in candidate_by_id.items()
        if bool(document.get("processing", {}).get("usesOcr"))
    }
    baseline_scan_ids = {
        case_id
        for case_id, document in baseline_by_id.items()
        if bool(document.get("processing", {}).get("usesOcr"))
    }
    scan_overlap_ids = overlap_ids & candidate_scan_ids & baseline_scan_ids
    gt_by_id = {str(case.get("caseId")): case for case in ground_truth.get("cases", [])}
    regressions = 0
    scan_regressions = 0
    for case_id in sorted(overlap_ids):
        candidate = candidate_by_id[case_id]
        baseline = baseline_by_id[case_id]
        category = str(candidate.get("category", ""))
        if category != str(baseline.get("category", "")):
            continue
        gt_fields = {
            str(item.get("name")): item for item in gt_by_id.get(case_id, {}).get("fields", [])
        }
        expected = FIELD_SPECS.get(category, ())
        candidate_fields = candidate.get("fields", {})
        baseline_fields = baseline.get("fields", {})
        for name in expected:
            truth = gt_fields.get(name, {}).get("value")
            candidate_value = (
                candidate_fields.get(name, {}).get("value")
                if isinstance(candidate_fields.get(name), dict)
                else None
            )
            baseline_value = (
                baseline_fields.get(name, {}).get("value")
                if isinstance(baseline_fields.get(name), dict)
                else None
            )
            baseline_exact = _field_match(category, name, truth, baseline_value)["exact"]
            candidate_exact = _field_match(category, name, truth, candidate_value)["exact"]
            regressions += int(baseline_exact and not candidate_exact)
            if case_id in scan_overlap_ids:
                scan_regressions += int(baseline_exact and not candidate_exact)
    return regressions, scan_regressions, {
        "baselineProvided": True,
        "sameEvaluationSet": candidate_ids == baseline_ids,
        "sameScanEvaluationSet": candidate_scan_ids == baseline_scan_ids,
        "baselineDocumentCount": len(baseline_ids),
        "candidateDocumentCount": len(candidate_ids),
        "overlapDocumentCount": len(overlap_ids),
        "baselineScanDocumentCount": len(baseline_scan_ids),
        "candidateScanDocumentCount": len(candidate_scan_ids),
        "scanOverlapDocumentCount": len(scan_overlap_ids),
    }


def build_aggregate_report(
    prediction: dict[str, Any],
    ground_truth: dict[str, Any],
    *,
    evaluated_at: str | None = None,
    baseline_prediction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data13_scope = prediction.get("ocrScopePolicy") in {
        "cccd-and-certificate-only",
        "all-active-families",
    }
    report_schema = DATA13_REPORT_SCHEMA_VERSION if data13_scope else REPORT_SCHEMA_VERSION
    gt_by_id = {str(case.get("caseId")): case for case in ground_truth.get("cases", [])}
    exact = 0
    semantic_exact = 0
    ocr_exact = 0
    ocr_field_count = 0
    present = 0
    applicable = 0
    applicable_present = 0
    sensitive_false_acceptance = 0
    field_count = 0
    schema_errors = 0
    classification_matches = 0
    ocr_documents = 0
    manual_review = 0
    false_auto = 0
    excluded_documents = 0
    evaluated_documents = 0
    by_category: dict[str, dict[str, int]] = {}
    diagnoses: dict[str, int] = {}
    for document in prediction.get("documents", []):
        case_id = str(document.get("caseId"))
        category = str(document.get("category"))
        if document.get("evaluationIncluded", True) is False:
            excluded_documents += 1
            continue
        evaluated_documents += 1
        case = gt_by_id.get(case_id, {})
        gt_fields = {str(item.get("name")): item for item in case.get("fields", [])}
        expected = FIELD_SPECS.get(category, ())
        predicted_fields = document.get("fields", {})
        if tuple(predicted_fields) != expected:
            schema_errors += 1
        classification_matches += int(document.get("predictedCategory") == category)
        processing = document.get("processing", {})
        ocr_documents += int(bool(processing.get("usesOcr")))
        manual_review += int(processing.get("recommendedAction") == "MANUAL_REVIEW")
        false_auto += int(
            processing.get("usesOcr") and processing.get("recommendedAction") == "AUTO_CONTINUE"
        )
        stats = by_category.setdefault(
            category,
            {"fields": 0, "exact": 0, "semanticExact": 0, "accepted": 0, "present": 0},
        )
        for name in expected:
            field_count += 1
            stats["fields"] += 1
            truth = gt_fields.get(name, {}).get("value")
            guess = (
                predicted_fields.get(name, {}).get("value")
                if isinstance(predicted_fields.get(name), dict)
                else None
            )
            match = _field_match(category, name, truth, guess)
            exact += int(match["exact"])
            stats["exact"] += int(match["exact"])
            if processing.get("usesOcr"):
                ocr_field_count += 1
                ocr_exact += int(match["exact"])
            semantic_exact += int(match["semanticExact"])
            stats["semanticExact"] += int(match["semanticExact"])
            stats["accepted"] += int(match["match"])
            if _norm(guess):
                present += 1
                stats["present"] += 1
            if _norm(truth):
                applicable += 1
                if _norm(guess):
                    applicable_present += 1
            if gt_fields.get(name, {}).get("sensitive") and match["match"] and not match["exact"]:
                sensitive_false_acceptance += 1
            if match["diagnosis"]:
                reason = match["diagnosis"]
                if reason == "OCR_NOT_RECOGNIZED" and not processing.get("usesOcr"):
                    reason = "PARSER_MISSED"
                diagnoses[reason] = diagnoses.get(reason, 0) + 1
    parser_regressions, scan_parser_regressions, parser_comparison = _parser_regression_summary(
        prediction, baseline_prediction, ground_truth
    )
    return {
        "schemaVersion": report_schema,
        "evaluationKind": "aggregate-only",
        "evaluatedAt": evaluated_at or utc_now(),
        "datasetId": prediction.get("datasetId"),
        "documentCount": len(prediction.get("documents", [])),
        "evaluatedDocumentCount": evaluated_documents,
        "policyExcludedDocumentCount": excluded_documents,
        "fieldCount": field_count,
        "classification": {
            "exactDocumentCount": classification_matches,
            "documentCount": len(prediction.get("documents", [])),
            "evaluatedDocumentCount": evaluated_documents,
            "excludedDocumentCount": excluded_documents,
            "accuracy": round(
                classification_matches / max(1, len(prediction.get("documents", []))), 6
            ),
        },
        "metrics": {
            "fieldExactMatchCount": exact,
            "fieldExactMatchRate": round(exact / max(1, field_count), 6),
            "fieldSemanticMatchCount": semantic_exact,
            "fieldSemanticMatchRate": round(semantic_exact / max(1, field_count), 6),
            "ocrFieldExactMatchCount": ocr_exact,
            "ocrFieldCount": ocr_field_count,
            "ocrFieldExactMatchRate": round(ocr_exact / max(1, ocr_field_count), 6),
            "applicableFieldCount": applicable,
            "applicableFieldPresenceCount": applicable_present,
            "applicableCompletenessRate": round(applicable_present / max(1, applicable), 6),
            "sensitiveFalseAcceptanceCount": sensitive_false_acceptance,
            "parserCorrectRegressionCount": parser_regressions,
            "scanParserCorrectRegressionCount": scan_parser_regressions,
            "fieldAcceptedMatchCount": sum(item["accepted"] for item in by_category.values()),
            "fieldAcceptedMatchRate": round(
                sum(item["accepted"] for item in by_category.values()) / max(1, field_count),
                6,
            ),
            "fieldPresenceCount": present,
            "fieldPresenceRate": round(present / max(1, field_count), 6),
        },
        "byCategory": {
            category: {
                **stats,
                "exactRate": round(stats["exact"] / max(1, stats["fields"]), 6),
                "semanticExactRate": round(
                    stats["semanticExact"] / max(1, stats["fields"]), 6
                ),
                "acceptedRate": round(stats["accepted"] / max(1, stats["fields"]), 6),
                "presenceRate": round(stats["present"] / max(1, stats["fields"]), 6),
            }
            for category, stats in by_category.items()
        },
        "diagnosisCounts": diagnoses,
        "matchingPolicy": {
            "strictExact": "NFC whitespace-normalized equality",
            "softTextFields": sorted(f"{category}.{name}" for category, name in SOFT_TEXT_FIELDS),
            "softTextMinTokenCoverage": SOFT_TEXT_MIN_COVERAGE,
            "caseInsensitiveForSoftText": True,
            "diacriticsSensitive": True,
            "semanticPersonFields": sorted(
                f"{category}.{name}" for category, name in SEMANTIC_PERSON_FIELDS
            ),
            "semanticPersonNormalization": (
                "NFC whitespace normalization; remove leading honorific and trailing "
                "Chức vụ/Chức danh or dash-delimited role; casefold; accents remain sensitive"
            ),
            "semanticMetricDoesNotReplaceStrict": True,
        },
        "schemaErrors": schema_errors,
        "parserRegressionComparison": parser_comparison,
        "ocrPolicy": {
            "ocrDocumentCount": ocr_documents,
            "manualReviewCount": manual_review,
            "manualReviewRate": round(manual_review / max(1, ocr_documents), 6),
            "falseAutoContinueCount": false_auto,
            "ocrAlwaysManualReview": ocr_documents > 0
            and manual_review == ocr_documents
            and false_auto == 0,
            "unsupportedNoOcrCount": excluded_documents,
            "scopePolicy": prediction.get("ocrScopePolicy", "legacy"),
        },
        "decision": "HOLD",
        "promotionAllowed": False,
        "containsRawFieldValues": False,
        "groundTruthUsedForScoringOnly": True,
    }


def build_gate_report(
    candidate_report: dict[str, Any],
    baseline_report: dict[str, Any] | None = None,
    *,
    fallback_candidate: bool = False,
) -> dict[str, Any]:
    """Apply DATA-20 gates to aggregate-only reports without exposing values."""

    metrics = candidate_report.get("metrics", {})
    categories = candidate_report.get("byCategory", {})
    strict_family = {
        category: float(categories.get(category, {}).get("exactRate", 0.0)) >= 0.80
        for category in sorted(ACTIVE_CATEGORIES)
    }
    ocr_policy = candidate_report.get("ocrPolicy", {})
    parser_comparison = candidate_report.get("parserRegressionComparison", {})
    base_rate = (
        float((baseline_report or {}).get("metrics", {}).get("ocrFieldExactMatchRate", 0.0))
        if baseline_report is not None
        else None
    )
    candidate_rate = float(metrics.get("fieldExactMatchRate", 0.0))
    candidate_scan_rate = float(metrics.get("ocrFieldExactMatchRate", 0.0))
    strict_delta = (
        round(candidate_scan_rate - base_rate, 6) if base_rate is not None else None
    )
    fallback = {
        "status": "NOT_EVALUATED" if not fallback_candidate else "HOLD",
        "baselineProvided": base_rate is not None,
        "strictImprovementRate": strict_delta,
        "scanStrictImprovementRate": strict_delta,
        "baselineScanStrictRate": base_rate,
        "candidateScanStrictRate": candidate_scan_rate,
        "minimumStrictImprovementRate": 0.10,
        "parserCorrectRegressionCount": metrics.get("scanParserCorrectRegressionCount", 0),
        "sameEvaluationSet": parser_comparison.get("sameScanEvaluationSet"),
        "fixedScanSubset": True,
        "schemaErrors": candidate_report.get("schemaErrors", 0),
        "scanManualReview": bool(ocr_policy.get("ocrAlwaysManualReview"))
        and int(ocr_policy.get("falseAutoContinueCount", 0)) == 0,
    }
    fallback["pass"] = bool(
        fallback["baselineProvided"]
        and fallback["sameEvaluationSet"] is True
        and strict_delta is not None
        and strict_delta >= 0.10
        and fallback["parserCorrectRegressionCount"] == 0
        and fallback["schemaErrors"] == 0
        and fallback["scanManualReview"]
    )
    if fallback_candidate:
        fallback["status"] = "PASS" if fallback["pass"] else "HOLD"

    gates: dict[str, Any] = {
        "strictOverallAtLeast80": candidate_rate >= 0.80,
        "strictEachFamilyAtLeast80": all(strict_family.values()),
        "strictByFamily": strict_family,
        "applicableCompletenessAtLeast95": int(metrics.get("applicableFieldCount", 0)) > 0
        and float(metrics.get("applicableCompletenessRate", 0.0)) >= 0.95,
        "classificationAtLeast95": float(
            candidate_report.get("classification", {}).get("accuracy", 0.0)
        )
        >= 0.95,
        "schemaErrorsZero": int(candidate_report.get("schemaErrors", 0)) == 0,
        "sensitiveFalseAcceptanceZero": int(
            metrics.get("sensitiveFalseAcceptanceCount", 0)
        )
        == 0,
        "parserCorrectRegressionZero": int(
            metrics.get("parserCorrectRegressionCount", 0)
        )
        == 0,
        "parserRegressionComparisonReady": bool(
            parser_comparison.get("baselineProvided")
            and parser_comparison.get("sameEvaluationSet")
        ),
        "scanAlwaysManualReview": bool(ocr_policy.get("ocrAlwaysManualReview")),
        "falseAutoContinueZero": int(ocr_policy.get("falseAutoContinueCount", 0)) == 0,
        "unsupportedOcrZero": int(ocr_policy.get("unsupportedNoOcrCount", 0)) == 0,
        "acceptedTextReportedSeparately": "fieldAcceptedMatchRate" in metrics,
        "semanticMetricNotUsedAsStrictGate": True,
    }
    passed = all(gates.values()) and (not fallback_candidate or fallback["pass"])
    return {
        "schemaVersion": "external-dataset-data20-gate/1.0.0",
        "evaluationKind": "development-gate-harness",
        "evaluatedAt": candidate_report.get("evaluatedAt", utc_now()),
        "datasetId": candidate_report.get("datasetId"),
        "candidateReportEvaluationKind": candidate_report.get("evaluationKind"),
        "gates": gates,
        "fallback": fallback,
        "decision": "PASS" if passed else "HOLD",
        "promotionAllowed": False,
        "containsRawFieldValues": False,
        "groundTruthUsedForScoringOnly": True,
    }


def load_prediction_summary(paths: tuple[Path, Path, Path]) -> dict[str, Any]:
    prediction, report, marker = paths
    artifact = _read_object(prediction)
    if artifact.get("schemaVersion") not in {
        PREDICTION_SCHEMA_VERSION,
        DATA13_PREDICTION_SCHEMA_VERSION,
    }:
        raise PredictionArtifactError("Unsupported external prediction artifact")
    if not report.is_file() or not marker.is_file():
        return {
            "status": "PREDICTION_READY",
            "predictionBlind": True,
            "documentCount": artifact.get("documentCount", 0),
            "reportAvailable": False,
            "promotionAllowed": False,
            "documents": [
                {
                    "caseId": d.get("caseId"),
                    "category": d.get("category"),
                    "sourceFormat": d.get("sourceFormat"),
                    "sourceFile": d.get("sourceFile"),
                    "evaluationIncluded": d.get("evaluationIncluded", True),
                    "ocrScope": (d.get("processing") or {}).get("ocrScope"),
                }
                for d in artifact.get("documents", [])
            ],
        }
    aggregate = _read_object(report)
    marker_payload = _read_object(marker)
    evaluated_status = (
        "DEVELOPMENT_EVALUATED"
        if marker_payload.get("evaluationKind") == "development-aggregate-comparison"
        else "EVALUATED_ONCE"
    )
    return {
        "status": evaluated_status,
        "predictionBlind": False,
        "documentCount": artifact.get("documentCount", 0),
        "reportAvailable": True,
        "promotionAllowed": False,
        "report": aggregate,
        "documents": [
            {
                "caseId": d.get("caseId"),
                "category": d.get("category"),
                "sourceFormat": d.get("sourceFormat"),
                "sourceFile": d.get("sourceFile"),
                "evaluationIncluded": d.get("evaluationIncluded", True),
                "ocrScope": (d.get("processing") or {}).get("ocrScope"),
            }
            for d in artifact.get("documents", [])
        ],
    }


def load_prediction_document(
    paths: tuple[Path, Path, Path], case_id: str, ground_truth_path: Path | None = None
) -> dict[str, Any]:
    artifact = _read_object(paths[0])
    document = next(
        (item for item in artifact.get("documents", []) if item.get("caseId") == case_id), None
    )
    if not isinstance(document, dict):
        raise FileNotFoundError("DATA-12 prediction case not found")
    result: dict[str, Any] = {
        "schemaVersion": "external-dataset-prediction-document/1.0.0",
        "prediction": document,
        "localOnly": True,
        "predictionBlind": True,
    }
    if (
        paths[1].is_file()
        and paths[2].is_file()
        and ground_truth_path is not None
        and ground_truth_path.is_file()
    ):
        ground_truth = _read_object(ground_truth_path)
        case = next(
            (item for item in ground_truth.get("cases", []) if item.get("caseId") == case_id), None
        )
        if isinstance(case, dict):
            gt = {str(item.get("name")): item.get("value") for item in case.get("fields", [])}
            field_names = list(document.get("fields", {}))
            field_names.extend(name for name in gt if name not in field_names)
            result["comparison"] = {}
            for name in field_names:
                field = document.get("fields", {}).get(name)
                guess = field.get("value") if isinstance(field, dict) else None
                match = _field_match(str(document.get("category", "")), name, gt.get(name), guess)
                if (
                    match["diagnosis"] == "OCR_NOT_RECOGNIZED"
                    and not (document.get("processing") or {}).get("usesOcr")
                ):
                    match["diagnosis"] = "PARSER_MISSED"
                result["comparison"][name] = {
                    "groundTruth": gt.get(name),
                    "prediction": guess,
                    **match,
                }
            result["predictionBlind"] = False
    return result
