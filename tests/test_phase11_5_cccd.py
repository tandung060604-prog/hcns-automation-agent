from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from phase11_5_cccd import (  # noqa: E402
    ascii_text,
    build_crop_variants,
    build_identity_card,
    field_candidate,
    infer_error_signals,
    select_field_candidate,
)


def candidate(value: str, profile: str, confidence: float = 0.9) -> dict:
    return {
        "value": value,
        "profile": profile,
        "confidence": confidence,
        "variant": "color_original",
    }


def test_ascii_keeps_base_letters_for_vietnamese_groups() -> None:
    assert ascii_text("A Ă Â O Ô Ơ U Ư E Ê I Y Đ") == "A A A O O O U U E E I Y D"
    assert ascii_text("TRẦN BẠCH NGUYỄN UYỂN VĨ") == "TRAN BACH NGUYEN UYEN VI"


def test_exact_consensus_accepts_unicode_nfc() -> None:
    result = select_field_candidate(
        "fullName",
        [
            candidate("NGUYỄN UYỂN VĨ", "paddle_ppocrv5"),
            candidate("NGUYỄN UYỂN VĨ", "vietocr_vgg_seq2seq", 0.95),
            candidate("NGUYEN UYEN VI", "easyocr_vi"),
        ],
        bbox=[1, 2, 3, 4],
    )
    assert result["status"] == "accepted"
    assert result["asciiStatus"] == "verified_base_text"
    assert result["selectionMode"] == "exact_consensus"
    assert result["value"] == "NGUYỄN UYỂN VĨ"
    assert result["asciiValue"] == "NGUYEN UYEN VI"


def test_base_consensus_never_silently_replaces_unicode() -> None:
    result = select_field_candidate(
        "fullName",
        [
            candidate("PHẠM THỊ LINH", "paddle_ppocrv5", 0.91),
            candidate("PHAM THI LINH", "easyocr_vi", 0.96),
            candidate("PHẠM THI LINH", "vietocr_vgg_seq2seq", 0.93),
        ],
        bbox=[1, 2, 3, 4],
    )
    assert result["status"] == "needs_review"
    assert result["asciiStatus"] == "verified_base_text"
    assert result["selectionMode"] == "base_text_consensus"
    assert result["asciiValue"] == "PHAM THI LINH"
    assert "diacritic_disagreement" in result["errorSignals"]


def test_exact_ascii_name_remains_review_only_without_unicode_evidence() -> None:
    result = select_field_candidate(
        "fullName",
        [
            candidate("NGUYEN UYEN VI", "paddle_ppocrv5"),
            candidate("NGUYEN UYEN VI", "easyocr_vi"),
        ],
        bbox=[1, 2, 3, 4],
    )
    assert result["selectionMode"] == "exact_consensus"
    assert result["status"] == "needs_review"
    assert result["asciiStatus"] == "verified_base_text"
    assert result["validation"]["unicodeEvidenceRequired"] is True
    assert result["validation"]["unicodeEvidencePresent"] is False


def test_correlated_vietocr_models_cannot_accept_a_field_alone() -> None:
    result = select_field_candidate(
        "fullName",
        [
            candidate("PHẠM VĂN NHẠT", "vietocr_vgg_seq2seq"),
            candidate("PHẠM VĂN NHẠT", "vietocr_vgg_transformer"),
        ],
        bbox=[1, 2, 3, 4],
    )
    assert result["selectionMode"] == "exact_consensus"
    assert result["status"] == "needs_review"
    assert result["validation"]["supportingRecognizerFamilyCount"] == 1


def test_non_finite_model_confidence_is_never_promoted() -> None:
    result = select_field_candidate(
        "fullName",
        [
            candidate("NGUYỄN UYỂN VĨ", "paddle_ppocrv5", float("nan")),
            candidate("NGUYỄN UYỂN VĨ", "easyocr_vi", 0.91),
        ],
        bbox=[1, 2, 3, 4],
    )
    assert result["confidence"] == 0.0


def test_character_omission_is_not_diacritics_only() -> None:
    signals = infer_error_signals(
        [
            candidate("TRẦN", "paddle_ppocrv5"),
            candidate("TRN", "easyocr_vi"),
        ]
    )
    assert "character_omission" in signals
    assert "diacritic_disagreement" not in signals
    assert ascii_text("BẠCH") == "BACH"


