from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from jsonschema import validate
except ModuleNotFoundError:  # pragma: no cover - minimal OCR runtime
    def validate(instance: dict, _schema: dict) -> None:
        assert instance["schemaVersion"] == "11.6.0"
        assert instance["documentType"] == "VIETNAM_CITIZEN_ID_FRONT"
        assert instance["policyMode"] == "SHADOW_REVIEW_ONLY"
        assert set(instance["fields"]) == set(FIELD_ORDER)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from phase11_5_cccd import FIELD_ORDER  # noqa: E402
from phase11_9_cccd_v2 import (  # noqa: E402
    CANDIDATE_VERSION,
    build_identity_card,
    field_candidate,
    locate_field_regions,
    select_address_candidate,
)


def _candidate(value: str, variant: str, confidence: float = 0.9) -> dict:
    return {
        "value": value,
        "rawValue": value,
        "profile": "paddle_ppocrv5",
        "confidence": confidence,
        "variant": variant,
    }


def test_address_rois_are_anchor_bounded_and_expiry_is_not_the_residence_end() -> None:
    page = {
        "pageIndex": 0,
        "recognizedTexts": [
            "Ho va ten:",
            "Noi thuong tru / Place of residence",
            "Co gia tri den / Date of expiry",
        ],
        "recognizedBoxes": [
            [[120, 280], [220, 280], [220, 302], [120, 302]],
            [[210, 456], [400, 456], [400, 494], [210, 494]],
            [[40, 512], [220, 509], [220, 540], [40, 540]],
        ],
    }
    regions = locate_field_regions([page], [(633, 633)])
    origin = regions["placeOfOrigin"]["bbox"]
    residence = regions["placeOfResidence"]["bbox"]
    assert origin[0] >= 190
    assert origin[1] < 430 < origin[3]
    assert residence[1] <= 456
    assert residence[3] < 560
    assert residence[3] > 500


def test_cleaner_removes_neighbor_label_and_expiry_date() -> None:
    raw = (
        "Quê quán / Place of origin: Phường Một, Thành phố A "
        "Nơi thường trú / Place of residence: Số 2, Phường Hai "
        "Có giá trị đến / Date of expiry: 24/09/2030"
    )
    assert field_candidate("placeOfOrigin", raw) == "Phường Một, Thành phố A"
    assert field_candidate("placeOfResidence", raw) == "Số 2, Phường Hai"


def test_same_profile_paddle_variants_require_two_matching_variants() -> None:
    candidates = [
        _candidate("Phường Một, Thành phố A", "color_original", 0.91),
        _candidate("Phường Một, Thành phố A", "lanczos_upscale", 0.94),
        _candidate("Phường Khác, Thành phố B", "grayscale_clahe", 0.99),
    ]
    result = select_address_candidate(
        "placeOfOrigin",
        candidates,
        bbox=[100, 300, 600, 480],
    )
    assert result["value"] == "Phường Một, Thành phố A"
    assert result["validation"]["sameProfileVariantConsensus"] is True
    assert result["status"] == "needs_review"


def test_schema_and_manual_review_contract_remain_locked() -> None:
    payload = build_identity_card(
        {
            "placeOfOrigin": [
                _candidate("Phường Một, Thành phố A", "color_original"),
                _candidate("Phường Một, Thành phố A", "lanczos_upscale"),
            ]
        },
        {name: {"pageIndex": 0, "bbox": [0, 0, 100, 100]} for name in FIELD_ORDER},
        baseline_fields={},
    )
    schema = json.loads(
        (ROOT / "schemas" / "vietnam_identity_card_phase11_6.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validate(payload, schema)
    assert payload["summary"]["candidateVersion"] == CANDIDATE_VERSION
    assert all(field["status"] != "accepted" for field in payload["fields"].values())
