from scripts.review_ocr_ho_v2_018i import build_report, validate_record


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018h-selector-safety-evidence-review/1.0.0",
        "taskId": "OCR-HO-V2-018H",
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
        "readiness": {
            "counterfactualOpeningAllowed": False,
            "counterfactualAuthorized": False,
        },
        "decision": {"status": "SELECTOR_SAFETY_EVIDENCE_HOLD"},
    }


def test_missing_record_is_fail_closed() -> None:
    intake = validate_record(None, "sealed-digest")
    assert intake["status"] == "MISSING"
    assert intake["counterfactualAuthorized"] is False
    report = build_report(source(), "sealed-digest", None, None)
    assert report["decision"]["status"] == "SELECTOR_SAFETY_AUTHORIZATION_REQUIRED"
    assert report["gates"]["acceptedCoverage"] == 0


def test_valid_record_only_authorizes_safety_review() -> None:
    record = {
        "schemaVersion": "ocr-ho-v2-018i-selector-safety-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-018I",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "containsRawPII": False,
        "sourceArtifactSha256": "sealed-digest",
        "safetyScope": {
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
            "approvedAt": "2026-08-10T10:00:00Z",
            "localOnly": True,
            "selectorSafetyEvidenceAuthorized": True,
            "counterfactualAuthorized": False,
            "selectorChangeAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }
    intake = validate_record(record, "sealed-digest")
    assert intake["status"] == "VALID_FOR_SAFETY_REVIEW"
    report = build_report(source(), "sealed-digest", record, "record-digest")
    assert report["decision"]["status"] == "SELECTOR_SAFETY_AUTHORIZATION_ACCEPTED"
    assert report["decision"]["counterfactualAuthorized"] is False
