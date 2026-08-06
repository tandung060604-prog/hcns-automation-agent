"""Aggregate-only gates and error labels for the v11.10 development replay."""

from __future__ import annotations

import unicodedata
from collections import Counter
from typing import Any


def gates(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    improvements: int,
    regressions: int,
    schema_errors: int,
    all_manual_review: bool,
    protected_regressions: int = 0,
) -> dict[str, Any]:
    per_field = after.get("perField", {})
    full_name_ascii = float(per_field.get("fullName", {}).get("asciiExactMatch", 0))
    address_ascii = (
        sum(
            float(per_field.get(name, {}).get("asciiExactMatch", 0))
            for name in ("placeOfOrigin", "placeOfResidence")
        )
        / 2
    )
    development = {
        "schemaErrorsZero": schema_errors == 0,
        "noExactRegression": regressions == 0,
        "targetImprovement": improvements >= 1,
        "exactNotWorse": after["strictFieldExactMatch"] >= before["strictFieldExactMatch"],
        "asciiNotWorse": after["asciiFieldExactMatch"] >= before["asciiFieldExactMatch"],
        "cerNotWorse": after["cer"] <= before["cer"],
        "derNotWorse": after["der"] <= before["der"],
        "presenceNotWorse": after["fieldPresence"] >= before["fieldPresence"],
        "manualReviewOnly": all_manual_review,
        "protectedFieldsPreserved": protected_regressions == 0,
    }
    readiness = {
        "fullNameAsciiExactMatch": full_name_ascii >= 0.90,
        "addressAsciiExactMatch": address_ascii >= 0.85,
        "fieldPresence": after["fieldPresence"] >= 0.95,
        "noSensitiveFalseAcceptance": after.get("sensitiveFieldFalseAcceptanceCount", 0) == 0,
        "noExactRegression": regressions == 0,
        "acceptedPrecision": (
            float(after.get("acceptedCoverage", 0.0)) == 0.0
            or after.get("acceptedPrecision") in (1.0, None)
        ),
        "protectedFieldsPreserved": protected_regressions == 0,
    }
    return {
        "developmentRegressionGate": {
            "status": "DEVELOPMENT_IMPROVED" if all(development.values()) else "HOLD",
            "checks": development,
        },
        "heldoutReadinessGate": {
            "status": "READY_FOR_NEW_HELDOUT" if all(readiness.values()) else "HOLD",
            "checks": readiness,
        },
        "fullNameAsciiExactMatch": full_name_ascii,
        "addressAsciiExactMatch": address_ascii,
    }


def classify(
    *,
    roi_contains_lines: bool,
    candidates: list[str],
    selected: str | None,
    expected: str,
    contaminated: bool,
) -> str:
    if not roi_contains_lines:
        return "ROI_MISS"
    def normalized(value: str) -> str:
        return "".join(
            char
            for char in unicodedata.normalize("NFD", value.casefold())
            if not unicodedata.combining(char) and not char.isspace()
        )
    if selected == expected:
        return "EXACT"
    if contaminated:
        return "PARSER_CONTAMINATION"
    if expected in candidates:
        return "SELECTOR_MISS"
    if normalized(expected) in {normalized(value) for value in candidates}:
        return "DIACRITIC_MISS"
    return "RECOGNIZER_MISS"


def aggregate(labels: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = {}
    for field, label in labels:
        counts.setdefault(field, Counter())[label] += 1
    return {field: dict(sorted(values.items())) for field, values in sorted(counts.items())}
