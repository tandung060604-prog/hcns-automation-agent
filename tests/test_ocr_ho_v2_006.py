from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_cccd_ocr_ho_v2_006 import build_gate  # noqa: E402
from phase11_5_cccd import FIELD_ORDER  # noqa: E402
from phase11_6_cccd_v2 import (  # noqa: E402
    CANDIDATE_VERSION,
    TARGET_FIELDS,
    build_identity_card,
    locate_field_regions,
)


def _candidate(value: str, profile: str, confidence: float = 0.9) -> dict:
    return {
        "value": value,
        "rawValue": value,
        "profile": profile,
        "confidence": confidence,
        "variant": "lanczos_upscale",
    }


def test_v2_splits_sex_and_nationality_roi_windows() -> None:
    regions = locate_field_regions([], [(1000, 1000)])
    sex = regions["sex"]["bbox"]
    nationality = regions["nationality"]["bbox"]
    assert sex[2] <= nationality[0]
    assert regions["sex"]["regionSource"] == "phase11_6_v2_split_shared_row"
    assert regions["nationality"]["regionSource"] == "phase11_6_v2_split_shared_row"


def test_v2_output_keeps_schema_and_manual_review() -> None:
    values = {
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
            _candidate(value, "paddle_ppocrv5"),
            _candidate(value, "vietocr_vgg_seq2seq"),
        ]
        for field_name, value in values.items()
    }
    regions = {
        name: {"pageIndex": 0, "bbox": [10, 20, 300, 80]}
        for name in FIELD_ORDER
    }
    payload = build_identity_card(candidates, regions, baseline_fields={})
    schema = json.loads(
        (ROOT / "schemas" / "vietnam_identity_card_phase11_6.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validate(payload, schema)
    assert payload["summary"]["candidateVersion"] == CANDIDATE_VERSION
    assert set(payload["summary"]["targetFields"]) == set(TARGET_FIELDS)
    assert all(field["status"] != "accepted" for field in payload["fields"].values())


def test_v2_recovers_only_an_unsafe_baseline_target() -> None:
    candidates = {
        "placeOfOrigin": [
            _candidate("Cà Mau", "easyocr_vi"),
            _candidate("Cà Mau", "vietocr_vgg_seq2seq"),
        ]
    }
    baseline = {
        "placeOfOrigin": {
            "value": "Quê quán / Place of origin: Cà Mau Nơi thường trú",
            "asciiValue": None,
            "status": "needs_review",
            "asciiStatus": "needs_review",
            "confidence": 0.3,
            "errorSignals": ["label_contamination"],
            "selectionMode": "phase11_6_single_candidate",
            "evidence": {"pageIndex": 0, "bbox": [], "candidates": []},
        }
    }
    regions = {
        name: {"pageIndex": 0, "bbox": [10, 20, 300, 80]}
        for name in FIELD_ORDER
    }
    payload = build_identity_card(candidates, regions, baseline_fields=baseline)
    field = payload["fields"]["placeOfOrigin"]
    assert field["value"] == "Cà Mau"
    assert field["status"] == "needs_review"
    assert field["selectionMode"] == "phase11_6_single_candidate"
    assert field["shadowRecovery"]["guardedRecoveryApplied"] is True


def test_development_gate_requires_an_exact_improvement() -> None:
    fields = {
        name: {"value": "synthetic", "status": "needs_review"}
        for name in FIELD_ORDER
    }
    document = {
        "groundTruth": {name: {"value": "different"} for name in FIELD_ORDER},
        "phase11_5": fields,
        "ocr_ho_v2_006": fields,
    }
    metrics = {
        "strictFieldExactMatch": 0.6,
        "asciiFieldExactMatch": 0.6,
        "cer": 0.4,
        "der": 0.1,
        "fieldPresence": 1.0,
    }
    gate = build_gate(metrics, metrics, [document], 0)
    assert gate["status"] == "DEVELOPMENT_FAIL"
    assert gate["checks"]["hasExactImprovement"] is False
    assert gate["checks"]["manualReviewPolicy"] is True
