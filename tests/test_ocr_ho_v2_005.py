from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from phase11_5_cccd import FIELD_ORDER  # noqa: E402
from phase11_5_cccd_v2 import (  # noqa: E402
    OCR_HO_V2_005_ORIENTATION_POLICY,
    OCR_HO_V2_005_VERSION,
    build_shadow_fields,
    clean_candidate_value,
    recover_field,
)


def _candidate(value: str, profile: str, confidence: float = 0.9) -> dict:
    return {"value": value, "profile": profile, "confidence": confidence}


def _field(value: str | None, status: str = "needs_review") -> dict:
    return {
        "value": value,
        "asciiValue": value,
        "status": status,
        "asciiStatus": "needs_review",
        "evidence": {"candidates": []},
    }


def test_candidate_cleaner_stops_at_bilingual_neighbor_labels() -> None:
    assert (
        clean_candidate_value(
            "placeOfOrigin",
            "Quê quán / Place of origin: Phường Một, Thành phố A "
            "Nơi thường trú / Place of residence: Số 2",
        )
        == "Phường Một, Thành phố A"
    )
    assert (
        clean_candidate_value(
            "placeOfResidence",
            "Nơi thường trú / Place of residence: Số 2, Phường Hai 01/02/2030",
        )
        == "Số 2, Phường Hai"
    )


def test_candidate_cleaner_rejects_a_date_label_as_full_name() -> None:
    assert clean_candidate_value("fullName", "Ngày, tháng, năm sinh") == ""
    assert (
        clean_candidate_value(
            "fullName", "Họ và tên / Full name: NGUYỄN VĂN AN Ngày sinh"
        )
        == "NGUYỄN VĂN AN"
    )


def test_guarded_recovery_replaces_only_a_baseline_risk_and_keeps_review() -> None:
    baseline = _field("Quê quán / Place of origin: Cà Mau Nơi thường trú")
    result = recover_field(
        "placeOfOrigin",
        baseline,
        [
            _candidate("Cà Mau", "vietocr_vgg_seq2seq"),
            _candidate("Cà Mau", "paddle_ppocrv5"),
        ],
    )
    assert result["value"] == "Cà Mau"
    assert result["status"] == "needs_review"
    assert result["shadowRecovery"]["guardedRecoveryApplied"] is True


def test_guarded_recovery_preserves_a_safe_baseline() -> None:
    baseline = _field("Cà Mau")
    result = recover_field(
        "placeOfOrigin",
        baseline,
        [
            _candidate("Hà Nội", "vietocr_vgg_seq2seq"),
            _candidate("Hà Nội", "paddle_ppocrv5"),
        ],
    )
    assert result["value"] == "Cà Mau"
    assert result["shadowRecovery"]["guardedRecoveryApplied"] is False
    assert result["status"] == "needs_review"


def test_shadow_fields_keep_schema_and_manual_review_policy() -> None:
    baseline = {name: _field(None, "not_found") for name in FIELD_ORDER}
    result = build_shadow_fields(baseline)
    assert set(result) == set(FIELD_ORDER)
    assert all(field["status"] != "accepted" for field in result.values())
    assert all(field["policyVersion"] == OCR_HO_V2_005_VERSION for field in result.values())
    assert OCR_HO_V2_005_ORIENTATION_POLICY == "fixed_0_degree"
