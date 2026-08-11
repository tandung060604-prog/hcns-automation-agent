from scripts.review_ocr_ho_v2_018n import review, validate_source


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018m-selector-counterfactual-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-018M",
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
        "gtUsedForScoring": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "SELECTOR_ONLY_PROFILE_WEIGHTED_CONSENSUS_SEALED_AGGREGATE",
        },
        "authorization": {
            "counterfactualExecutionAuthorized": True,
            "selectorChangeAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
        "execution": {
            "counterfactualExecuted": True,
            "ocrRerun": False,
            "replayExecuted": False,
            "selectorChanged": False,
            "runtimeChanged": False,
        },
        "counterfactual": {
            "delta": {
                "der": 0.007905,
                "diacriticErrorCount": 2,
                "strictExactCount": -1,
            },
            "changedFieldCount": 2,
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
        "decision": {"status": "COUNTERFACTUAL_DIAGNOSTIC_COMPLETE_HOLD"},
    }


def test_closes_selector_path_on_regression() -> None:
    report = review(source(), "018m-digest")
    assert report["decision"]["status"] == "SELECTOR_PATH_CLOSED_HOLD"
    assert report["decision"]["selectorPathOpen"] is False
    assert report["decision"]["counterfactualAuthorized"] is False
    assert report["evidence"]["regression"]["qualityNonRegression"] == "FAIL"
    assert report["gates"]["acceptedCoverage"] == 0


def test_rejects_runtime_change() -> None:
    bad = source()
    bad["execution"]["runtimeChanged"] = True
    try:
        validate_source(bad)
    except SystemExit as exc:
        assert "execution boundary" in str(exc)
    else:
        raise AssertionError("runtime change must fail closed")


def test_rejects_broader_authorization() -> None:
    bad = source()
    bad["authorization"]["selectorChangeAuthorized"] = True
    try:
        validate_source(bad)
    except SystemExit as exc:
        assert "broader" in str(exc)
    else:
        raise AssertionError("selector change authorization must fail closed")
