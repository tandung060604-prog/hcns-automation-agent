from scripts.review_ocr_ho_v2_018u import review, validate_018p, validate_018t


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


def source_018t() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018t-bounded-non-selector-diagnostic-selection/1.0.0",
        "taskId": "OCR-HO-V2-018T",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_BOUNDED_NON_SELECTOR_SELECTION_ONLY",
        },
        "evidence": {
            "crossTabCeiling": {
                "combinationCount": 16,
                "evaluatedPerCombination": 15,
                "gateAsciiExactCount": 13,
                "profileOracleBestMaxAsciiExactCount": 2,
                "variantOracleBestMaxAsciiExactCount": 2,
                "profileOrVariantReachesGate": False,
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


def source_018p() -> dict:
    classes = {
        "LINE_ID_MISS": 1,
        "LINE_ORDER_MISMATCH": 32,
        "TOKEN_OMISSION": 0,
        "TOKEN_EXTRA": 8,
        "TOKEN_SWAP": 3,
        "DUPLICATE_LINE": 0,
        "RECOGNIZER_DISAGREEMENT": 116,
    }
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
        "tokenDefinition": "NFC-normalized whitespace-delimited tokens; no model token IDs",
        "byField": {
            "placeOfResidence": {
                "groups": 160,
                "eligibleLineTokenGroups": 127,
                "classCounts": classes,
                "errorGroupCount": 160,
                "dominantErrorClass": "RECOGNIZER_DISAGREEMENT",
                "dominantErrorRate": 0.725,
                "tokenMismatchCount": 11,
                "lineOrderMismatchCount": 32,
                "recognizerDisagreementCount": 116,
            }
        },
        "decision": {
            "counterfactualAuthorized": False,
            "selectorChanged": False,
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


def test_attributes_residence_recognizer_dominance_without_selector() -> None:
    report = review(source_018t(), source_018p(), {})
    assert report["decision"]["status"] == "RESIDENCE_ERROR_CLASS_ATTRIBUTED_HOLD"
    assert report["decision"]["dominantErrorClass"] == "RECOGNIZER_DISAGREEMENT"
    assert report["decision"]["dominanceObserved"] == 0.725
    assert report["evidence"]["residenceAutoRegionHitCohort"]["nonRecognizerErrorCount"] == 44
    assert (
        report["evidence"]["attributionBoundary"][
            "profileVariantErrorClassCrossTabAvailable"
        ]
        is False
    )
    assert report["decision"]["profileSelectorAuthorized"] is False


def test_rejects_changed_residence_error_class_count() -> None:
    bad = source_018p()
    bad["byField"]["placeOfResidence"]["classCounts"]["RECOGNIZER_DISAGREEMENT"] = 115
    try:
        validate_018p(bad)
    except SystemExit as exc:
        assert "error-class evidence mismatch" in str(exc)
    else:
        raise AssertionError("changed residence evidence must fail closed")


def test_rejects_open_selector_boundary() -> None:
    bad = source_018t()
    bad["decision"]["profileSelectorAuthorized"] = True
    try:
        validate_018t(bad)
    except SystemExit as exc:
        assert "authorization boundary" in str(exc)
    else:
        raise AssertionError("selector authorization must fail closed")
