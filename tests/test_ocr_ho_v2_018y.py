from scripts.review_ocr_ho_v2_018y import (
    review,
    validate_018w,
    validate_018x,
    validate_authorization,
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


def authorization() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018y-class-distribution-review-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-018Y",
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
            "aggregateClassDistributionReviewAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def source_x() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018x-sealed-joint-table-review/1.0.0",
        "taskId": "OCR-HO-V2-018X",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "review": {
            "combinationCount": 16,
            "evaluatedDocumentsPerCombination": 15,
            "totalProfileVariantDocumentGroups": 240,
            "classTotals": {
                "LINE_ID_MISS": 81,
                "LINE_ORDER_MISMATCH": 32,
                "TOKEN_OMISSION": 0,
                "TOKEN_EXTRA": 8,
                "TOKEN_SWAP": 3,
                "DUPLICATE_LINE": 0,
                "RECOGNIZER_DISAGREEMENT": 116,
            },
            "rawValuesReviewed": False,
        },
        "decision": {
            "profileVariantWinner": None,
            "selectionEligible": False,
            "selectorChanged": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
        },
    }


def source_w() -> dict:
    rows = [
        {
            "classCounts": {
                "LINE_ID_MISS": 5,
                "LINE_ORDER_MISMATCH": 2,
                "TOKEN_OMISSION": 0,
                "TOKEN_EXTRA": 0,
                "TOKEN_SWAP": 0,
                "DUPLICATE_LINE": 0,
                "RECOGNIZER_DISAGREEMENT": 8,
            },
            "evaluatedDocuments": 15,
        }
        for _ in range(16)
    ]
    return {
        "schemaVersion": (
            "ocr-ho-v2-018w-sealed-joint-residence-profile-variant-error-class-extractor/1.0.0"
        ),
        "taskId": "OCR-HO-V2-018W",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "jointEvidence": {"rows": rows},
        "decision": {"profileVariantWinner": None},
    }


def test_selects_one_bounded_line_id_diagnostic() -> None:
    validate_018x(source_x())
    validate_018w(source_w())
    report = review(source_x(), source_w(), {})
    assert report["decision"]["selectedDiagnostic"] == "RESIDENCE_LINE_ID_MISS_BOUNDARY_ATTRIBUTION"
    assert report["distribution"]["lineIdMissRows"] == 16
    assert report["decision"]["selectionEligible"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_no_global_class_reaches_half() -> None:
    report = review(source_x(), source_w(), {})
    assert report["distribution"]["global50PercentThresholdReached"] is False
    assert report["decision"]["profileVariantWinner"] is None


def test_rejects_changed_class_distribution() -> None:
    bad = source_x()
    bad["review"]["classTotals"]["LINE_ID_MISS"] = 80
    try:
        validate_018x(bad)
    except SystemExit as exc:
        assert "class distribution" in str(exc)
    else:
        raise AssertionError("changed distribution must fail closed")


def test_authorization_requires_matching_manifest_digest() -> None:
    validate_authorization(authorization(), "manifest-digest")
    record = authorization()
    record["sealedManifestSha256"] = "wrong-digest"
    try:
        validate_authorization(record, "manifest-digest")
    except SystemExit as exc:
        assert "authorization record invalid" in str(exc)
    else:
        raise AssertionError("manifest digest mismatch must fail closed")


def test_authorization_rejects_selector_permission() -> None:
    record = authorization()
    record["approval"]["selectorChangeAuthorized"] = True
    try:
        validate_authorization(record, "manifest-digest")
    except SystemExit as exc:
        assert "prohibited authorization" in str(exc)
    else:
        raise AssertionError("selector authorization must fail closed")
