from scripts.review_ocr_ho_v2_019a import (
    review,
    validate_authorization,
    validate_sources,
)


def scope() -> dict:
    return {
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
    }


def source_018z() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018z-residence-line-id-boundary-attribution/1.0.0",
        "taskId": "OCR-HO-V2-018Z",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "decision": {"patchAuthorized": False},
        "attribution": {
            "residenceBoundary": {"boundaryMissCases": 5},
            "crossTabAvailable": False,
        },
        "geometryCorroboration": {
            "globalDominantBoundaryRate": 0.444444,
            "globalPatchThresholdReached": False,
        },
    }


def source_018a() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018a-shadow-patch-review/1.0.0",
        "taskId": "OCR-HO-V2-018A",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "review": {
            "primaryRuntimeChanged": False,
            "qualityImprovementProven": False,
        },
    }


def source_018c() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018c-development-replay/1.0.0",
        "taskId": "OCR-HO-V2-018C",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "roiDiagnostics": {
            "automaticDetector": {"placeOfResidence": {"accuracy": 0.666667}}
        },
        "gates": {
            "developmentRegressionGate": {
                "status": "HOLD",
                "checks": {
                    "derNotWorse": False,
                    "residenceAsciiExactMatch": False,
                },
            }
        },
    }


def authorization() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019a-residence-patch-review-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-019A",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "containsRawPII": False,
        "sealedManifestSha256": "manifest-digest",
        "approval": {
            "approved": True,
            "approverRole": "OCR_REVIEW_OWNER",
            "localOnly": True,
            "aggregateResidencePatchReviewAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_patch_review_stays_closed_after_der_and_cross_tab_failures() -> None:
    sources = (source_018z(), source_018a(), source_018c())
    validate_sources(*sources)
    report = review(*sources, {})
    assert report["decision"]["status"] == "PATCH_REVIEW_NOT_WARRANTED_HOLD"
    assert report["decision"]["patchReviewEligible"] is False
    assert report["decision"]["patchAuthorizationIssued"] is False
    assert report["decision"]["recommendedNextTask"] == "OCR-HO-V2-019B"
    assert report["gates"]["acceptedCoverage"] == 0


def test_der_regression_drift_fails_closed() -> None:
    bad = source_018c()
    bad["gates"]["developmentRegressionGate"]["checks"]["derNotWorse"] = True
    try:
        validate_sources(source_018z(), source_018a(), bad)
    except SystemExit as exc:
        assert "DER non-regression" in str(exc)
    else:
        raise AssertionError("DER drift must fail closed")


def test_authorization_requires_matching_digest_and_no_selector() -> None:
    validate_authorization(authorization(), "manifest-digest")
    record = authorization()
    record["sealedManifestSha256"] = "wrong"
    try:
        validate_authorization(record, "manifest-digest")
    except SystemExit as exc:
        assert "authorization record invalid" in str(exc)
    else:
        raise AssertionError("digest mismatch must fail closed")

    record = authorization()
    record["approval"]["selectorChangeAuthorized"] = True
    try:
        validate_authorization(record, "manifest-digest")
    except SystemExit as exc:
        assert "prohibited authorization" in str(exc)
    else:
        raise AssertionError("selector authorization must fail closed")
