#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""User-reviewed ground truth, OCR evaluation, and verified Business JSON pilot."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from phase11_cccd import (
    FIELD_ORDER,
    evaluate_field_predictions,
    extract_cccd_fields,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def edit_distance(reference: Sequence[Any], hypothesis: Sequence[Any]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, ref_item in enumerate(reference, start=1):
        current = [row]
        for column, hyp_item in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (ref_item != hyp_item),
                )
            )
        previous = current
    return previous[-1]


def metrics(reference: str, hypothesis: str) -> dict[str, float | bool]:
    ref = normalize(reference)
    hyp = normalize(hypothesis)
    ref_words = ref.split()
    hyp_words = hyp.split()
    return {
        "cer": round(edit_distance(list(ref), list(hyp)) / max(1, len(ref)), 6),
        "wer": round(edit_distance(ref_words, hyp_words) / max(1, len(ref_words)), 6),
        "exactMatch": ref == hyp,
    }


def _page_texts(
    result: dict[str, Any], session_dir: Path | None = None
) -> dict[str, list[str]]:
    raw_pages = (
        result.get("phase9", {}).get("rawOcr", {}).get("pages")
        or result.get("document", {}).get("pages", [])
    )
    phase9_pages = result.get("phase9", {}).get("pages", [])
    output = {
        "phase8Raw": [
            "\n".join(page.get("recognizedTexts", [])) for page in raw_pages
        ],
        "phase9Selected": [
            page.get("rawText", "") for page in phase9_pages
        ],
        "phase9Corrected": [
            page.get("correctedText", "") for page in phase9_pages
        ],
    }
    challenger_path = session_dir / "phase10" / "easyocr.json" if session_dir else None
    if challenger_path and challenger_path.is_file():
        challenger = json.loads(challenger_path.read_text(encoding="utf-8"))
        output["easyocrChallenger"] = [
            page.get("recognizedText", "")
            for page in challenger.get("document", {}).get("pages", [])
        ]
    return output


def review_payload(session_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    phase10_dir = session_dir / "phase10"
    ground_truth_path = phase10_dir / "ground_truth.json"
    evaluation_path = phase10_dir / "evaluation.json"
    business_path = phase10_dir / "business.json"
    page_texts = _page_texts(result, session_dir)
    draft_pages = [
        {"pageIndex": index, "text": text}
        for index, text in enumerate(
            page_texts["phase9Corrected"]
            or page_texts["phase9Selected"]
            or page_texts["phase8Raw"]
        )
    ]
    ground_truth = (
        json.loads(ground_truth_path.read_text(encoding="utf-8"))
        if ground_truth_path.is_file()
        else None
    )
    assertions = ground_truth.get("verificationAssertions", {}) if ground_truth else {}
    reviewed = bool(
        ground_truth
        and assertions.get("comparedWithImage")
        and assertions.get("allTextChecked")
    )
    challenger_path = phase10_dir / "easyocr.json"
    challenger = (
        json.loads(challenger_path.read_text(encoding="utf-8"))
        if challenger_path.is_file()
        else None
    )
    controlled_pilot_path = (
        session_dir / "phase14_2" / "controlled_pilot.json"
    )
    hybrid_path = (
        controlled_pilot_path
        if controlled_pilot_path.is_file()
        else session_dir / "phase13_3" / "hybrid_ocr.json"
    )
    hybrid = (
        json.loads(hybrid_path.read_text(encoding="utf-8"))
        if hybrid_path.is_file()
        else None
    )
    identity_card = result.get("phase11", {}).get("identityCard") or {}
    identity_field_draft = {
        field_name: str(
            identity_card.get("fields", {})
            .get(field_name, {})
            .get("value")
            or ""
        )
        for field_name in FIELD_ORDER
    }
    return {
        "reviewed": reviewed,
        "reviewStatus": (
            "USER_REVIEWED"
            if reviewed
            else "NEEDS_RECONFIRMATION"
            if ground_truth
            else "DRAFT"
        ),
        "draftPages": draft_pages,
        "groundTruth": ground_truth,
        "identityFieldDraft": identity_field_draft,
        "challenger": (
            {
                "available": True,
                "engine": challenger.get("processing", {}).get("engine"),
                "version": challenger.get("processing", {}).get("version"),
                "avgConfidence": challenger.get("document", {}).get("avgConfidence"),
                "durationMs": challenger.get("processing", {}).get("durationMs"),
                "draftPages": [
                    {
                        "pageIndex": page.get("pageIndex", index),
                        "text": page.get("recognizedText", ""),
                    }
                    for index, page in enumerate(
                        challenger.get("document", {}).get("pages", [])
                    )
                ],
                "identityCard": challenger.get("document", {}).get(
                    "identityCard"
                ),
            }
            if challenger
            else {"available": False}
        ),
        "hybrid": (
            {
                "available": True,
                "phase": "14.2" if hybrid_path == controlled_pilot_path else "13.3",
                "status": hybrid.get("status"),
                "policy": hybrid.get("policy", {}),
                "runtime": hybrid.get("runtime", {}),
                "summary": hybrid.get("summary", {}),
                "pages": hybrid.get("pages", []),
            }
            if hybrid
            else {"available": False}
        ),
        "evaluation": (
            json.loads(evaluation_path.read_text(encoding="utf-8"))
            if reviewed and evaluation_path.is_file()
            else None
        ),
        "businessJson": (
            json.loads(business_path.read_text(encoding="utf-8"))
            if reviewed and business_path.is_file()
            else None
        ),
    }


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(" ".join(value.split()) for value in values))


