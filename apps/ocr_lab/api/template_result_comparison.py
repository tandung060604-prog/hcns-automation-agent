"""Local-only field comparison for one Template-first session."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from external_dataset_prediction import MATCHING_POLICY_V2, _field_match

_META_FIELDS = frozenset(
    {
        "documentId",
        "documentType",
        "templateId",
        "templateVersion",
        "schemaVersion",
        "missingFields",
        "validationErrors",
        "confidence",
        "recommendedAction",
        "sourceFile",
    }
)
_CATEGORY_BY_DOCUMENT_TYPE = {
    "CV": "cv",
    "EMPLOYMENT_CONTRACT": "contract",
    "CERTIFICATE": "ielts",
}


def compare_template_result(
    result: dict[str, Any],
    ground_truth: dict[str, object],
) -> dict[str, Any]:
    data = result.get("data")
    quality = result.get("quality")
    processing = result.get("processing")
    if (
        not isinstance(data, dict)
        or not isinstance(quality, dict)
        or not isinstance(processing, dict)
    ):
        raise ValueError("Template result is inconsistent")

    predictions = {name: value for name, value in data.items() if name not in _META_FIELDS}
    unsupported = set(ground_truth) - set(predictions)
    if unsupported:
        raise ValueError("Ground Truth contains unsupported fields")
    if any(not _is_scalar(value) for value in ground_truth.values()):
        raise ValueError("Ground Truth values must be scalar")

    category = _CATEGORY_BY_DOCUMENT_TYPE.get(str(result.get("documentType")), "generic")
    missing_fields = set(quality.get("missingFields", []))
    evidence_by_field = {
        str(item.get("field")): item
        for item in processing.get("ocrFieldEvidence", [])
        if isinstance(item, dict) and item.get("field")
    }
    fallback_confidence = _number_or_none(quality.get("confidence"))
    rows: list[dict[str, Any]] = []
    for name, prediction in predictions.items():
        evidence = evidence_by_field.get(name)
        field_confidence = (
            _number_or_none(evidence.get("confidence")) if evidence else fallback_confidence
        )
        if name not in ground_truth:
            rows.append(
                {
                    "name": name,
                    "prediction": prediction,
                    "groundTruth": None,
                    "status": "NEEDS_REVIEW",
                    "confidence": field_confidence,
                    "evidence": evidence or _native_evidence(processing),
                    "matchType": None,
                    "coverage": None,
                    "diagnosis": "GROUND_TRUTH_NOT_REVIEWED",
                }
            )
            continue

        truth = ground_truth[name]
        matched = _field_match(
            category,
            name,
            truth,
            prediction,
            policy_version=MATCHING_POLICY_V2,
        )
        if truth not in {None, ""} and (prediction in {None, ""} or name in missing_fields):
            status = "MISSING"
        elif matched["rawExact"] or matched["matchType"] == "CANONICAL_EXACT":
            status = "EXACT"
        elif matched["match"]:
            status = "ACCEPTED"
        else:
            status = "MISMATCH"
        rows.append(
            {
                "name": name,
                "prediction": prediction,
                "groundTruth": truth,
                "status": status,
                "confidence": field_confidence,
                "evidence": evidence or _native_evidence(processing),
                "matchType": matched["matchType"],
                "coverage": matched["coverage"],
                "diagnosis": matched["diagnosis"],
            }
        )

    counts = {status: sum(row["status"] == status for row in rows) for status in (
        "EXACT", "ACCEPTED", "MISMATCH", "MISSING", "NEEDS_REVIEW"
    )}
    compared = len(rows) - counts["NEEDS_REVIEW"]
    wrong = counts["MISMATCH"] + counts["MISSING"]
    decision = "PASS" if rows and compared == len(rows) and wrong == 0 else "HOLD"
    return {
        "schemaVersion": "template-current-file-comparison/1.0.0",
        "scope": "CURRENT_FILE",
        "documentId": data.get("documentId"),
        "documentType": result.get("documentType"),
        "templateId": result.get("templateId"),
        "templateVersion": result.get("templateVersion"),
        "matchingPolicyVersion": MATCHING_POLICY_V2,
        "comparedAt": datetime.now(timezone.utc).isoformat(),
        "groundTruth": ground_truth,
        "fields": rows,
        "summary": {
            "totalFields": len(rows),
            "comparedFields": compared,
            "exactFields": counts["EXACT"],
            "acceptedFields": counts["ACCEPTED"],
            "wrongFields": wrong,
            "mismatchFields": counts["MISMATCH"],
            "missingFields": counts["MISSING"],
            "needsReviewFields": counts["NEEDS_REVIEW"],
            "decision": decision,
        },
        "workflow": {
            "recommendedAction": quality.get("recommendedAction"),
            "promotionAllowed": False,
            "note": (
                "PASS chỉ xác nhận đối chiếu field của file hiện tại; "
                "không tự động duyệt nghiệp vụ."
            ),
        },
    }


def _native_evidence(processing: dict[str, Any]) -> dict[str, object]:
    return {
        "source": "ocr" if processing.get("usesOcr") else "native-parser",
        "parserName": processing.get("parserName"),
        "available": False,
        "note": "Không có bounding box theo field; hiển thị confidence cấp tài liệu.",
    }


def _number_or_none(value: object) -> float | None:
    return float(value) if not isinstance(value, bool) and isinstance(value, (int, float)) else None


def _is_scalar(value: object) -> bool:
    return value is None or (
        isinstance(value, (str, int, float, bool))
        and not (isinstance(value, str) and len(value) > 16_384)
    )
