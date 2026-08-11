from scripts.analyze_ocr_ho_v2_019d import (
    classify_line_ids,
    compare_to_baseline,
    metric_summary,
    validate_authorization,
)


def authorization() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019d-per-profile-quality-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-019D",
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
            "aggregatePerProfileQualityAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_quality_summary_is_aggregate_only_and_baseline_comparison_is_explicit() -> None:
    summary = metric_summary([("Đà Nẵng", "Đà Nẵng"), ("Hà Nội", "Ha Noi")])
    assert summary["evaluated"] == 2
    assert summary["strictExactCount"] == 1
    assert summary["asciiExactCount"] == 2
    assert set(summary) == {
        "evaluated",
        "strictExactCount",
        "asciiExactCount",
        "characterErrorCount",
        "referenceCharacterCount",
        "diacriticErrorCount",
        "referenceDiacriticCount",
        "strictExactMatch",
        "asciiExactMatch",
        "cer",
        "der",
    }
    comparison = compare_to_baseline(
        {"oracleBest": summary},
        {"strictExactMatch": 0.5, "asciiExactMatch": 1.0, "cer": 0.5, "der": 0.5},
    )
    assert comparison == {
        "strictNotWorse": True,
        "asciiNotWorse": True,
        "cerNotWorse": True,
        "derNotWorse": True,
    }


def test_line_quality_classification_is_deterministic() -> None:
    assert classify_line_ids((12, 13), [{"lineIds": [12]}, {"lineIds": [13]}]) == "LINE_ID_MATCH"
    assert classify_line_ids((12, 13), [{"lineIds": [12]}]) == "LINE_ID_MISS"
    assert (
        classify_line_ids(
            (12, 13),
            [{"lineIds": [13], "lineOrder": 0}, {"lineIds": [12], "lineOrder": 1}],
        )
        == "LINE_ORDER_MISMATCH"
    )
    assert (
        classify_line_ids((12, 13), [{"lineIds": [12]}, {"lineIds": [12, 13]}]) == "DUPLICATE_LINE"
    )


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
