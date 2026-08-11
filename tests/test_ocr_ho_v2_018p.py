from scripts.review_ocr_ho_v2_018p import review, validate_018f, validate_018o


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
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
    }


def source_018o() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018o-layer-selection-review/1.0.0",
        "taskId": "OCR-HO-V2-018O",
        **scope(),
        "decision": {
            "selectedLayer": "RECOGNIZER_TOKEN_ALIGNMENT",
            "selectorPathOpen": False,
            "patchAuthorized": False,
            "replayAuthorized": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
        },
    }


def compact(
    classes: dict[str, int],
    *,
    groups: int,
    eligible: int,
    errors: int,
    dominant: str,
    rate: float,
    token: int,
    order: int,
    recognizer: int,
) -> dict:
    return {
        "groups": groups,
        "eligibleLineTokenGroups": eligible,
        "classCounts": classes,
        "errorGroupCount": errors,
        "dominantErrorClass": dominant,
        "dominantErrorRate": rate,
        "tokenMismatchCount": token,
        "lineOrderMismatchCount": order,
        "recognizerDisagreementCount": recognizer,
    }


def source_018f() -> dict:
    classes = {
        "LINE_ID_MISS": 0,
        "LINE_ORDER_MISMATCH": 72,
        "TOKEN_OMISSION": 0,
        "TOKEN_EXTRA": 8,
        "TOKEN_SWAP": 3,
        "DUPLICATE_LINE": 0,
        "RECOGNIZER_DISAGREEMENT": 291,
    }
    miss_classes = {key: 0 for key in classes}
    miss_classes["LINE_ID_MISS"] = 245
    hit = compact(
        classes,
        groups=430,
        eligible=357,
        errors=375,
        dominant="RECOGNIZER_DISAGREEMENT",
        rate=0.776,
        token=11,
        order=72,
        recognizer=291,
    )
    miss = compact(
        miss_classes,
        groups=245,
        eligible=0,
        errors=245,
        dominant="LINE_ID_MISS",
        rate=1.0,
        token=0,
        order=0,
        recognizer=0,
    )
    return {
        "schemaVersion": "ocr-ho-v2-018f-recognizer-token-attribution/1.0.0",
        "taskId": "OCR-HO-V2-018F",
        **scope(),
        "protocol": {"gate": "AUTO_DETECTOR", "diagnostic": "ORACLE_LINE_TOKEN_ATTRIBUTION_ONLY"},
        "tokenDefinition": "NFC-normalized whitespace-delimited tokens; no model token IDs",
        "lineage": {
            "automaticRoiReconciled": True,
            "boundaryPatchAuthorized": False,
            "replayExecuted": False,
        },
        "cohorts": {"AUTO_REGION_HIT": hit, "AUTO_REGION_MISS": miss},
        "byField": {"placeOfResidence": hit},
        "byProfile": {
            "easyocr_vi": {
                "autoRegionHit": hit,
                "autoRegionMiss": miss,
                "recognizerDisagreementRateAmongHitErrors": 0.88,
            }
        },
        "byVariant": {
            "balanced_padding": {
                "autoRegionHit": hit,
                "autoRegionMiss": miss,
                "recognizerDisagreementRateAmongHitErrors": 0.76,
            }
        },
        "attribution": {"autoRegionHit": {"parserContaminationSignalCountFrom017K": 10}},
        "decision": {
            "selectedLayer": "RECOGNIZER_TOKEN_ALIGNMENT",
            "runtimeChanged": False,
            "replayExecuted": False,
            "patchAuthorized": False,
            "counterfactualAuthorized": False,
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


def test_reports_aggregate_attribution_only() -> None:
    report = review(source_018o(), source_018f(), {})
    assert report["decision"]["status"] == "RECOGNIZER_TOKEN_ATTRIBUTION_HOLD"
    assert report["attribution"]["dominantErrorClass"] == "RECOGNIZER_DISAGREEMENT"
    assert report["attribution"]["dominantFieldByRecognizerDisagreement"] == "placeOfResidence"
    assert report["decision"]["counterfactualAuthorized"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_rejects_selector_opening() -> None:
    bad = source_018o()
    bad["decision"]["counterfactualAuthorized"] = True
    try:
        validate_018o(bad)
    except SystemExit as exc:
        assert "diagnostic-only" in str(exc)
    else:
        raise AssertionError("selector opening must fail closed")


def test_rejects_token_definition_change() -> None:
    bad = source_018f()
    bad["tokenDefinition"] = "model token IDs"
    try:
        validate_018f(bad)
    except SystemExit as exc:
        assert "token definition" in str(exc)
    else:
        raise AssertionError("token definition must fail closed")
