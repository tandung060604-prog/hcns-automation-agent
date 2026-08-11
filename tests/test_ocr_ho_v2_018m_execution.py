from scripts.execute_ocr_ho_v2_018m import execute, validate_017d, validate_execution_record


def source_018l() -> dict:
    return {
        "authorizationIntake": {"status": "VALID_FOR_COUNTERFACTUAL_REVIEW"}
    }


def source_017d() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-017d-selector-counterfactual/1.0.0",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
        "targetFields": ["fullName", "placeOfOrigin", "placeOfResidence"],
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "protocols": {
            "gate": "AUTO_DETECTOR",
            "counterfactual": "SELECTOR_ONLY_PROFILE_WEIGHTED_CONSENSUS",
        },
        "metrics": {
            "selected_11_10_2": {
                "strictExactCount": 76,
                "asciiExactCount": 90,
                "cer": 0.16,
                "der": 0.162055,
                "diacriticErrorCount": 41,
                "referenceDiacriticCount": 253,
            },
            "counterfactual_017d": {
                "strictExactCount": 75,
                "asciiExactCount": 90,
                "cer": 0.17,
                "der": 0.16996,
                "diacriticErrorCount": 43,
                "referenceDiacriticCount": 253,
            },
        },
        "selectionDiagnostics": {
            "fullName": {"changed": 1, "counterfactualSelected": 10, "fallbackCurrent": 5},
            "placeOfOrigin": {"changed": 1, "counterfactualSelected": 4, "fallbackCurrent": 11},
            "placeOfResidence": {"changed": 0, "counterfactualSelected": 3, "fallbackCurrent": 12},
        },
    }


def valid_record() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018m-counterfactual-execution-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-018M",
        "containsRawPII": False,
        "sourceArtifactSha256": "l",
        "executionScope": {
            "datasetFamily": "CCCD",
            "datasetId": "DATA-HO-014",
            "datasetRole": "DEVELOPMENT_REGRESSION",
            "documentCount": 15,
            "evaluatedFieldCount": 120,
            "diagnosticFieldCount": 45,
            "candidateVersion": "11.10.2",
            "baselineVersion": "11.9.1",
            "protocol": "AUTO_DETECTOR",
        },
        "approval": {
            "approved": True,
            "approverRole": "OCR_REVIEW_OWNER",
            "approvedAt": "2026-08-10T12:00:00Z",
            "localOnly": True,
            "counterfactualExecutionAuthorized": True,
            "selectorChangeAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_sealed_counterfactual_reports_regression() -> None:
    report = execute(
        source_018l(),
        source_017d(),
        {
            "artifact018lSha256": "l",
            "executionAuthorizationSha256": "a",
            "artifact018kSha256": "k",
            "artifact017dSha256": "d",
        },
    )
    assert report["execution"]["counterfactualExecuted"] is True
    assert report["execution"]["ocrRerun"] is False
    assert report["execution"]["replayExecuted"] is False
    assert report["counterfactual"]["delta"]["der"] == 0.007905
    assert report["decision"]["status"] == "COUNTERFACTUAL_DIAGNOSTIC_COMPLETE_HOLD"
    assert report["gates"]["acceptedCoverage"] == 0


def test_execution_record_rejects_broader_permission() -> None:
    record = valid_record()
    record["approval"]["selectorChangeAuthorized"] = True
    try:
        validate_execution_record(record, "l")
    except SystemExit as exc:
        assert "invalid or broader" in str(exc)
    else:
        raise AssertionError("broader execution permission must fail closed")


def test_017d_validation_rejects_ground_truth_selection() -> None:
    source = source_017d()
    source["gtUsedAtSelection"] = True
    try:
        validate_017d(source)
    except SystemExit as exc:
        assert "Ground Truth" in str(exc)
    else:
        raise AssertionError("Ground Truth at selection must fail closed")
