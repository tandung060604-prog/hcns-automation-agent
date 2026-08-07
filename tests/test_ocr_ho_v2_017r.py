from scripts.review_ocr_ho_v2_017r import evaluate_patch_gate


def source(overlap: float) -> dict[str, object]:
    return {
        "candidateRule": {
            "maxBottomExtensionPixels": 15,
            "preserveMaxValueLines": 2,
            "lineIdRemapping": False,
            "lineIdOverlapRateInEvidence": overlap,
        }
    }


def test_patch_gate_denies_rule_without_line_id_evidence() -> None:
    result = evaluate_patch_gate(source(0.0))
    assert result["boundedRuleGate"] == "PASS"
    assert result["independentLineIdEvidenceGate"] == "HOLD"
    assert result["patchAuthorized"] is False
    assert result["replayAuthorized"] is False


def test_patch_gate_is_explicitly_separable_from_rule_boundedness() -> None:
    result = evaluate_patch_gate(source(0.5))
    assert result["boundedRuleSatisfied"] is True
    assert result["lineIdEvidenceAvailable"] is True
    assert result["patchAuthorized"] is True
    assert result["replayAuthorized"] is False