def test_next_field_label_marks_region_or_line_merge() -> None:
    signals = infer_error_signals(
        [
            {
                **candidate("NGUYỄN UYỂN VĨ", "paddle_ppocrv5"),
                "rawValue": "Họ và tên: NGUYỄN UYỂN VĨ Ngày sinh: 17/12/2004",
            }
        ],
        "fullName",
    )
    assert "region_or_line_merge" in signals


def test_sex_does_not_take_nam_from_viet_nam() -> None:
    assert field_candidate("sex", "Quốc tịch / Nationality: Việt Nam") == ""
    assert field_candidate("sex", "Giới tính / Sex: Nữ Quốc tịch: Việt Nam") == "Nữ"


def test_enum_normalization_does_not_invent_missing_diacritics() -> None:
    assert field_candidate("sex", "Giới tính / Sex: Nu") == "Nu"
    assert field_candidate("nationality", "Quốc tịch / Nationality: Viet Nam") == "Viet Nam"
    assert field_candidate("nationality", "Nữ Việt Nam") == "Việt Nam"
    result = select_field_candidate(
        "nationality",
        [
            candidate("Viet Nam", "paddle_ppocrv5"),
            candidate("Viet Nam", "easyocr_vi"),
        ],
        bbox=[1, 2, 3, 4],
    )
    assert result["status"] == "needs_review"
    assert result["asciiStatus"] == "verified_base_text"
    assert result["validation"]["valid"] is False


def test_known_enum_validation_outranks_invalid_consensus() -> None:
    result = select_field_candidate(
        "nationality",
        [
            candidate("Nữ", "paddle_ppocrv5", 0.99),
            candidate("Nữ", "easyocr_vi", 0.99),
            candidate("Việt Nam", "vietocr_vgg_seq2seq", 0.80),
        ],
        bbox=[1, 2, 3, 4],
    )
    assert result["value"] == "Việt Nam"
    assert result["validation"]["valid"] is True
    assert result["status"] == "needs_review"


def test_full_name_stops_before_birth_date_even_when_line_order_is_merged() -> None:
    assert (
        field_candidate(
            "fullName",
            "Họ và tên / Full name: PHẠM VĂN NHẬT 21/07/1995 Ngày sinh",
        )
        == "PHẠM VĂN NHẬT"
    )


def test_expiry_must_be_after_birth() -> None:
    result = select_field_candidate(
        "dateOfExpiry",
        [
            candidate("17/12/2004", "paddle_ppocrv5"),
            candidate("17/12/2004", "easyocr_vi"),
        ],
        bbox=[1, 2, 3, 4],
        date_of_birth="17/12/2004",
    )
    assert result["status"] == "needs_review"
    assert result["validation"]["valid"] is False


def test_crop_profiles_preserve_color_and_accents() -> None:
    image = np.full((200, 400, 3), 255, dtype=np.uint8)
    variants = build_crop_variants(image, [20, 20, 380, 180])
    assert set(variants) == {
        "color_original",
        "grayscale_clahe",
        "lanczos_upscale",
        "balanced_padding",
    }
    assert variants["lanczos_upscale"]["image"].shape[0] > 160


def test_phase11_5_output_matches_locked_schema_and_provenance() -> None:
    candidates = {
        field_name: [
            candidate(
                {
                    "identityNumber": "017304006572",
                    "fullName": "NGUYỄN UYỂN VĨ",
                    "dateOfBirth": "17/12/2004",
                    "sex": "Nữ",
                    "nationality": "Việt Nam",
                    "placeOfOrigin": "Quỳnh Lâm, Hòa Bình",
                    "placeOfResidence": "Tổ 02, Quỳnh Lâm, Hòa Bình",
                    "dateOfExpiry": "17/12/2029",
                }[field_name],
                profile,
            )
            for profile in ("paddle_ppocrv5", "vietocr_vgg_seq2seq")
        ]
        for field_name in (
            "identityNumber",
            "fullName",
            "dateOfBirth",
            "sex",
            "nationality",
            "placeOfOrigin",
            "placeOfResidence",
            "dateOfExpiry",
        )
    }
    regions = {name: {"pageIndex": 0, "bbox": [1, 2, 3, 4]} for name in candidates}
    payload = build_identity_card(candidates, regions)
    schema = json.loads(
        (ROOT / "schemas" / "vietnam_identity_card_phase11_5.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validate(payload, schema)
    assert payload["policyMode"] == "SHADOW_REVIEW_ONLY"
    assert payload["fields"]["fullName"]["evidence"]["bbox"] == [1, 2, 3, 4]
