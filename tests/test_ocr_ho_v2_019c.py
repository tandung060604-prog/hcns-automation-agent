from scripts.review_ocr_ho_v2_019c import review, signature_review, validate_authorization


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


def source() -> dict:
    rows = []
    for profile in ("p1", "p2"):
        for variant in ("v1", "v2"):
            rows.extend(
                [
                    {
                        "profile": profile,
                        "variant": variant,
                        "boundaryCategory": "bottom_boundary",
                        "lineIdMissGroups": 3,
                    },
                    {
                        "profile": profile,
                        "variant": variant,
                        "boundaryCategory": "line_order",
                        "lineIdMissGroups": 1,
                    },
                    {
                        "profile": profile,
                        "variant": variant,
                        "boundaryCategory": "multiple_boundary_sides",
                        "lineIdMissGroups": 1,
                    },
                ]
            )
    return {
        "schemaVersion": (
            "ocr-ho-v2-019b-independent-residence-boundary-profile-variant-crosstab/1.0.0"
        ),
        "taskId": "OCR-HO-V2-019B",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "crossTab": {
            "available": True,
            "rows": rows,
            "profileVariantCombinationCount": 4,
            "profileVariantDocumentGroups": 60,
            "lineIdClassTotals": {"LINE_ID_MISS": 20},
            "boundaryAttributedLineIdMissGroups": 20,
        },
    }


def authorization() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019c-independent-cross-tab-review-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-019C",
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
            "aggregateCrossTabReviewAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_identical_signatures_are_nondiscriminative() -> None:
    result = signature_review(source()["crossTab"]["rows"])
    assert result["combinationCount"] == 4
    assert result["signatureCount"] == 1
    assert result["discriminative"] is False
    report = review(source(), {})
    assert report["decision"]["profileVariantWinner"] is None
    assert report["decision"]["patchReviewEligible"] is False
    assert report["decision"]["nextTask"] == "OCR-HO-V2-019D"


def test_authorization_fails_closed_on_digest_and_selector() -> None:
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
