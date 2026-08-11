from scripts.review_ocr_ho_v2_018k import review, validate_source


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018j-aggregate-selector-safety-evidence/1.0.0",
        "taskId": "OCR-HO-V2-018J",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_SELECTOR_SAFETY_EVIDENCE_ONLY",
        },
        "readiness": {
            "safetyEvidenceCollected": True,
            "independentSafetyEvidenceReady": False,
            "selectorCounterfactualOpeningAllowed": False,
            "counterfactualAuthorized": False,
        },
        "gates": {
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
            "productionPromotionAllowed": False,
        },
        "evidence": {
            "priorNonRegression": {
                "status": "FAIL",
                "derDelta": 0.007905,
                "diacriticErrorDelta": 2,
                "strictExactDelta": -1,
            },
            "eligibleSwitch": {
                "status": "FAIL",
                "eligibleSwitchCount": 0,
                "changedFieldCount": 0,
            },
            "replayChange": {
                "status": "FAIL",
                "eligibleSwitchCount": 0,
                "changedFieldCount": 0,
            },
            "safetyInvariants": {
                "status": "PASS",
                "schemaErrors": 0,
                "sensitiveFalseAcceptance": 0,
                "acceptedCoverage": 0,
                "manualReviewOnly": True,
            },
        },
    }


def test_counterfactual_is_not_recommended() -> None:
    report = review(source(), "018j-digest")
    assert report["decision"]["status"] == "SELECTOR_COUNTERFACTUAL_NOT_RECOMMENDED_HOLD"
    assert report["decision"]["counterfactualRecommended"] is False
    assert report["decision"]["counterfactualOpeningAllowed"] is False
    assert report["decision"]["ownerAuthorizationRequired"] is True
    assert report["gates"]["acceptedCoverage"] == 0


def test_source_fails_closed_if_counterfactual_is_open() -> None:
    bad = source()
    bad["readiness"]["counterfactualAuthorized"] = True
    try:
        validate_source(bad)
    except SystemExit as exc:
        assert "counterfactual-closed" in str(exc)
    else:
        raise AssertionError("counterfactual authorization must fail closed")
