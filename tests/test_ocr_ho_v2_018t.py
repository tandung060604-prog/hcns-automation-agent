from scripts.review_ocr_ho_v2_018t import review, validate_018q, validate_018s


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


def source_018s() -> dict:
    rows = [
        {
            "profile": "vietocr_vgg_transformer",
            "variant": "lanczos_upscale",
            "residence": {"evaluated": 15},
        }
    ]
    rows.extend(
        {
            "profile": f"profile_{index}",
            "variant": f"variant_{index}",
            "residence": {"evaluated": 15},
        }
        for index in range(15)
    )
    return {
        "schemaVersion": (
            "ocr-ho-v2-018s-residence-profile-variant-crosstab-validation/1.0.0"
        ),
        "taskId": "OCR-HO-V2-018S",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "ORACLE_PROFILE_VARIANT_CROSSTAB_ATTRIBUTION_ONLY",
        },
        "crossTab": {
            "available": True,
            "residenceSpecific": True,
            "combinationCount": 16,
            "evaluatedPerCombination": 15,
            "oracleAttributionOnly": True,
        },
        "residenceCeiling": {
            "gateAsciiExactCount": 13,
            "profileOracleBestMaxAsciiExactCount": 2,
            "variantOracleBestMaxAsciiExactCount": 2,
            "profileOrVariantReachesGate": False,
        },
        "profileVariantResidenceRows": rows,
        "decision": {
            "profileVariantWinner": None,
            "bestDiagnosticRow": {
                "profile": "vietocr_vgg_transformer",
                "variant": "lanczos_upscale",
                "asciiExactCount": 2,
                "strictExactCount": 2,
            },
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


def source_018q() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018q-recognizer-sublayer-selection/1.0.0",
        "taskId": "OCR-HO-V2-018Q",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_RECOGNIZER_SUBLAYER_SELECTION_ONLY",
        },
        "evidence": {
            "residenceSubLayerComparison": {
                "recognizerDisagreement": 116,
                "lineOrderMismatch": 32,
                "tokenMismatch": 11,
            },
            "selectionBasis": {
                "selectedField": "placeOfResidence",
                "selectedCohort": "AUTO_REGION_HIT",
                "selectedClass": "RECOGNIZER_DISAGREEMENT",
                "selectedSubLayer": "PLACE_OF_RESIDENCE_RECOGNIZER_DISAGREEMENT",
                "profileOrVariantSelectorUsed": False,
            },
        },
        "decision": {
            "selectedSubLayer": "PLACE_OF_RESIDENCE_RECOGNIZER_DISAGREEMENT",
            "selectorPathOpen": False,
            "counterfactualAuthorized": False,
            "profileSelectorAuthorized": False,
            "variantSelectorAuthorized": False,
            "lineOrderChangeAuthorized": False,
            "tokenAlignmentChangeAuthorized": False,
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


def test_selects_one_bounded_non_selector_diagnostic() -> None:
    report = review(source_018s(), source_018q(), {})
    assert report["decision"]["status"] == "NON_SELECTOR_DIAGNOSTIC_SELECTED_HOLD"
    assert (
        report["decision"]["selectedDiagnostic"]
        == "RESIDENCE_RECOGNIZER_ERROR_CLASS_ATTRIBUTION"
    )
    assert report["evidence"]["crossTabCeiling"]["profileOrVariantReachesGate"] is False
    assert report["evidence"]["residenceErrorClasses"]["dominantClassCount"] == 116
    assert report["decision"]["profileSelectorAuthorized"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_rejects_gate_reaching_cross_tab() -> None:
    bad = source_018s()
    bad["residenceCeiling"]["profileOracleBestMaxAsciiExactCount"] = 13
    try:
        validate_018s(bad)
    except SystemExit as exc:
        assert "ceiling mismatch" in str(exc)
    else:
        raise AssertionError("gate-reaching cross-tab must fail closed")


def test_rejects_selector_authorization() -> None:
    bad = source_018q()
    bad["decision"]["profileSelectorAuthorized"] = True
    try:
        validate_018q(bad)
    except SystemExit as exc:
        assert "authorization boundary" in str(exc)
    else:
        raise AssertionError("selector authorization must fail closed")
