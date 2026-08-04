from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from phase11_5_cccd import FIELD_ORDER  # noqa: E402
from phase11_7_cccd_v2 import (  # noqa: E402
    CANDIDATE_VERSION,
    build_identity_card,
    field_candidate,
    locate_field_regions,
    repair_unicode,
    select_address_candidate,
)


def _candidate(value: str, profile: str, confidence: float = 0.9) -> dict:
    return {
        "value": value,
        "rawValue": value,
        "profile": profile,
        "confidence": confidence,
        "variant": "balanced_padding",
    }


def test_address_roi_includes_same_row_value_and_stops_origin_before_residence() -> None:
    page = {
        "pageIndex": 0,
        "recognizedTexts": [
            "Quê quán / Place of origin",
            "Nơi thường trú / Place of residence",
            "Có giá trị đến / Date of expiry",
        ],
        "recognizedBoxes": [
            [[100, 400], [250, 400], [250, 425], [100, 425]],
            [[100, 450], [280, 450], [280, 478], [100, 478]],
            [[0, 600], [100, 600], [100, 620], [0, 620]],
        ],
    }
    regions = locate_field_regions([page], [(633, 633)])
    origin = regions["placeOfOrigin"]["bbox"]
    residence = regions["placeOfResidence"]["bbox"]
    assert origin[1] < 400 < origin[3] < residence[1] + 5
    assert residence[1] <= 450
    assert residence[3] >= 500


def test_repair_unicode_only_decodes_reversible_mojibake() -> None:
    source = "Nơi thường trú"
    mojibake = source.encode("utf-8").decode("latin-1")
    assert repair_unicode(mojibake) == source
    assert repair_unicode("Hoang Lau Tam Duong") == "Hoang Lau Tam Duong"


def test_address_cleaner_removes_bilingual_neighbor_label_and_date() -> None:
    raw = (
        "Quê quán / Place of origin: Hoàng Lâu, Tam Dương, Vĩnh Phúc "
        "Nơi thường trú / Place of residence: Số 2, Phường Hai 24/09/2030"
    )
    assert field_candidate("placeOfOrigin", raw) == "Hoàng Lâu, Tam Dương, Vĩnh Phúc"
    assert (
        field_candidate(
            "placeOfResidence",
            "Nơi thường trú / Place of residence: Số 2, Phường Hai 24/09/2030",
        )
        == "Số 2, Phường Hai"
    )


def test_selector_prefers_unicode_with_independent_family_support() -> None:
    candidates = [
        _candidate(
            "Hoàng Lâu, Tam Dương, Vĩnh Phúc",
            "vietocr_vgg_seq2seq",
            0.82,
        ),
        _candidate(
            "Hoàng Lâu Tam Dương Vĩnh Phúc",
            "paddle_ppocrv5",
            0.91,
        ),
    ]
    result = select_address_candidate("placeOfOrigin", candidates, bbox=[0, 0, 100, 100])
    assert result["value"] == "Hoàng Lâu, Tam Dương, Vĩnh Phúc"
    assert result["status"] == "needs_review"
    assert result["validation"]["unicodeEvidencePresent"] is True


def test_candidate_schema_fields_remain_manual_review() -> None:
    payload = build_identity_card(
        {
            "placeOfOrigin": [
                _candidate("Hà Nội", "vietocr_vgg_seq2seq", 0.8),
                _candidate("Ha Noi", "paddle_ppocrv5", 0.9),
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
