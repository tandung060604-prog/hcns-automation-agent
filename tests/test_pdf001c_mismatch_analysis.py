from __future__ import annotations

from scripts.analyze_pdf001c_mismatches import _classify_mismatch, _field_ocr_text


def test_alg004_classification_prefers_policy_normalization_then_parser_boundary() -> None:
    assert (
        _classify_mismatch(
            match={"match": True},
            truth_value="01/01/2026",
            raw_present=False,
            ground_truth_confirmed=True,
        )
        == "NORMALIZATION"
    )
    assert (
        _classify_mismatch(
            match={"match": False},
            truth_value="Công ty Kiểm thử",
            raw_present=True,
            prediction_present=False,
            ground_truth_confirmed=True,
        )
        == "PARSER_BOUNDARY"
    )
    assert (
        _classify_mismatch(
            match={"match": False},
            truth_value="Công ty Kiểm thử",
            raw_present=False,
            prediction_present=False,
            ground_truth_confirmed=True,
        )
        == "OCR_RECOGNITION"
    )
    assert (
        _classify_mismatch(
            match={"match": False},
            truth_value="Công ty Kiểm thử",
            raw_present=True,
            prediction_present=False,
            ground_truth_confirmed=False,
        )
        == "GROUND_TRUTH_REVIEW"
    )


def test_alg005_scopes_ocr_evidence_to_the_field_label() -> None:
    blocks = [
        {"text": "Đại diện cho: OCR COMPANY"},
        {"text": "Địa điểm: Công ty TNHH Ground Truth"},
    ]

    scoped = _field_ocr_text("employer_name", blocks)

    assert "OCR COMPANY" in scoped
    assert "Ground Truth" not in scoped
