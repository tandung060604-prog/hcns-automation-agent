from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from phase11_6_cccd import (  # noqa: E402
    field_candidate,
    locate_field_regions,
    select_field_candidate,
)


def candidate(value: str, profile: str, confidence: float = 0.8) -> dict:
    return {
        "value": value,
        "rawValue": value,
        "profile": profile,
        "confidence": confidence,
        "variant": "lanczos_upscale",
    }


def test_address_region_stops_before_next_label_and_allows_two_lines() -> None:
    pages = [
        {
            "pageIndex": 0,
            "recognizedTexts": [
                "Quê quán / Place of origin",
                "Nơi thường trú / Place of residence",
                "Có giá trị đến / Date of expiry",
            ],
            "recognizedBoxes": [
                [[100, 660], [500, 660], [500, 685], [100, 685]],
                [[100, 760], [500, 760], [500, 785], [100, 785]],
                [[20, 910], [350, 910], [350, 935], [20, 935]],
            ],
        }
    ]

    regions = locate_field_regions(pages, [(1000, 1000)])

    assert regions["placeOfOrigin"]["bbox"][3] < 760
    assert regions["placeOfOrigin"]["maxValueLines"] == 2
    assert regions["placeOfResidence"]["bbox"][3] < 910
    assert regions["placeOfResidence"]["maxValueLines"] == 2


def test_address_cleanup_drops_trailing_next_field_label() -> None:
    value = field_candidate(
        "placeOfOrigin",
        "Quê quán / Place of origin: Quỳnh Lâm, Hòa Bình Nơi thường trú / Place of residence",
    )
    assert value == "Quỳnh Lâm, Hòa Bình"


def test_name_selection_penalizes_label_merged_candidate_without_creating_text() -> None:
    result = select_field_candidate(
        "fullName",
        [
            candidate("Họ và tên / Full name: NGUYỄN NGỌC PHÚ Ngày sinh", "paddle_ppocrv5"),
            candidate("NGUYỄN NGỌC PHÚ", "easyocr_vi", 0.72),
            candidate("NGUYỄN NGỌC PHÚ", "vietocr_vgg_seq2seq", 0.70),
        ],
        bbox=[1, 2, 3, 4],
    )

    assert result["value"] == "NGUYỄN NGỌC PHÚ"
    # The merged raw Paddle evidence remains visible, therefore this is review-only.
    assert result["status"] == "needs_review"
    assert result["selectionMode"].startswith("phase11_6_")
