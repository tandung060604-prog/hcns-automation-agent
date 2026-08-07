from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_ocr_ho_v2_015 import class_report  # noqa: E402
from ocr_ho_v2_014_evaluation import classify, diagnostic_gates, gates  # noqa: E402
from phase11_10_cccd_v2 import (  # noqa: E402
    _select_name,
    assemble_line_candidates,
    build_identity_card,
    field_candidate,
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


def test_residence_keeps_value_sharing_its_label_line() -> None:
    page = {
        "pageIndex": 0,
        "recognizedTexts": [
            "Place of origin",
            "Origin value",
            "Place of residence: Residence value",
            "Date of expiry",
        ],
        "recognizedBoxes": [
            [[10, 100], [180, 100], [180, 120], [10, 120]],
            [[20, 130], [220, 130], [220, 150], [20, 150]],
            [[10, 300], [320, 300], [320, 325], [10, 325]],
            [[10, 400], [180, 400], [180, 420], [10, 420]],
        ],
    }
    regions = locate_field_regions([page], [(500, 500)])
    assert regions["placeOfResidence"]["lineIds"] == [2]


def test_parser_removes_merged_residence_label_without_accepting_value() -> None:
    assert field_candidate(
        "placeOfResidence", "N\u01a1i th\u01b0\u1eddng tr\u00fa: ABC DEF"
    ) == "ABC DEF"
    card = build_identity_card(
        {
            "placeOfResidence": [
                {
                    "profile": "paddle_ppocrv5",
                    "variant": "color_original",
                    "value": "ABC DEF",
                    "rawValue": "Place of residence: ABC DEF",
                    "confidence": 0.9,
                },
                {
                    "profile": "paddle_ppocrv5",
                    "variant": "grayscale_clahe",
                    "value": "ABC DEF",
                    "rawValue": "Place of residence: ABC DEF",
                    "confidence": 0.9,
                },
            ]
        },
        {"placeOfResidence": {"bbox": [0, 0, 100, 100], "pageIndex": 0}},
    )
    field = card["fields"]["placeOfResidence"]
    assert field["value"] == "ABC DEF"
    assert "label_contamination" not in field["errorSignals"]
    assert field["status"] == "needs_review"


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


def test_diagnostic_gate_holds_when_canonical_snapshot_does_not_match() -> None:
    metric = {
        "strictFieldExactMatch": 0.7,
        "asciiFieldExactMatch": 0.95,
        "cer": 0.1,
        "der": 0.1,
        "fieldPresence": 1.0,
        "sensitiveFieldFalseAcceptanceCount": 0,
        "perField": {
            "fullName": {"asciiExactMatch": 0.95},
            "placeOfOrigin": {"asciiExactMatch": 0.9},
            "placeOfResidence": {"asciiExactMatch": 0.9},
        },
    }
    result = diagnostic_gates(
        metric,
        metric,
        improvements=1,
        regressions=0,
        schema_errors=0,
        all_manual_review=True,
        protected_regressions=0,
        snapshot_status="SNAPSHOT_MISMATCH",
        document_count=15,
        evaluated_field_count=120,
        automatic_roi={"placeOfOrigin": 1.0, "placeOfResidence": 1.0},
    )
    assert result["developmentRegressionGate"]["status"] == "HOLD"
    assert result["developmentRegressionGate"]["checks"]["snapshotMatched"] is False
    assert result["heldoutReadinessGate"]["status"] == "HOLD"


def test_oracle_class_report_uses_oracle_regions_not_auto_regions() -> None:
    target = {
        "fullName": "A",
        "placeOfOrigin": "B",
        "placeOfResidence": "C",
    }
    document = {
        "groundTruth": target,
        "oracle": {name: {"value": value} for name, value in target.items()},
        "oracleArtifact": {
            "regions": {name: {"lineIds": [0]} for name in target},
            "candidates": {name: [] for name in target},
        },
        "gtFields": {name: {"lineIds": [0]} for name in target},
    }
    report = class_report([document], "oracle")
    assert all(item["accuracy"] == 1.0 for item in report["roiByField"].values())
