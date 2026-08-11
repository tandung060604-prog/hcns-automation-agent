from scripts.intake_ocr_ho_v2_018v import build_report, validate_record, validate_source


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018u-residence-error-class-attribution/1.0.0",
        "taskId": "OCR-HO-V2-018U",
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
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_RESIDENCE_ERROR_CLASS_ATTRIBUTION_ONLY",
        },
        "evidence": {
            "attributionBoundary": {
                "profileVariantErrorClassCrossTabAvailable": False
            }
        },
        "decision": {
            "selectedDiagnostic": "RESIDENCE_RECOGNIZER_ERROR_CLASS_ATTRIBUTION",
            "profileSelectorAuthorized": False,
            "variantSelectorAuthorized": False,
            "counterfactualAuthorized": False,
            "selectorPathOpen": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
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
    }


def valid_record() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018v-profile-variant-error-class-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-018V",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "containsRawPII": False,
        "sourceArtifactSha256": "sealed-digest",
        "reviewScope": {
            "protocol": "AUTO_DETECTOR",
            "review": "AGGREGATE_PROFILE_VARIANT_BY_ERROR_CLASS_ONLY",
            "targetField": "placeOfResidence",
            "selectedErrorClass": "RECOGNIZER_DISAGREEMENT",
            "profileVariantSelectorChange": False,
        },
        "approval": {
            "approved": True,
            "approverRole": "OCR_REVIEW_OWNER",
            "approvedAt": "2026-08-10T12:00:00Z",
            "localOnly": True,
            "aggregateProfileVariantErrorClassReviewAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_missing_authorization_is_fail_closed() -> None:
    validate_source(source())
    intake = validate_record(None, "sealed-digest")
    assert intake["status"] == "MISSING"
    report = build_report(source(), "sealed-digest", None, None)
    assert report["decision"]["status"] == "PROFILE_VARIANT_ERROR_CLASS_AUTHORIZATION_REQUIRED"
    assert report["decision"]["evidenceReviewExecuted"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_valid_record_authorizes_review_only() -> None:
    intake = validate_record(valid_record(), "sealed-digest")
    assert intake["status"] == "VALID_FOR_PROFILE_VARIANT_ERROR_CLASS_REVIEW"
    report = build_report(source(), "sealed-digest", valid_record(), "record-digest")
    assert report["decision"]["status"] == "PROFILE_VARIANT_ERROR_CLASS_AUTHORIZATION_ACCEPTED"
    assert report["decision"]["nextTask"] == "OCR-HO-V2-018W"
    assert report["decision"]["counterfactualAuthorized"] is False
    assert report["decision"]["evidenceReviewExecuted"] is False


def test_prohibited_selector_authorization_is_invalid() -> None:
    record = valid_record()
    record["approval"]["selectorChangeAuthorized"] = True
    intake = validate_record(record, "sealed-digest")
    assert intake["status"] == "INVALID"
    assert intake["selectorChangeAuthorized"] is False
