from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from phase11_6_cccd import (  # noqa: E402
    FIELD_ORDER,
    build_identity_card,
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


def test_phase11_6_output_matches_locked_schema() -> None:
    samples = {
        "identityNumber": "012345678901",
        "fullName": "NGUYỄN VĂN AN",
        "dateOfBirth": "01/02/1990",
        "sex": "Nam",
        "nationality": "Việt Nam",
        "placeOfOrigin": "Phường Một, Thành phố A",
        "placeOfResidence": "Tổ 02, Phường Hai, Thành phố B",
        "dateOfExpiry": "01/02/2030",
    }
    candidates = {
        field_name: [
            candidate(samples[field_name], "paddle_ppocrv5"),
            candidate(samples[field_name], "vietocr_vgg_seq2seq"),
        ]
        for field_name in FIELD_ORDER
    }
    regions = {
        name: {"pageIndex": 0, "bbox": [10, 20, 300, 80]}
        for name in FIELD_ORDER
    }
    payload = build_identity_card(candidates, regions)
    schema = json.loads(
        (ROOT / "schemas" / "vietnam_identity_card_phase11_6.schema.json").read_text(
            encoding="utf-8"
        )
    )

    validate(payload, schema)
    assert payload["schemaVersion"] == "11.6.0"
    assert payload["policyMode"] == "SHADOW_REVIEW_ONLY"
    assert all(
        field["selectionMode"].startswith("phase11_6_")
        for field in payload["fields"].values()
    )


def test_phase11_6_preserves_baseline_when_target_candidate_disagrees() -> None:
    baseline = {
        name: select_field_candidate(
            name,
            [
                candidate(
                    {
                        "identityNumber": "012345678901",
                        "fullName": "NGUYỄN VĂN AN",
                        "dateOfBirth": "01/02/1990",
                        "sex": "Nam",
                        "nationality": "Việt Nam",
                        "placeOfOrigin": "Phường Một",
                        "placeOfResidence": "Tổ 02, Phường Hai",
                        "dateOfExpiry": "01/02/2030",
                    }[name],
                    "paddle_ppocrv5",
                )
            ],
            bbox=[1, 2, 3, 4],
        )
        for name in FIELD_ORDER
    }
    candidates = {
        "fullName": [
            candidate("NGUYỄN VĂN B", "easyocr_vi"),
            candidate("NGUYỄN VĂN B", "vietocr_vgg_seq2seq"),
        ],
        "placeOfOrigin": [
            candidate("Phường Khác", "easyocr_vi"),
            candidate("Phường Khác", "vietocr_vgg_seq2seq"),
        ],
        "placeOfResidence": [],
    }
    regions = {
        name: {"pageIndex": 0, "bbox": [10, 20, 300, 80]}
        for name in FIELD_ORDER
    }

    payload = build_identity_card(
        candidates,
        regions,
        baseline_fields=baseline,
    )

    assert payload["fields"]["fullName"]["value"] == "NGUYỄN VĂN AN"
    assert (
        payload["fields"]["fullName"]["selectionMode"]
        == "phase11_6_baseline_preserved"
    )
    assert (
        payload["fields"]["fullName"]["phase11_6Candidate"]["value"]
        == "NGUYỄN VĂN B"
    )
    assert payload["fields"]["sex"]["value"] == "Nam"


def test_phase11_6_new_target_value_is_review_only() -> None:
    candidates = {
        "placeOfOrigin": [
            candidate("Phường Một", "easyocr_vi"),
            candidate("Phường Một", "vietocr_vgg_seq2seq"),
        ]
    }
    regions = {
        name: {"pageIndex": 0, "bbox": [10, 20, 300, 80]}
        for name in FIELD_ORDER
    }

    payload = build_identity_card(candidates, regions, baseline_fields={})

    assert payload["fields"]["placeOfOrigin"]["value"] == "Phường Một"
    assert payload["fields"]["placeOfOrigin"]["status"] == "needs_review"
