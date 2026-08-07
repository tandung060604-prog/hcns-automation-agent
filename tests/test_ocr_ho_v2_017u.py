from scripts.review_ocr_ho_v2_017u import build_report, review_authorization


def source(reconciliation: str = "PASS") -> dict[str, object]:
    return {
        "schemaVersion": "ocr-ho-v2-017t-patch-gate-reconciliation/1.0.0",
        "taskId": "OCR-HO-V2-017T",
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
        "protocol": {"diagnostic": "RESIDENCE_GEOMETRY_PATCH_GATE_RECONCILIATION_ONLY"},
        "candidateRule": {
            "name": "GEOMETRY_REGION_BOTTOM_EXTEND_TO_OBSERVED_LINE_BBOX",
            "field": "placeOfResidence",
            "maxBottomExtensionPixels": 15,
            "preserveMaxValueLines": 2,
            "lineIdRemapping": False,
        },
        "gateReview": {
            "reconciliationGate": reconciliation,
            "qualityImprovementProven": False,
        },
    }


def test_missing_authorization_fails_closed_after_reconciliation() -> None:
    result = review_authorization(source())
    assert result["reconciliationGate"] == "PASS"
    assert result["authorizationRecordProvided"] is False
    assert result["authorizationStatus"] == "MISSING"
    assert result["explicitPatchApprovalRequired"] is True
    assert result["patchAuthorized"] is False
    assert result["replayAuthorized"] is False


def test_unreconciled_source_cannot_open_authorization() -> None:
    result = review_authorization(source("HOLD"))
    assert result["reconciliationGate"] == "HOLD"
    assert result["patchReviewAuthorized"] is False


def test_report_keeps_all_fields_manual_review_and_no_promotion() -> None:
    report = build_report(source(), "digest")
    assert report["decision"]["status"] == "PATCH_AUTHORIZATION_REQUIRED"
    assert report["decision"]["recommendedNextTask"] == "OCR-HO-V2-017V"
    assert report["gates"]["developmentRegressionGate"] == "HOLD"
    assert report["gates"]["acceptedCoverage"] == 0
    assert report["gates"]["manualReviewOnly"] is True
    assert report["gates"]["productionPromotionAllowed"] is False
