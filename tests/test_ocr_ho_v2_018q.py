from scripts.review_ocr_ho_v2_018q import review, validate_source


def source() -> dict:
    classes = {
        "LINE_ID_MISS": 0,
        "LINE_ORDER_MISMATCH": 32,
        "TOKEN_OMISSION": 0,
        "TOKEN_EXTRA": 8,
        "TOKEN_SWAP": 3,
        "DUPLICATE_LINE": 0,
        "RECOGNIZER_DISAGREEMENT": 116,
    }
    field = {
        "groups": 160,
        "eligibleLineTokenGroups": 127,
        "classCounts": classes,
        "errorGroupCount": 160,
        "dominantErrorClass": "RECOGNIZER_DISAGREEMENT",
        "dominantErrorRate": 0.725,
        "tokenMismatchCount": 11,
    }
    return {
        "schemaVersion": "ocr-ho-v2-018p-recognizer-token-attribution/1.0.0",
        "taskId": "OCR-HO-V2-018P",
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
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_RECOGNIZER_TOKEN_ATTRIBUTION_ONLY",
        },
        "tokenDefinition": "NFC-normalized whitespace-delimited tokens; no model token IDs",
        "decision": {
            "selectedLayer": "RECOGNIZER_TOKEN_ALIGNMENT",
            "counterfactualAuthorized": False,
            "selectorChanged": False,
            "runtimeChanged": False,
            "replayExecuted": False,
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
        "byField": {
            "fullName": {**field, "classCounts": {**classes, "RECOGNIZER_DISAGREEMENT": 79}},
            "placeOfOrigin": {
                **field,
                "classCounts": {
                    **classes,
                    "RECOGNIZER_DISAGREEMENT": 96,
                    "LINE_ORDER_MISMATCH": 40,
                },
            },
            "placeOfResidence": field,
        },
    }


def test_selects_residence_recognizer_disagreement() -> None:
    report = review(source(), "018p-digest")
    assert report["decision"]["status"] == "RECOGNIZER_SUBLAYER_SELECTED_HOLD"
    assert report["decision"]["selectedSubLayer"] == (
        "PLACE_OF_RESIDENCE_RECOGNIZER_DISAGREEMENT"
    )
    assert report["evidence"]["residenceSubLayerComparison"]["recognizerDisagreement"] == 116
    assert report["decision"]["selectorPathOpen"] is False


def test_rejects_selector_authorization() -> None:
    bad = source()
    bad["decision"]["counterfactualAuthorized"] = True
    try:
        validate_source(bad)
    except SystemExit as exc:
        assert "attribution-only" in str(exc)
    else:
        raise AssertionError("selector authorization must fail closed")


def test_rejects_non_manual_gate() -> None:
    bad = source()
    bad["gates"]["manualReviewOnly"] = False
    try:
        validate_source(bad)
    except SystemExit as exc:
        assert "attribution-only" in str(exc)
    else:
        raise AssertionError("manual-review guard must fail closed")
