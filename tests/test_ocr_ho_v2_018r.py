from scripts.review_ocr_ho_v2_018r import review, validate_018p, validate_018q


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


def source_018q() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018q-recognizer-sublayer-selection/1.0.0",
        "taskId": "OCR-HO-V2-018Q",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "decision": {
            "selectedSubLayer": "PLACE_OF_RESIDENCE_RECOGNIZER_DISAGREEMENT",
            "selectorPathOpen": False,
            "counterfactualAuthorized": False,
            "profileSelectorAuthorized": False,
            "variantSelectorAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
        },
        "evidence": {
            "fieldCohorts": {
                "placeOfResidence": {
                    "recognizerDisagreementCount": 116,
                    "lineOrderMismatchCount": 32,
                    "tokenMismatchCount": 11,
                    "dominantErrorClass": "RECOGNIZER_DISAGREEMENT",
                }
            }
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


def group(rate: float, disagreement: int, errors: int, miss: int) -> dict:
    return {
        "autoRegionHit": {
            "errorGroupCount": errors,
            "recognizerDisagreementCount": disagreement,
            "lineOrderMismatchCount": 0,
            "tokenMismatchCount": 0,
        },
        "autoRegionMiss": {"errorGroupCount": miss},
        "recognizerDisagreementRateAmongHitErrors": rate,
    }


def source_018p() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018p-recognizer-token-attribution/1.0.0",
        "taskId": "OCR-HO-V2-018P",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_RECOGNIZER_TOKEN_ATTRIBUTION_ONLY",
        },
        "byField": {
            "placeOfResidence": {
                "classCounts": {
                    "RECOGNIZER_DISAGREEMENT": 116,
                    "LINE_ORDER_MISMATCH": 32,
                },
                "tokenMismatchCount": 11,
            }
        },
        "byProfile": {
            "easyocr_vi": group(0.88, 91, 103, 52),
            "vietocr_vgg_transformer": group(0.68, 57, 84, 72),
        },
        "byVariant": {
            "balanced_padding": group(0.76, 72, 94, 64),
            "lanczos_upscale": group(0.79, 76, 96, 60),
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


def test_keeps_global_profile_rates_descriptive_only() -> None:
    report = review(source_018q(), source_018p(), {})
    assert report["decision"]["status"] == "RESIDENCE_PROFILE_VARIANT_REVIEW_HOLD"
    assert report["decision"]["profileVariantWinner"] is None
    assert report["evidenceScope"]["residenceSpecificProfileVariantCrossTabAvailable"] is False
    assert report["decision"]["profileSelectorAuthorized"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_rejects_profile_selector_authorization() -> None:
    bad = source_018q()
    bad["decision"]["profileSelectorAuthorized"] = True
    try:
        validate_018q(bad)
    except SystemExit as exc:
        assert "broader" in str(exc)
    else:
        raise AssertionError("profile selector authorization must fail closed")


def test_rejects_missing_profile_aggregate() -> None:
    bad = source_018p()
    bad["byProfile"] = {}
    try:
        validate_018p(bad)
    except SystemExit as exc:
        assert "profile/variant aggregate" in str(exc)
    else:
        raise AssertionError("missing profile evidence must fail closed")
