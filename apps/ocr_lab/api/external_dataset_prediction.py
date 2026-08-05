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
    from .phase15_idp import classify_phase15_document, extract_phase15_document
except ImportError:  # Direct script execution used by the local OCR runner.
    from external_dataset_review import (
        ALLOWED_SUFFIXES,
        FIELD_SPECS,
        OUT_OF_SCOPE_REVIEW_FORMATS,
    )
    from phase12_ingestion import ingest_document, ingest_image
    from phase15_idp import classify_phase15_document, extract_phase15_document

PREDICTION_SCHEMA_VERSION = "external-dataset-predictions/1.0.0"
DATA13_PREDICTION_SCHEMA_VERSION = "external-dataset-predictions/data13/1.0.0"
REPORT_SCHEMA_VERSION = "external-dataset-data12-aggregate/1.0.0"
DATA13_REPORT_SCHEMA_VERSION = "external-dataset-data13-aggregate/1.0.0"
ACTIVE_CATEGORIES = frozenset(FIELD_SPECS)


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


def _lines(text: str) -> list[str]:
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _field(
    value: str | None,
    *,
    method: str,
    block: dict[str, Any] | None,
    review: bool,
) -> dict[str, Any]:
    value = " ".join(value.split()).strip() if isinstance(value, str) and value.strip() else None
    evidence = block.get("evidence") if block else None
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
        "method": method,
    }


def _find_line(lines: list[str], *markers: str) -> tuple[str | None, dict[str, Any] | None]:
    folded = tuple(_fold(marker) for marker in markers)
    for line in lines:
        key = _fold(line)
        marker = next((item for item in folded if item in key), None)
        if marker is None:
            continue
        tail = re.split(r"[:\-]\s*", line, maxsplit=1)
        value = tail[1] if len(tail) == 2 else line[key.find(marker) + len(marker) :]
        return value.strip(" .;"), None
    return None, None


def _regex_line(lines: list[str], pattern: str) -> str | None:
    expression = re.compile(pattern, re.IGNORECASE)
    for line in lines:
        match = expression.search(_fold(line))
        if match:
            # Fold preserves character count for Vietnamese accents and đ.
            return line[match.start(1) : match.end(1)].strip(" .;:")
    return None


def _section(lines: list[str], heading: str, stops: tuple[str, ...]) -> str | None:
    start = next((i for i, line in enumerate(lines) if heading in _fold(line)), None)
    if start is None:
        return None
    stop_keys = tuple(_fold(item) for item in stops)
    values: list[str] = []
    for line in lines[start + 1 :]:
        if any(marker in _fold(line) for marker in stop_keys):
            break
        values.append(line)
    return "\n".join(values).strip() or None


def _date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", value)
    return (
        f"{int(match.group(1)):02d}/{int(match.group(2)):02d}/{match.group(3)}"
        if match
        else value.strip()
    )


