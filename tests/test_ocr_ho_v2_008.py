import json
import os
import sys
from pathlib import Path

from jsonschema import validate

sys.path.insert(0, os.path.abspath("apps/ocr_lab/api"))

import phase11_8_cccd_v2 as candidate  # noqa: E402


def _candidate(value: str, profile: str, confidence: float = 0.9) -> dict:
    return {
        "value": value,
        "rawValue": value,
        "profile": profile,
        "confidence": confidence,
    }


def test_token_consensus_restores_origin_separators() -> None:
    result = candidate.select_address_candidate(
        "placeOfOrigin",
        [
            _candidate("Alpha Commune Beta District Gamma Province", "paddle_ppocrv5"),
            _candidate(
                "Alpha Commune Beta District Gamma Province",
                "vietocr_vgg_transformer",
            ),
        ],
        bbox=[0, 0, 100, 100],
    )

    assert result["status"] == "needs_review"
    assert result["validation"]["tokenConsensus"] is True
    assert result["value"].count(",") == 2


def test_weak_token_consensus_is_not_selected() -> None:
    result = candidate.select_address_candidate(
        "placeOfOrigin",
        [
            _candidate("Alpha Commune Beta District", "paddle_ppocrv5"),
            _candidate("Gamma Ward Delta City", "vietocr_vgg_transformer"),
        ],
        bbox=[0, 0, 100, 100],
    )

    assert result["value"] is None
    assert result["selectionMode"] == "phase11_8_no_token_consensus"


def test_candidate_card_is_shadow_manual_review() -> None:
    fields = {name: {} for name in candidate.FIELD_ORDER}
    card = candidate.build_identity_card(
        {name: [] for name in candidate.FIELD_ORDER},
        {},
        baseline_fields=fields,
    )

    assert card["summary"]["candidateVersion"] == candidate.CANDIDATE_VERSION
    assert card["policyMode"] == "SHADOW_REVIEW_ONLY"
    assert all(field["status"] != "accepted" for field in card["fields"].values())


def test_candidate_card_matches_locked_schema() -> None:
    schema_path = Path("schemas/vietnam_identity_card_phase11_6.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    fields = {name: {} for name in candidate.FIELD_ORDER}
    card = candidate.build_identity_card(
        {name: [] for name in candidate.FIELD_ORDER},
        {},
        baseline_fields=fields,
    )

    validate(card, schema)
