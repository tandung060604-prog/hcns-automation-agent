from scripts.review_ocr_ho_v2_019f import close_path, validate_authorization, validate_source


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019e-quality-matrix-review/1.0.0",
        "taskId": "OCR-HO-V2-019E",
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
        "gtUsedForAttribution": False,
        "review": {
            "profileVariantRows": 16,
            "fieldQualityRows": 48,
            "allFieldNonRegressionPassRows": 0,
            "residence": {
                "oracleAsciiExactMax": 2,
                "gateQualifiedCombinationCount": 0,
            },
            "matrixSignatureCount": 16,
        },
        "decision": {
            "selectorEligible": False,
            "patchReviewEligible": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "promotionAllowed": False,
        },
        "gates": {
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
        },
    }


def authorization() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019f-profile-variant-closure-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-019F",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "containsRawPII": False,
        "sealedManifestSha256": "manifest-digest",
        "source019eSha256": "source-digest",
        "approval": {
            "approved": True,
            "approverRole": "OCR_REVIEW_OWNER",
            "localOnly": True,
            "aggregateProfileVariantClosureAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_close_path_requires_independent_reopen_evidence() -> None:
    payload = source()
    validate_source(payload)
    result = close_path(payload)
    assert result["selectionPath"]["status"] == "CLOSED"
    assert result["selectionPath"]["selectorEligible"] is False
    assert len(result["reopenRequirements"]) == 5
    assert result["closureBasis"]["fullNonRegressionPassRows"] == 0


def test_authorization_fails_closed_on_source_digest_and_selector() -> None:
    validate_authorization(authorization(), "source-digest", "manifest-digest")
    record = authorization()
    record["source019eSha256"] = "wrong"
    try:
        validate_authorization(record, "source-digest", "manifest-digest")
    except SystemExit as exc:
        assert "authorization record invalid" in str(exc)
    else:
        raise AssertionError("source digest mismatch must fail closed")

    record = authorization()
    record["approval"]["selectorChangeAuthorized"] = True
    try:
        validate_authorization(record, "source-digest", "manifest-digest")
    except SystemExit as exc:
        assert "prohibited authorization" in str(exc)
    else:
        raise AssertionError("selector authorization must fail closed")
