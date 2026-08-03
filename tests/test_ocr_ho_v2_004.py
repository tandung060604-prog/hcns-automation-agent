from __future__ import annotations

import sys

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from phase11_cccd import (  # noqa: E402
    OCR_HO_V2_VERSION,
    ORIENTATION_POLICY,
    SUPPORTED_ORIENTATIONS,
    extract_cccd_fields,
)


def _line(text: str, top: int, left: int = 100, width: int = 900) -> dict:
    return {
        "rawText": text,
        "confidence": 0.96,
        "box": [[left, top], [left + width, top], [left + width, top + 24], [left, top + 24]],
        "outputIndex": top,
    }


def _page(lines: list[dict]) -> list[dict]:
    return [{"pageIndex": 0, "lines": lines}]


def test_v11_removes_bilingual_label_contamination_and_preserves_address_order() -> None:
    result = extract_cccd_fields(
        _page(
            [
                _line("Số / No. 012345678901", 40),
                _line("Họ và tên / Full name: NGUYỄN VĂN AN", 90),
                _line("Ngày sinh / Date of birth: 01/02/1990", 140),
                _line("Giới tính / Sex Nam Quốc tịch / Nationality Việt Nam", 190),
                _line("Quê quán / Place of qrigin: Phường Một, Thành phố A", 240),
                _line("Nơi thường trú I Piace of residence: Số 2, Phường Hai", 290),
                _line("Thành phố B", 320),
                _line("Có giá trị đến / Date of expiry: 01/02/2030", 370),
            ]
        ),
        engine="PaddleOCR/PP-OCRv5",
    )

    fields = result["fields"]
    assert fields["sex"]["value"] == "Nam"
    assert fields["placeOfOrigin"]["value"] == "Phường Một, Thành phố A"
    assert fields["placeOfResidence"]["value"] == "Số 2, Phường Hai Thành phố B"
    assert "place of" not in fields["placeOfOrigin"]["value"].casefold()
    assert "residence" not in fields["placeOfResidence"]["value"].casefold()
    assert result["schemaVersion"] == OCR_HO_V2_VERSION
    assert result["orientationPolicy"] == ORIENTATION_POLICY
    assert result["evaluationScope"] == "DEVELOPMENT_ONLY"


def test_v11_does_not_use_a_distant_enum_as_sex_evidence() -> None:
    result = extract_cccd_fields(
        _page(
            [
                _line("Số / No. 012345678901", 40),
                _line("Họ và tên / Full name: NGUYỄN VĂN AN", 90),
                _line("Ngày sinh / Date of birth: 01/02/1990", 140),
                _line("Quê quán / Place of origin: Phường Một, Thành phố A", 240),
                _line("Nơi thường trú / Place of residence: Số 2, Phường Hai", 290),
                _line("Có giá trị đến / Date of expiry: 01/02/2030", 370),
                _line("Nam", 900),
            ]
        ),
        engine="PaddleOCR/PP-OCRv5",
    )

    assert result["fields"]["sex"]["status"] == "not_found"


def test_v11_orientation_contract_is_fixed_to_zero_degrees() -> None:
    assert SUPPORTED_ORIENTATIONS == (0,)


def test_v11_does_not_reuse_birth_date_as_expiry_without_expiry_label() -> None:
    result = extract_cccd_fields(
        _page(
            [
                _line("So / No. 012345678901", 40),
                _line("Ho va ten / Full name: NGUYEN VAN AN", 90),
                _line("Ngay sinh / Date of birth: 01/02/1990", 140),
                _line("Que quan / Place of origin: Phuong Mot, Thanh pho A", 240),
                _line("Noi thuong tru / Place of residence: So 2, Phuong Hai", 290),
                _line("01/02/2030", 370),
            ]
        ),
        engine="PaddleOCR/PP-OCRv5",
    )

    assert result["fields"]["dateOfBirth"]["value"] == "01/02/1990"
    assert result["fields"]["dateOfExpiry"]["status"] == "not_found"
