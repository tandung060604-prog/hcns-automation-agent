from scripts.intake_ocr_ho_v2_018l import build_report, validate_record, validate_source


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018k-selector-safety-decision-review/1.0.0",
        "taskId": "OCR-HO-V2-018K",
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
            "diagnostic": "AGGREGATE_SELECTOR_SAFETY_DECISION_REVIEW_ONLY",
        },
        "decision": {
            "status": "SELECTOR_COUNTERFACTUAL_NOT_RECOMMENDED_HOLD",
            "counterfactualRecommended": False,
            "counterfactualOpeningAllowed": False,
            "counterfactualAuthorized": False,
        },
    }


def valid_record() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018l-selector-counterfactual-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-018L",
        "containsRawPII": False,
        "sourceArtifactSha256": "sealed-digest",
        "counterfactualScope": {
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
            "selectorCounterfactualAuthorized": True,
            "selectorChangeAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_missing_record_is_fail_closed() -> None:
    intake = validate_record(None, "sealed-digest")
    assert intake["status"] == "MISSING"
    report = build_report(source(), "sealed-digest", None, None)
    assert report["decision"]["status"] == "COUNTERFACTUAL_AUTHORIZATION_REQUIRED"
    assert report["decision"]["counterfactualAuthorized"] is False
    assert report["decision"]["counterfactualExecuted"] is False


def test_valid_record_authorizes_review_only() -> None:
    record = valid_record()
    intake = validate_record(record, "sealed-digest")
    assert intake["status"] == "VALID_FOR_COUNTERFACTUAL_REVIEW"
    report = build_report(source(), "sealed-digest", record, "record-digest")
    assert report["decision"]["status"] == "COUNTERFACTUAL_AUTHORIZATION_ACCEPTED_FOR_REVIEW"
    assert report["decision"]["counterfactualAuthorized"] is True
    assert report["decision"]["counterfactualExecutionAllowed"] is False
    assert report["decision"]["counterfactualExecuted"] is False


def test_broader_selector_change_fails_closed() -> None:
    record = valid_record()
    record["approval"]["selectorChangeAuthorized"] = True
    intake = validate_record(record, "sealed-digest")
    assert intake["status"] == "INVALID"


def test_source_rejects_open_counterfactual() -> None:
    bad = source()
    bad["decision"]["counterfactualAuthorized"] = True
    try:
        validate_source(bad)
    except SystemExit as exc:
        assert "counterfactual closed" in str(exc)
    else:
        raise AssertionError("open counterfactual must fail closed")
