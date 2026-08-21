"""Classify PDF-001C Contract scan mismatches without writing raw evidence.

All source, OCR and Ground Truth values are read from an explicitly authorized
private root. The output is aggregate-only and contains field names, parser
methods and category counts, never document identifiers, paths or values.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "ocr_lab" / "api"))

from external_dataset_prediction import (  # noqa: E402
    FIELD_SPECS,
    MATCHING_POLICY_V2,
    _field_match,
)

from hcns_agent.adapters.easyocr import EASYOCR_TEXT_REPAIR_PROFILE  # noqa: E402
from hcns_agent.adapters.external_dataset import count_source_format_and_pages  # noqa: E402
from hcns_agent.application.external_dataset import (  # noqa: E402
    read_inventory,
    validate_inventory,
)
from hcns_agent.domain.content import iter_text_observations  # noqa: E402
from hcns_agent.ports.document_parser import DocumentSource  # noqa: E402
from hcns_agent.templates.service import (  # noqa: E402
    build_local_template_processing_service,
)
from hcns_agent.templates.structured_hr import (  # noqa: E402
    STRUCTURED_HR_PARSER_VERSION,
    _legacy_document,
    extract_structured_hr_fields,
)

SCHEMA_VERSION = "pdf001g-job-title-schema-replay/1.0.0"
PARSER_VERSION = STRUCTURED_HR_PARSER_VERSION
JOB_TITLE_POLICY = (
    "professional_title_and_role_title; job_title_maps_to_role_title"
)
CATEGORIES = (
    "OCR_RECOGNITION",
    "PARSER_BOUNDARY",
    "NORMALIZATION",
    "GROUND_TRUTH_REVIEW",
)
_FIELD_LABELS = {
    "employee_id_number": ("CCCD số", "CCCD sỗ", "CCCD sõ", "CMND số", "Employee ID"),
    "employee_name": ("Ông/bà", "ÔngJBà", "Họ và tên", "Người lao động", "Bên B"),
    "employer_name": ("Đại diện cho", "Tên công ty", "Employer"),
    "employer_representative": ("Đại diện:", "Đại diện bởi"),
    "job_title": ("Chức vụ/Vị trí", "Chức danh chuyên môn", "Công việc/Chức danh", "Job Title"),
    "probation_salary_monthly": ("Mức lương thử việc", "Lương thử việc", "Salary"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorization-confirmed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--easyocr-decoder",
        choices=("greedy", "beamsearch"),
        default="greedy",
    )
    parser.add_argument(
        "--easyocr-language-profile",
        choices=("vi", "vi-en"),
        default="vi",
    )
    parser.add_argument(
        "--easyocr-preprocess-profile",
        choices=("none", "content-roi-autocontrast-v1"),
        default="none",
    )
    parser.add_argument("--expected-strict-mismatches", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.authorization_confirmed:
        raise SystemExit("Analysis rejected: pass --authorization-confirmed")

    dataset_root = _private_existing(args.dataset_root)
    inventory_path = _private_existing(args.inventory)
    ground_truth_path = _private_existing(args.ground_truth)
    output_path = _private_output(args.output)
    if output_path.exists() and not args.overwrite:
        raise SystemExit("Analysis report exists; pass --overwrite")

    inventory = read_inventory(inventory_path)
    validate_inventory(
        dataset_root,
        inventory,
        page_counter=count_source_format_and_pages,
    )
    ground_truth = _read_object(ground_truth_path)
    _validate_ground_truth(ground_truth)

    inventory_cases = {
        str(case["caseId"]): case
        for case in _object_list(inventory, "cases")
        if case.get("sourceFormat") == "PDF_SCAN"
    }
    truth_cases = {
        str(case["caseId"]): case for case in _object_list(ground_truth, "cases")
    }
    if set(inventory_cases) != set(truth_cases):
        raise SystemExit("PDF-001C inventory and Ground Truth case sets differ")

    service = build_local_template_processing_service(
        ocr_backend="easyocr",
        pdf_dpi=150,
        easyocr_canvas_size=1280,
        easyocr_mag_ratio=1.3,
        easyocr_preprocess_profile=args.easyocr_preprocess_profile,
        easyocr_decoder=args.easyocr_decoder,
        easyocr_language_profile=args.easyocr_language_profile,
    )
    service.warm_up_ocr()
    report = _analyze_cases(
        dataset_root,
        inventory_cases,
        truth_cases,
        service,
        easyocr_decoder=args.easyocr_decoder,
        easyocr_language_profile=args.easyocr_language_profile,
        easyocr_preprocess_profile=args.easyocr_preprocess_profile,
        expected_strict_mismatches=args.expected_strict_mismatches,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


def _analyze_cases(
    dataset_root: Path,
    inventory_cases: Mapping[str, dict[str, Any]],
    truth_cases: Mapping[str, dict[str, Any]],
    service: Any,
    *,
    easyocr_decoder: str,
    easyocr_language_profile: str,
    easyocr_preprocess_profile: str,
    expected_strict_mismatches: int | None = None,
) -> dict[str, Any]:
    field_names = tuple(FIELD_SPECS["contract"])
    category_counts = Counter({category: 0 for category in CATEGORIES})
    by_field: dict[str, Counter[str]] = defaultdict(Counter)
    method_counts: Counter[str] = Counter()
    diagnosis_counts: Counter[str] = Counter()
    match_type_counts: Counter[str] = Counter()
    accepted_partial_over_extraction = 0
    accepted_partial_full_token_coverage = 0
    raw_evidence_counts = Counter({"located": 0, "notLocated": 0})
    strict_exact = 0
    accepted = 0
    present = 0
    field_count = 0

    for case_id in sorted(inventory_cases):
        inventory_case = inventory_cases[case_id]
        truth_case = truth_cases[case_id]
        relative = Path(str(inventory_case["sourceRelativePath"]))
        source_path = (dataset_root / relative).resolve(strict=True)
        source = DocumentSource(
            document_id=f"alg004-{case_id}",
            filename=source_path.name,
            content=source_path.read_bytes(),
            source_reference=f"alg004-{case_id}",
        )
        canonical = service._intake.execute(source)
        detection = service._registry.detect(canonical)
        if detection is None:
            raise SystemExit("Template detection failed for an authorized scan")
        parsed = detection.definition.parser.parse(canonical, detection)
        extracted = extract_structured_hr_fields(
            _legacy_document(canonical),
            "contract",
            ocr=True,
        )
        blocks = [
            block
            for page in _legacy_document(canonical)["pages"]
            for block in page["blocks"]
        ]
        raw_text = "\n".join(
            observation.text for observation in iter_text_observations(canonical)
        )
        truth = {
            str(field["name"]): field.get("value")
            for field in _object_list(truth_case, "fields")
        }
        for name in field_names:
            field_count += 1
            truth_value = truth.get(name)
            guess = parsed.data.get(name)
            if guess not in (None, ""):
                present += 1
            match = _field_match(
                "contract",
                name,
                truth_value,
                guess,
                policy_version=MATCHING_POLICY_V2,
            )
            strict_exact += int(bool(match["exact"]))
            accepted += int(bool(match["match"]))
            if match["exact"]:
                continue

            detail = extracted.get(name, {})
            method = str(detail.get("method") or "unknown")
            diagnosis = str(match.get("diagnosis") or "none")
            method_counts[method] += 1
            diagnosis_counts[diagnosis] += 1
            match_type = str(match.get("matchType") or "unknown")
            match_type_counts[match_type] += 1
            if match.get("matchType") == "ACCEPTED_PARTIAL":
                if bool(match.get("overExtraction")):
                    accepted_partial_over_extraction += 1
                if float(match.get("groundTruthTokenCoverage") or 0.0) >= 1.0:
                    accepted_partial_full_token_coverage += 1
            scoped_ocr = _field_ocr_text(name, blocks) or raw_text
            raw_present = _value_present_in_ocr(truth_value, scoped_ocr)
            prediction_present = _value_present_in_ocr(guess, scoped_ocr)
            raw_evidence_counts["located" if raw_present else "notLocated"] += 1
            category = _classify_mismatch(
                match=match,
                truth_value=truth_value,
                raw_present=raw_present,
                prediction_present=prediction_present,
                competing_candidates=_has_competing_job_title_labels(name, blocks),
                ground_truth_confirmed=True,
            )
            category_counts[category] += 1
            by_field[name][category] += 1

    mismatch_count = sum(category_counts.values())
    if mismatch_count != field_count - strict_exact:
        raise SystemExit("ALG-004 mismatch accounting is inconsistent")
    if (
        expected_strict_mismatches is not None
        and mismatch_count != expected_strict_mismatches
    ):
        raise SystemExit(
            f"Expected {expected_strict_mismatches} strict mismatches, got {mismatch_count}"
        )
    if category_counts["GROUND_TRUTH_REVIEW"]:
        raise SystemExit("Confirmed Ground Truth unexpectedly entered review category")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "datasetId": "PDF-001C",
        "scope": {
            "sourceFormat": "PDF_SCAN",
            "documents": len(inventory_cases),
            "fields": field_count,
            "strictMismatchCount": mismatch_count,
        },
        "runtime": {
            "profile": "template-first",
            "ocrBackend": "easyocr",
            "ocrProfile": f"easyocr/{easyocr_language_profile}-{easyocr_decoder}",
            "preprocessProfile": easyocr_preprocess_profile,
            "pdfDpi": 150,
            "easyocrCanvasSize": 1280,
            "easyocrMagRatio": 1.3,
            "parserVersion": PARSER_VERSION,
            "matchingPolicy": MATCHING_POLICY_V2,
            "jobTitlePolicy": JOB_TITLE_POLICY,
            "easyocrDecoder": easyocr_decoder,
            "easyocrLanguageProfile": easyocr_language_profile,
            "easyocrTextRepairProfile": EASYOCR_TEXT_REPAIR_PROFILE,
        },
        "metrics": {
            "present": present,
            "strictExact": strict_exact,
            "accepted": accepted,
            "technicalErrors": 0,
            "manualReviewDocuments": len(inventory_cases),
        },
        "classification": {
            "counts": dict(category_counts),
            "byField": {
                name: dict(sorted(counts.items()))
                for name, counts in sorted(by_field.items())
            },
            "parserMethodCounts": dict(sorted(method_counts.items())),
            "matchingDiagnosisCounts": dict(sorted(diagnosis_counts.items())),
            "matchingOutcomeCounts": dict(sorted(match_type_counts.items())),
            "acceptedPartial": {
                "overExtractionCount": accepted_partial_over_extraction,
                "fullGroundTruthTokenCoverageCount": accepted_partial_full_token_coverage,
            },
            "groundTruthReview": {
                "status": "CONFIRMED",
                "count": category_counts["GROUND_TRUTH_REVIEW"],
            },
            "ocrEvidence": dict(raw_evidence_counts),
        },
        "policy": {
            "aggregateOnly": True,
            "containsDocumentIds": False,
            "containsSourcePaths": False,
            "containsRawFieldValues": False,
            "containsRawOcrText": False,
            "promotionAllowed": False,
        },
    }


def _classify_mismatch(
    *,
    match: Mapping[str, Any],
    truth_value: Any,
    raw_present: bool,
    ground_truth_confirmed: bool,
    prediction_present: bool = False,
    competing_candidates: bool = False,
) -> str:
    if not ground_truth_confirmed:
        return "GROUND_TRUTH_REVIEW"
    if bool(match.get("match")):
        return "NORMALIZATION"
    if raw_present and (not prediction_present or competing_candidates):
        return "PARSER_BOUNDARY"
    return "OCR_RECOGNITION"


def _has_competing_job_title_labels(name: str, blocks: list[dict[str, Any]]) -> bool:
    if name != "job_title":
        return False
    text = "\n".join(str(block.get("text") or "") for block in blocks)
    compact_text = _compact_ocr_text(text)
    return (
        "chucdanhchuyenmon" in compact_text
        and "chucvuvitri" in compact_text
    )


def _value_present_in_ocr(value: Any, raw_text: str) -> bool:
    if value in (None, ""):
        return False
    expected = _compact_ocr_text(str(value))
    observed = _compact_ocr_text(raw_text)
    return bool(expected) and expected in observed


def _field_ocr_text(name: str, blocks: list[dict[str, Any]]) -> str:
    labels = _FIELD_LABELS.get(name)
    if not labels:
        return ""
    selected: list[str] = []
    compact_labels = tuple(_compact_ocr_text(label) for label in labels)
    for index, block in enumerate(blocks):
        text = str(block.get("text") or "")
        compact_text = _compact_ocr_text(text)
        if not any(label and label in compact_text for label in compact_labels):
            continue
        selected.append(text)
        if ":" not in text and index + 1 < len(blocks):
            selected.append(str(blocks[index + 1].get("text") or ""))
    return "\n".join(selected)


def _compact_ocr_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value).casefold()
    plain = "".join(
        "d" if character == "đ" else character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "", plain)


def _validate_ground_truth(payload: dict[str, Any]) -> None:
    review = payload.get("review")
    if not isinstance(review, dict):
        raise SystemExit("Ground Truth review metadata is invalid")
    if review.get("status") != "CONFIRMED" or review.get("predictionBlindness") is not True:
        raise SystemExit("Ground Truth must be confirmed and prediction-blind")
    dataset = payload.get("dataset")
    if not isinstance(dataset, dict) or dataset.get("datasetId") != "PDF-001C":
        raise SystemExit("Ground Truth dataset is not PDF-001C")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("Private JSON artifact is unreadable") from error
    if not isinstance(payload, dict):
        raise SystemExit("Private JSON artifact must be an object")
    return payload


def _object_list(payload: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SystemExit(f"Private artifact field is invalid: {key}")
    return value


def _private_existing(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if _inside_git(resolved):
        raise SystemExit("Private input must stay outside Git")
    if not resolved.is_file() and resolved.suffix:
        raise SystemExit("Private input file is missing")
    return resolved


def _private_output(path: Path) -> Path:
    resolved = path.resolve()
    if _inside_git(resolved):
        raise SystemExit("Private output must stay outside Git")
    return resolved


def _inside_git(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


if __name__ == "__main__":
    raise SystemExit(main())