def verified_fields(text: str) -> dict[str, list[dict[str, Any]]]:
    patterns = {
        "emails": r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "phoneNumbers": r"(?<!\d)(?:\+?84|0)(?:[\s.\-]?\d){8,10}(?!\d)",
        "dates": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        "identityNumbers": r"(?<!\d)\d{12}(?!\d)",
        "employeeCodes": r"\b(?:NV|EMP|MSNV)[\s\-:]?[A-Z0-9]{3,12}\b",
    }
    fields: dict[str, list[dict[str, Any]]] = {}
    for name, pattern in patterns.items():
        flags = re.I if name in {"emails", "employeeCodes"} else 0
        fields[name] = [
            {
                "value": value,
                "verified": True,
                "verificationMethod": "user_reviewed_ground_truth",
            }
            for value in _unique(re.findall(pattern, text, flags))
        ]
    return fields


def save_review(
    session_dir: Path,
    result: dict[str, Any],
    pages: list[dict[str, Any]],
    assertions: dict[str, Any],
    identity_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected_pages = int(result.get("source", {}).get("pageCount", 0))
    if len(pages) != expected_pages:
        raise ValueError("Ground-truth page count does not match the document")
    normalized_pages: list[dict[str, Any]] = []
    for expected_index, page in enumerate(pages):
        page_index = page.get("pageIndex")
        text = page.get("text")
        if page_index != expected_index or not isinstance(text, str):
            raise ValueError("Invalid ground-truth page payload")
        if len(text) > 500_000:
            raise ValueError("Ground-truth page is too large")
        normalized_pages.append({"pageIndex": page_index, "text": text.strip()})
    compared_with_image = assertions.get("comparedWithImage") is True
    all_text_checked = assertions.get("allTextChecked") is True
    if not compared_with_image or not all_text_checked:
        raise ValueError("Image comparison and full-text confirmation are required")
    draft_reference = "\n".join(
        _page_texts(result, session_dir).get("phase9Corrected", [])
    )
    submitted_reference = "\n".join(page["text"] for page in normalized_pages)
    unchanged_from_draft = normalize(draft_reference) == normalize(submitted_reference)
    if unchanged_from_draft and assertions.get("acceptUnchangedDraft") is not True:
        raise ValueError(
            "Ground truth is unchanged from the OCR draft; explicitly confirm it is exact"
        )
    normalized_identity_fields: dict[str, str] = {}
    if identity_fields is not None:
        if not isinstance(identity_fields, dict):
            raise ValueError("identityFields must be an object")
        unknown_fields = set(identity_fields) - set(FIELD_ORDER)
        if unknown_fields:
            raise ValueError("identityFields contains unsupported fields")
        for field_name in FIELD_ORDER:
            value = identity_fields.get(field_name, "")
            if not isinstance(value, str):
                raise ValueError("Every identity field must be text")
            normalized_value = " ".join(value.split()).strip()
            if len(normalized_value) > 500:
                raise ValueError("An identity field is too large")
            if normalized_value:
                normalized_identity_fields[field_name] = normalized_value
    phase10_dir = session_dir / "phase10"
    phase10_dir.mkdir(parents=True, exist_ok=True)
    reviewed_at = utc_now()
    ground_truth = {
        "schemaVersion": "1.1.0",
        "sessionId": result["sessionId"],
        "reviewedAt": reviewed_at,
        "reviewer": "local_user",
        "containsRealPII": True,
        "verificationAssertions": {
            "comparedWithImage": True,
            "allTextChecked": True,
            "acceptUnchangedDraft": bool(assertions.get("acceptUnchangedDraft")),
            "unchangedFromDraft": unchanged_from_draft,
        },
        "pages": normalized_pages,
    }
    if normalized_identity_fields:
        ground_truth["identityFields"] = normalized_identity_fields
    page_texts = _page_texts(result, session_dir)
    variants = [
        variant
        for variant in (
            "phase8Raw",
            "phase9Selected",
            "phase9Corrected",
            "easyocrChallenger",
        )
        if variant in page_texts
    ]
    page_evaluations: list[dict[str, Any]] = []
    aggregate: dict[str, dict[str, float | bool]] = {}
    for page in normalized_pages:
        page_index = page["pageIndex"]
        variant_metrics = {
            variant: metrics(
                page["text"],
                page_texts.get(variant, [""] * expected_pages)[page_index]
                if page_index < len(page_texts.get(variant, []))
                else "",
            )
            for variant in variants
        }
        page_evaluations.append(
            {"pageIndex": page_index, "variants": variant_metrics}
        )
    reference = submitted_reference
    for variant in variants:
        aggregate[variant] = metrics(
            reference, "\n".join(page_texts.get(variant, []))
        )
    evaluation = {
        "schemaVersion": "1.0.0",
        "sessionId": result["sessionId"],
        "evaluatedAt": reviewed_at,
        "containsRawPII": False,
        "pageCount": expected_pages,
        "pages": page_evaluations,
        "aggregate": aggregate,
    }
    if normalized_identity_fields:
        phase9_identity = extract_cccd_fields(
            result.get("phase9", {}).get("pages", []),
            engine="PaddleOCR/Phase9",
        )
        phase11_identity = result.get("phase11", {}).get("identityCard") or {
            "fields": {}
        }
        field_variants = {
            "phase9Before": evaluate_field_predictions(
                normalized_identity_fields,
                phase9_identity.get("fields", {}),
            ),
            "phase11After": evaluate_field_predictions(
                normalized_identity_fields,
                phase11_identity.get("fields", {}),
            ),
        }
        challenger_path = phase10_dir / "easyocr.json"
        if challenger_path.is_file():
            challenger = json.loads(
                challenger_path.read_text(encoding="utf-8")
            )
            challenger_identity = (
                challenger.get("document", {}).get("identityCard") or {}
            )
            field_variants["easyocrChallenger"] = evaluate_field_predictions(
                normalized_identity_fields,
                challenger_identity.get("fields", {}),
            )
        evaluation["fieldEvaluation"] = {
            "groundTruthFieldCount": len(normalized_identity_fields),
            "variants": field_variants,
        }
    business_json = {
        "schemaVersion": "0.1.0-pilot",
        "documentId": result["sessionId"],
        "documentType": result.get("document", {}).get(
            "documentType", "GENERIC_DOCUMENT"
        ),
        "verificationStatus": "USER_REVIEWED",
        "verifiedAt": reviewed_at,
        "containsRealPII": True,
        "source": {
            "sessionId": result["sessionId"],
            "groundTruth": "phase10/ground_truth.json",
        },
        "fields": verified_fields(reference),
        "identityCardFields": {
            field_name: {
                "value": value,
                "verified": True,
                "verificationMethod": "user_reviewed_ground_truth",
            }
            for field_name, value in normalized_identity_fields.items()
        },
        "limitations": [
            "Pilot schema only; no Camunda mapping.",
            "Only explicitly reviewed identity fields are marked verified.",
        ],
    }
    (phase10_dir / "ground_truth.json").write_text(
        json.dumps(ground_truth, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (phase10_dir / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (phase10_dir / "business.json").write_text(
        json.dumps(business_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "reviewed": True,
        "draftPages": normalized_pages,
        "groundTruth": ground_truth,
        "evaluation": evaluation,
        "businessJson": business_json,
    }
