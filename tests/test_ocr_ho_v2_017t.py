from scripts.review_ocr_ho_v2_017t import reconcile_gate


def rule() -> dict[str, object]:
    return {
        "candidateRule": {
            "maxBottomExtensionPixels": 15,
            "preserveMaxValueLines": 2,
            "lineIdRemapping": False,
        },
        "gateReview": {
            "boundedRuleGate": "PASS",
            "independentLineIdEvidenceGate": "HOLD",
        },
    }


def evidence(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "evidenceAssessment": {
            "lineIdEvidenceGate": "PASS",
            "independentSourceAvailable": True,
            "independentDocumentCoverage": 15,
            "independentLineIdOverlapCount": 61,
            "independentLineIdOverlapRate": 1.0,
        },
        "sourceInventory": {
            "independentFromCandidate": True,
            "rawTextConsumed": False,
        },
    }
    payload.update(overrides)
    return payload


def test_reconciliation_requires_both_rule_and_independent_evidence() -> None:
    result = reconcile_gate(rule(), evidence())
    assert result["reconciliationGate"] == "PASS"
    assert result["boundedRuleGate"] == "PASS"
    assert result["independentLineIdEvidenceGate"] == "PASS"
    assert result["qualityImprovementProven"] is False
    assert result["explicitPatchApproval"] == "REQUIRED"
    assert result["patchAuthorized"] is False
    assert result["replayAuthorized"] is False


def test_zero_overlap_keeps_patch_gate_closed() -> None:
    source = evidence()
    source["evidenceAssessment"]["independentLineIdOverlapCount"] = 0
    source["evidenceAssessment"]["independentLineIdOverlapRate"] = 0.0
    result = reconcile_gate(rule(), source)
    assert result["independentLineIdEvidenceGate"] == "HOLD"
    assert result["reconciliationGate"] == "HOLD"
    assert result["patchAuthorized"] is False


def test_rule_remapping_or_unbounded_extension_keeps_gate_closed() -> None:
    source_rule = rule()
    source_rule["candidateRule"]["maxBottomExtensionPixels"] = 16
    source_rule["candidateRule"]["lineIdRemapping"] = True
    result = reconcile_gate(source_rule, evidence())
    assert result["boundedRuleGate"] == "HOLD"
    assert result["reconciliationGate"] == "HOLD"
    assert result["replayAuthorized"] is False
