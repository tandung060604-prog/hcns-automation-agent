from scripts.review_ocr_ho_v2_018m import review, validate_lineage


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018l-selector-counterfactual-authorization-intake/1.0.0",
        "taskId": "OCR-HO-V2-018L",
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
            "diagnostic": "EXPLICIT_SELECTOR_COUNTERFACTUAL_AUTHORIZATION_INTAKE_ONLY",
        },
        "sourceDigests": {"artifact018kSha256": "k"},
        "authorizationIntake": {
            "status": "VALID_FOR_COUNTERFACTUAL_REVIEW",
            "sourceArtifactMatch": True,
            "scopeMatch": True,
            "selectorCounterfactualAuthorized": True,
            "selectorChangeAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
        "decision": {
            "counterfactualAuthorized": True,
            "counterfactualExecutionAllowed": False,
            "counterfactualExecuted": False,
        },
    }


def test_review_does_not_infer_execution_authority() -> None:
    report = review(source(), "l", "k")
    assert report["decision"]["status"] == "COUNTERFACTUAL_EXECUTION_AUTHORIZATION_REQUIRED"
    assert report["authorizationEvidence"]["counterfactualAuthorized"] is True
    assert report["decision"]["counterfactualExecutionAuthorized"] is False
    assert report["decision"]["counterfactualExecuted"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_lineage_rejects_execution_opened_in_018l() -> None:
    bad = source()
    bad["decision"]["counterfactualExecutionAllowed"] = True
    try:
        validate_lineage(bad, "k")
    except SystemExit as exc:
        assert "execution-closed" in str(exc)
    else:
        raise AssertionError("018L execution authorization must fail closed")