def _external_fields(
    category: str,
    canonical: dict[str, Any],
    extraction: dict[str, Any],
    *,
    ocr: bool,
) -> dict[str, dict[str, Any]]:
    lines = _lines(canonical.get("plainText", ""))
    phase_fields = extraction.get("fields", {})

    def direct(name: str, aliases: tuple[str, ...] = ()) -> dict[str, Any]:
        for candidate in (name, *aliases):
            item = phase_fields.get(candidate)
            if isinstance(item, dict) and item.get("value") is not None:
                return _field(
                    str(item["value"]),
                    method="phase15_alias",
                    block=item.get("evidence"),
                    review=ocr,
                )
        return _field(None, method="phase15_alias", block=None, review=ocr)

    if category == "cv":
        name = direct("fullName")
        if name["value"] is None and lines:
            name = _field(lines[0], method="top_line", block=None, review=ocr)
        headline = direct("headline")
        if headline["value"] is None and len(lines) > 1:
            headline = _field(lines[1], method="top_line", block=None, review=ocr)
        email = direct("email")
        if email["value"] is None:
            email = _field(
                _regex_line(lines, r"([\w.+-]+@[\w.-]+\.[a-z]{2,})"),
                method="email_pattern",
                block=None,
                review=ocr,
            )
        phone = direct("phoneNumber")
        if phone["value"] is None:
            phone = _field(
                _regex_line(lines, r"(0\d{8,10})"), method="phone_pattern", block=None, review=ocr
            )
        address = direct("address")
        if address["value"] is None:
            value, _ = _find_line(lines, "địa chỉ", "address")
            address = _field(value, method="address_label", block=None, review=ocr)
        education = direct("education")
        if education["value"] is None:
            education = _field(
                _section(lines, "học vấn", ("kinh nghiệm", "kỹ năng")),
                method="section",
                block=None,
                review=ocr,
            )
        experience = direct("experience")
        if experience["value"] is None:
            experience = _field(
                _section(lines, "kinh nghiệm", ("kỹ năng", "chứng chỉ")),
                method="section",
                block=None,
                review=ocr,
            )
        skills = direct("skills")
        if skills["value"] is None:
            skills = _field(
                _section(lines, "kỹ năng", ("chứng chỉ", "giải thưởng", "hoạt động")),
                method="section",
                block=None,
                review=ocr,
            )
        desired = _field(
            _regex_line(lines, r"trở thành\s+(.+)$"),
            method="desired_role_pattern",
            block=None,
            review=ocr,
        )
        years = _field(
            _regex_line(lines, r"((?:hơn|trên|ít nhất)\s+\d+\s+năm)"),
            method="years_experience_pattern",
            block=None,
            review=ocr,
        )
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

        def line(*markers: str, method: str = "label") -> dict[str, Any]:
            value, _ = _find_line(lines, *markers)
            return _field(value, method=method, block=None, review=ocr)

        contract_number = _field(
            _regex_line(lines, r"(?:số|so)\s*[:\-]?\s*([a-z0-9./-]{5,})"),
            method="contract_number_pattern",
            block=None,
            review=ocr,
        )
        sign_date = _field(
            _regex_line(
                lines, r"(?:ngày ký|ngay ky|ngày)\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4})"
            ),
            method="sign_date_pattern",
            block=None,
            review=ocr,
        )
        effective = _field(
            _regex_line(
                lines,
                r"(?:hiệu lực từ|hieu luc tu|bắt đầu từ|bat dau tu)\s*"
                r"(?:ngày|ngay)?\s*[:\-]?\s*"
                r"(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
            ),
            method="effective_date_pattern",
            block=None,
            review=ocr,
        )
        probation_end = _field(
            _regex_line(
                lines,
                r"(?:kết thúc thử việc|ket thuc thu viec|hết hạn thử việc)\s*"
                r"[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
            ),
            method="probation_end_pattern",
            block=None,
            review=ocr,
        )
        employer = line("đại diện cho", "cong ty", method="employer_label")
        representative = line("đại diện", "dai dien", method="representative_label")
        employee = line("ông/bà", "ong/ba", method="employee_label")
        employee_id = _field(
            _regex_line(lines, r"(?:cccd số|cccd so|cmnd số|cmnd so)\s*[:\-]?\s*([0-9]{9,12})"),
            method="employee_id_pattern",
            block=None,
            review=ocr,
        )
        job = line("công việc/chức danh", "chức danh", "vi tri cong viec", method="job_title_label")
        workplace = line("địa điểm làm việc", "dia diem lam viec", method="workplace_label")
        weekly = _field(
            _regex_line(lines, r"(\d{1,3}\s*giờ\s*/\s*tuần|\d{1,3}\s*gio\s*/\s*tuan)"),
            method="weekly_hours_pattern",
            block=None,
            review=ocr,
        )
        salary = line(
            "mức lương thử việc", "muc luong thu viec", "lương thử việc", method="salary_label"
        )
        allowances = line("phụ cấp", "phu cap", method="allowances_label")
        payment = line("thanh toán", "thanh toan", "trả lương", method="payment_label")
        for item in (sign_date, effective, probation_end):
            item["value"] = _date(item["value"])
            item["normalizedValue"] = item["value"]
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

    credential = _field(
        _regex_line(lines, r"(ielts\s+(?:academic|general training))"),
        method="credential_type_pattern",
        block=None,
        review=ocr,
    )
    recipient = _field(
        _regex_line(lines, r"(?:candidate name|recipient|họ và tên|ho va ten)\s*[:\-]?\s*(.+)$"),
        method="recipient_label",
        block=None,
        review=ocr,
    )
    if recipient["value"] is None:
        recipient = _field(
            next((line for line in lines if re.fullmatch(r"[A-Z][A-Z .'-]{5,}", line)), None),
            method="uppercase_name_candidate",
            block=None,
            review=ocr,
        )
    credential_id = _field(
        _regex_line(
            lines,
            r"(?:trf no|test report form|candidate number|credential id|id)\s*"
            r"[:\-]?\s*([a-z0-9-]{6,})",
        ),
        method="credential_id_pattern",
        block=None,
        review=ocr,
    )
    score = _field(
        _regex_line(lines, r"(?:overall(?: band)?(?: score)?|overall)\s*[:\-]?\s*(\d(?:\.\d)?)"),
        method="overall_score_pattern",
        block=None,
        review=ocr,
    )
    issue = _field(
        _regex_line(
            lines,
            r"(?:issue date|test date|date of issue|ngày cấp|ngay cap)\s*"
            r"[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        ),
        method="issue_date_pattern",
        block=None,
        review=ocr,
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
        if data13_scope and scan_input and category != "ielts":
            fields = {
                name: _field(
                    None,
                    method="ocr_disabled_by_policy",
                    block=None,
                    review=False,
                )
                for name in FIELD_SPECS[category]
            }
            documents.append(
                {
                    "caseId": record["caseId"],
                    "category": category,
                    "sourceFormat": source_format,
                    "sourceFile": source.name,
                    "sourceSha256": record.get("sourceSha256"),
                    "predictedCategory": None,
                    "classification": {},
                    "fields": fields,
                    "evaluationIncluded": False,
                    "processing": {
                        "usesOcr": False,
                        "ocrEngine": None,
                        "ocrScope": "UNSUPPORTED_NO_OCR",
                        "recommendedAction": "REJECT_UNSUPPORTED",
                        "reason": "OCR_DISABLED_BY_POLICY",
                    },
                }
            )
            continue
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
                    "ocrEngine": "paddleocr/latin_pp-ocrv5" if ocr_required else None,
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
        "ocrScopePolicy": ("cccd-and-certificate-only" if scope_policy == "data13" else "legacy"),
        "documents": documents,
    }


def _norm(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split())


def build_aggregate_report(
    prediction: dict[str, Any], ground_truth: dict[str, Any], *, evaluated_at: str | None = None
) -> dict[str, Any]:
    data13_scope = prediction.get("ocrScopePolicy") == "cccd-and-certificate-only"
    report_schema = DATA13_REPORT_SCHEMA_VERSION if data13_scope else REPORT_SCHEMA_VERSION
    gt_by_id = {str(case.get("caseId")): case for case in ground_truth.get("cases", [])}
    exact = 0
    present = 0
    field_count = 0
    schema_errors = 0
    classification_matches = 0
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
        manual_review += int(processing.get("recommendedAction") == "MANUAL_REVIEW")
        false_auto += int(
            processing.get("usesOcr") and processing.get("recommendedAction") == "AUTO_CONTINUE"
        )
        stats = by_category.setdefault(category, {"fields": 0, "exact": 0, "present": 0})
        for name in expected:
            field_count += 1
            stats["fields"] += 1
            truth = gt_fields.get(name, {}).get("value")
            guess = (
                predicted_fields.get(name, {}).get("value")
                if isinstance(predicted_fields.get(name), dict)
                else None
            )
            truth_norm, guess_norm = _norm(truth), _norm(guess)
            exact += int(truth_norm == guess_norm)
            stats["exact"] += int(truth_norm == guess_norm)
            if guess_norm:
                present += 1
                stats["present"] += 1
            if truth_norm and not guess_norm:
                reason = "OCR_NOT_RECOGNIZED" if processing.get("usesOcr") else "PARSER_MISSED"
                diagnoses[reason] = diagnoses.get(reason, 0) + 1
            elif truth_norm and guess_norm and truth_norm != guess_norm:
                diagnoses["OCR_RECOGNIZED_PARSER_MISSED"] = (
                    diagnoses.get("OCR_RECOGNIZED_PARSER_MISSED", 0) + 1
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
            "fieldPresenceCount": present,
            "fieldPresenceRate": round(present / max(1, field_count), 6),
        },
        "byCategory": by_category,
        "diagnosisCounts": diagnoses,
        "schemaErrors": schema_errors,
        "ocrPolicy": {
            "manualReviewCount": manual_review,
            "falseAutoContinueCount": false_auto,
            "ocrAlwaysManualReview": false_auto == 0,
            "unsupportedNoOcrCount": excluded_documents,
            "scopePolicy": prediction.get("ocrScopePolicy", "legacy"),
        },
        "decision": "HOLD",
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
    return {
        "status": "EVALUATED_ONCE",
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
            result["comparison"] = {
                name: {
                    "groundTruth": gt.get(name),
                    "prediction": (field or {}).get("value") if isinstance(field, dict) else None,
                    "exact": _norm(gt.get(name))
                    == _norm((field or {}).get("value") if isinstance(field, dict) else None),
                }
                for name, field in document.get("fields", {}).items()
            }
            result["predictionBlind"] = False
    return result
