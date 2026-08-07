from scripts.review_ocr_ho_v2_017l import dominant_classes, review, validate_source


def source() -> dict[str, object]:
    classes = {
        "LINE_ID_MISS": 4,
        "LINE_ORDER_MISMATCH": 2,
        "TOKEN_OMISSION": 0,
        "TOKEN_EXTRA": 0,
        "TOKEN_SWAP": 0,
        "DUPLICATE_LINE": 0,
        "RECOGNIZER_DISAGREEMENT": 3,
        "PARSER_CONTAMINATION": 1,
        "UNCLASSIFIED": 0,
    }
    return {
        "schemaVersion": "ocr-ho-v2-017k-line-token-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-017K",
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
        "aggregate": {
            "groups": 10,
            "eligibleLineTokenGroups": 8,
            "eligibleFailureCount": 10,
            "classCounts": classes,
            "dominantCategory": "LINE_ID_MISS",
            "dominantCategoryRate": 0.4,
        },
        "automaticRegion": {"evaluated": 3, "hit": 1, "miss": 2},
        "byField": {"fullName": {}, "placeOfOrigin": {}, "placeOfResidence": {}},
    }


def test_017l_proposes_one_non_runtime_diagnostic_when_no_class_dominates() -> None:
    data = source()
    validate_source(data)
    assert dominant_classes(data)[0]["class"] == "LINE_ID_MISS"
    report = review(data, "synthetic-digest")
    assert report["selectedNextDiagnostic"]["taskId"] == "OCR-HO-V2-017M"
    assert report["selectedNextDiagnostic"]["status"] == "PROPOSED_NOT_AUTHORIZED"
    assert report["selectedNextDiagnostic"]["runtimeChange"] is False
    assert report["gates"]["developmentRegressionGate"] == "HOLD"


def test_017l_rejects_dominant_class_for_new_layer_selection() -> None:
    data = source()
    data["aggregate"]["classCounts"]["LINE_ID_MISS"] = 6
    data["aggregate"]["eligibleFailureCount"] = 10
    try:
        review(data, "synthetic-digest")
    except SystemExit as error:
        assert "dominant class" in str(error)
    else:
        raise AssertionError("017L must stop when a class reaches the dominance threshold")
