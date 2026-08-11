from scripts.review_ocr_ho_v2_018x import review, validate_source


def source() -> dict:
    rows = []
    for index in range(16):
        rows.append(
            {
                "profile": f"p{index // 4}",
                "variant": f"v{index % 4}",
                "evaluatedDocuments": 15,
                "groups": 15,
                "eligibleLineTokenGroups": 8,
                "errorGroupCount": 15,
                "classCounts": {
                    "LINE_ID_MISS": 5,
                    "LINE_ORDER_MISMATCH": 2,
                    "TOKEN_OMISSION": 0,
                    "TOKEN_EXTRA": 0,
                    "TOKEN_SWAP": 0,
                    "DUPLICATE_LINE": 0,
                    "RECOGNIZER_DISAGREEMENT": 8,
                },
                "dominantErrorClass": "RECOGNIZER_DISAGREEMENT",
                "dominantErrorRate": 8 / 15,
            }
        )
    return {
        "schemaVersion": (
            "ocr-ho-v2-018w-sealed-joint-residence-profile-variant-error-class-"
            "extractor/1.0.0"
        ),
        "taskId": "OCR-HO-V2-018W",
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
            "diagnostic": "SEALED_JOINT_RESIDENCE_PROFILE_VARIANT_ERROR_CLASS_EXTRACTION_ONLY",
        },
        "jointEvidence": {
            "available": True,
            "combinationCount": 16,
            "completeCombinationCount": 16,
            "evaluatedDocumentsPerCompleteCombination": 15,
            "rows": rows,
            "rawValuesEmitted": False,
        },
        "decision": {
            "selectionEligible": False,
            "selectorChanged": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "profileVariantWinner": None,
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


def test_review_summarizes_complete_joint_table_without_winner() -> None:
    source_data = source()
    validate_source(source_data)
    report = review(source_data, "sealed-digest")
    assert report["decision"]["status"] == "SEALED_JOINT_TABLE_REVIEW_HOLD"
    assert report["review"]["totalProfileVariantDocumentGroups"] == 240
    assert report["review"]["classTotals"]["RECOGNIZER_DISAGREEMENT"] == 128
    assert report["decision"]["profileVariantWinner"] is None
    assert report["gates"]["acceptedCoverage"] == 0


def test_rejects_incomplete_joint_table() -> None:
    bad = source()
    bad["jointEvidence"]["completeCombinationCount"] = 15
    try:
        validate_source(bad)
    except SystemExit as exc:
        assert "joint evidence mismatch" in str(exc)
    else:
        raise AssertionError("incomplete joint table must fail closed")


def test_rejects_raw_value_field() -> None:
    bad = source()
    bad["jointEvidence"]["rows"][0]["value"] = "sensitive"
    try:
        validate_source(bad)
    except SystemExit as exc:
        assert "raw value" in str(exc)
    else:
        raise AssertionError("raw value emission must fail closed")
