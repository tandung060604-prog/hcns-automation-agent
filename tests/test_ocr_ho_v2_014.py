from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from ocr_ho_v2_014_evaluation import classify, gates  # noqa: E402
from phase11_10_cccd_v2 import (  # noqa: E402
    _select_name,
    assemble_line_candidates,
    locate_field_regions,
)


def test_line_aware_regions_stop_at_the_next_label() -> None:
    page = {
        "pageIndex": 0,
        "recognizedTexts": [
            "Họ và tên",
            "Nguyễn Văn A",
            "Nơi thường trú",
            "Số 1",
            "Phường A",
            "Có giá trị đến",
        ],
        "recognizedBoxes": [
            [[10, 100], [100, 100], [100, 120], [10, 120]],
            [[20, 130], [160, 130], [160, 150], [20, 150]],
            [[10, 300], [180, 300], [180, 320], [10, 320]],
            [[20, 330], [100, 330], [100, 350], [20, 350]],
            [[20, 360], [100, 360], [100, 380], [20, 380]],
            [[10, 400], [180, 400], [180, 420], [10, 420]],
        ],
    }
    regions = locate_field_regions([page], [(500, 500)])
    assert regions["fullName"]["lineIds"] == [1]
    assert regions["placeOfResidence"]["lineIds"] == [3, 4]


def test_line_candidates_keep_reading_order() -> None:
    candidates = {
        "placeOfResidence": [
            {
                "profile": "paddle_ppocrv5",
                "variant": "color",
                "lineOrder": 1,
                "value": "Dòng hai",
                "rawValue": "Dòng hai",
            },
            {
                "profile": "paddle_ppocrv5",
                "variant": "color",
                "lineOrder": 0,
                "value": "Dòng một",
                "rawValue": "Dòng một",
            },
        ]
    }
    assert (
        assemble_line_candidates(candidates)["placeOfResidence"][0]["value"] == "Dòng một Dòng hai"
    )


def test_gates_and_error_labels_are_separate() -> None:
    metric = {
        "strictFieldExactMatch": 0.7,
        "asciiFieldExactMatch": 0.95,
        "cer": 0.1,
        "der": 0.1,
        "fieldPresence": 1.0,
        "acceptedPrecision": 1.0,
        "sensitiveFieldFalseAcceptanceCount": 0,
        "perField": {
            "fullName": {"asciiExactMatch": 1.0},
            "placeOfOrigin": {"asciiExactMatch": 0.9},
            "placeOfResidence": {"asciiExactMatch": 0.9},
        },
    }
    result = gates(
        metric, metric, improvements=1, regressions=0, schema_errors=0, all_manual_review=True
    )
    assert result["developmentRegressionGate"]["status"] == "DEVELOPMENT_IMPROVED"
    assert result["heldoutReadinessGate"]["status"] == "READY_FOR_NEW_HELDOUT"
    assert (
        classify(
            roi_contains_lines=True,
            candidates=["Nguyen Van A"],
            selected="Nguyen Van A",
            expected="Nguyễn Văn A",
            contaminated=False,
        )
        == "DIACRITIC_MISS"
    )


def test_readiness_does_not_require_precision_without_accepted_fields() -> None:
    metric = {
        "strictFieldExactMatch": 0.7,
        "asciiFieldExactMatch": 0.95,
        "cer": 0.1,
        "der": 0.1,
        "fieldPresence": 1.0,
        "acceptedPrecision": 0.0,
        "acceptedCoverage": 0.0,
        "sensitiveFieldFalseAcceptanceCount": 0,
        "perField": {
            "fullName": {"asciiExactMatch": 0.95},
            "placeOfOrigin": {"asciiExactMatch": 0.9},
            "placeOfResidence": {"asciiExactMatch": 0.9},
        },
    }
    result = gates(
        metric, metric, improvements=1, regressions=0, schema_errors=0, all_manual_review=True
    )
    assert result["heldoutReadinessGate"]["checks"]["acceptedPrecision"] is True


def test_name_selector_counts_two_vietocr_profiles_as_independent_support() -> None:
    candidates = [
        {
            "profile": "vietocr_vgg_seq2seq",
            "variant": "color",
            "value": "Nguyen Van A",
            "confidence": 0.8,
        },
        {
            "profile": "vietocr_vgg_transformer",
            "variant": "color",
            "value": "Nguyễn Văn A",
            "confidence": 0.8,
        },
    ]
    selected = _select_name(candidates, [0, 0, 100, 20])
    assert selected["status"] == "needs_review"
    assert selected["selectionMode"] in {
        "phase11_10_name_unicode_consensus",
        "phase11_10_name_ascii_consensus",
    }
