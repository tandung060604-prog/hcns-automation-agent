"""Front-side Vietnam citizen ID (CCCD) field extraction from noisy OCR."""

from __future__ import annotations

import re
import unicodedata

from hcns_agent.domain.canonical import CanonicalDocument
from hcns_agent.templates.common import document_text, normalize_for_ocr_match
from hcns_agent.templates.model import ParsedTemplate, TemplateDetection

_ID_RE = re.compile(r"\b(\d{9}|\d{12})\b")
_DATE_RE = re.compile(r"\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})\b")
_NAME_RE = re.compile(
    r"^[A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ]"
    r"[A-ZÀ-ỴĐ\s'.-]{3,80}$"
)


def _fold(value: str) -> str:
    return normalize_for_ocr_match(value)


def _clean_line(line: str) -> str:
    return unicodedata.normalize("NFC", line).strip(" :\t.-")


def _is_noise(line: str) -> bool:
    folded = _fold(line)
    if not folded or len(folded) <= 2:
        return True
    if folded in {"a", "e", "i", "o", "u", "x", "s", "d", "l", "wa", "hon", "ith", "un"}:
        return True
    if re.fullmatch(r"[\d\W_]+", folded):
        return True
    letters = sum(ch.isalpha() for ch in folded)
    return letters < max(2, len(folded) // 3)


_HEADER_NOISE = (
    "viet nam",
    "cong hoa",
    "socialist",
    "republic",
    "independence",
    "freedom",
    "happiness",
    "identity card",
    "citzen",
    "can cuoc",
    "cn cuc",
)


def _looks_like_person_name(line: str) -> bool:
    cleaned = _clean_line(line)
    if len(cleaned) < 4 or _is_noise(cleaned):
        return False
    folded = _fold(cleaned)
    if any(token in folded for token in _HEADER_NOISE):
        return False
    words = [w for w in cleaned.split() if w]
    if len(words) < 2 or len(words) > 6:
        return False
    # Prefer ALL-CAPS Vietnamese names printed on CCCD.
    if _NAME_RE.match(cleaned.upper()):
        return True
    alpha_ratio = sum(ch.isalpha() or ch.isspace() for ch in cleaned) / max(len(cleaned), 1)
    return alpha_ratio >= 0.7 and not any(ch.isdigit() for ch in cleaned)


def _value_after_labels(
    lines: list[str], labels: tuple[str, ...], *, max_lookahead: int = 8
) -> str | None:
    label_folds = tuple(_fold(label) for label in labels)
    for index, raw in enumerate(lines):
        folded = _fold(raw)
        if not any(label in folded for label in label_folds):
            continue
        # Same-line value after colon / slash separator.
        for sep in (":", "/"):
            if sep in raw:
                right = _clean_line(raw.split(sep, 1)[1])
                # Drop English residual after bilingual labels.
                for cut in ("date of", "place of", "full name", "ful name", "sex", "nationality"):
                    cut_at = _fold(right).find(_fold(cut))
                    if cut_at > 0:
                        right = _clean_line(right[:cut_at])
                if (
                    right
                    and not _is_noise(right)
                    and not any(_fold(label) in _fold(right) for label in labels)
                ):
                    date = _DATE_RE.search(right)
                    if date and any(
                        "sinh" in label or "birth" in label or "bith" in label
                        for label in label_folds
                    ):
                        return date.group(1)
                    if not any(label in _fold(right) for label in label_folds):
                        return right
        for offset in range(1, max_lookahead + 1):
            if index + offset >= len(lines):
                break
            candidate = _clean_line(lines[index + offset])
            if not candidate or _is_noise(candidate):
                continue
            if any(label in _fold(candidate) for label in label_folds):
                continue
            return candidate
    return None


class CitizenIdFrontParser:
    version = "1.1.0"

    def parse(
        self,
        document: CanonicalDocument,
        detection: TemplateDetection,
    ) -> ParsedTemplate:
        lines = [
            _clean_line(line)
            for line in document_text(document).splitlines()
            if _clean_line(line)
        ]
        joined = "\n".join(lines)
        id_match = _ID_RE.search(joined)
        date_match = None
        for line in lines:
            if "sinh" in _fold(line) or "birth" in _fold(line) or "bith" in _fold(line):
                date_match = _DATE_RE.search(line)
                if date_match:
                    break
        if date_match is None:
            date_match = _DATE_RE.search(joined)

        full_name = None
        for index, raw in enumerate(lines):
            folded = _fold(raw)
            if not any(token in folded for token in ("ho va ten", "full name", "ful name")):
                continue
            for offset in range(1, 10):
                if index + offset >= len(lines):
                    break
                candidate = _clean_line(lines[index + offset])
                if _looks_like_person_name(candidate):
                    full_name = candidate
                    break
            break
        if full_name is None:
            for line in lines:
                if _looks_like_person_name(line) and line.isupper():
                    full_name = line
                    break

        sex = _value_after_labels(lines, ("gioi tinh", "sex", "giới tính"))
        if sex:
            folded_sex = _fold(sex)
            if "nam" in folded_sex:
                sex = "Nam"
            elif "nu" in folded_sex or "nữ" in sex.casefold():
                sex = "Nữ"

        data: dict[str, object] = {
            "documentId": document.document_id,
            "documentType": detection.definition.document_type.value,
            "templateId": detection.definition.template_id,
            "templateVersion": detection.definition.version,
            "sourceFile": document.source.filename,
            "idNumber": id_match.group(1) if id_match else None,
            "fullName": full_name,
            "dateOfBirth": date_match.group(1) if date_match else None,
            "sex": sex,
            "nationality": _value_after_labels(lines, ("quoc tich", "nationality", "quốc tịch")),
            "placeOfOrigin": _value_after_labels(
                lines, ("que quan", "place of origin", "quê quán")
            ),
            "placeOfResidence": None,
        }
        residence = _value_after_labels(
            lines,
            (
                "noi thuong tru",
                "place of residence",
                "nơi thường trú",
                "pce rsidence",
                "rsidence",
            ),
        )
        if residence:
            folded_res = _fold(residence)
            if not any(
                token in folded_res
                for token in ("expir", "het han", "tiden", "date of", "place of")
            ):
                data["placeOfResidence"] = residence
        origin = data.get("placeOfOrigin")
        if isinstance(origin, str) and (
            "place of" in _fold(origin) or _is_noise(origin)
        ):
            data["placeOfOrigin"] = None
        return ParsedTemplate(data=data)
