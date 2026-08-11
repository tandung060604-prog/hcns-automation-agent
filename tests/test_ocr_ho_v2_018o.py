from scripts.review_ocr_ho_v2_018o import review, validate_018e, validate_018f


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


def source_018n() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018n-selector-path-closure-review/1.0.0",
        "taskId": "OCR-HO-V2-018N",
        **scope(),
        "decision": {"selectorPathOpen": False},
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


def source_018e() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018e-boundary-reconciliation/1.0.0",
        "taskId": "OCR-HO-V2-018E",
        **scope(),
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_BOUNDARY_RECONCILIATION_ONLY",
        },
        "reconciliation": {
            "automaticBoundary": {
                "aggregate": {
                    "evaluated": 45,
                    "autoHit": 27,
                    "boundaryMiss": 18,
                    "detectorMiss": 0,
                    "cropMiss": 0,
                    "dominantCategory": "bottom_boundary",
                    "categoryCounts": {"bottom_boundary": 8},
                    "dominantCategoryRate": 0.444444,
                    "meets50PercentThreshold": False,
                }
            }
        },
        "gates": {
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
            "productionPromotionAllowed": False,
        },
    }


def source_018f() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018f-recognizer-token-attribution/1.0.0",
        "taskId": "OCR-HO-V2-018F",
        **scope(),
        "protocol": {"gate": "AUTO_DETECTOR", "diagnostic": "ORACLE_LINE_TOKEN_ATTRIBUTION_ONLY"},
        "attribution": {
            "autoRegionMiss": {"lineIdMissCount": 245, "errorGroupCount": 245},
            "autoRegionHit": {
                "errorGroupCount": 375,
                "recognizerDisagreementCount": 291,
                "recognizerDisagreementRate": 0.776,
                "lineOrderMismatchCount": 72,
                "tokenMismatchCount": 11,
                "recognizerDominantAttribution": True,
            },
        },
        "decision": {
            "selectedLayer": "RECOGNIZER_TOKEN_ALIGNMENT",
            "runtimeChanged": False,
            "replayExecuted": False,
            "patchAuthorized": False,
            "counterfactualAuthorized": False,
        },
    }


def test_selects_recognizer_token_alignment_only() -> None:
    report = review(source_018n(), source_018e(), source_018f(), {})
    assert report["decision"]["status"] == "NON_SELECTOR_LAYER_SELECTED_HOLD"
    assert report["decision"]["selectedLayer"] == "RECOGNIZER_TOKEN_ALIGNMENT"
    assert report["decision"]["selectorPathOpen"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_rejects_detector_crop_threshold_claim() -> None:
    bad = source_018e()
    bad["reconciliation"]["automaticBoundary"]["aggregate"]["meets50PercentThreshold"] = True
    try:
        validate_018e(bad)
    except SystemExit as exc:
        assert "detector/crop evidence" in str(exc)
    else:
        raise AssertionError("threshold evidence must fail closed")


def test_rejects_selector_opening() -> None:
    bad = source_018f()
    bad["decision"]["counterfactualAuthorized"] = True
    try:
        validate_018f(bad)
    except SystemExit as exc:
        assert "attribution-only" in str(exc)
    else:
        raise AssertionError("selector counterfactual must fail closed")
