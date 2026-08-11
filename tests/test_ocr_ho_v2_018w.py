from scripts.extract_ocr_ho_v2_018w import build_joint_table, build_report, validate_authorization


def source_018v() -> dict:
    return {"decision": {"status": "PROFILE_VARIANT_ERROR_CLASS_REVIEW_HOLD"}}


def manifest() -> dict:
    return {"manifestSha256": "manifest-digest"}


def authorization() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018w-sealed-joint-extractor-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-018W",
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
            "aggregateExtractorExecutionAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_joint_table_aggregates_without_values() -> None:
    records = [
        {
            "profile": "p1",
            "variant": "v1",
            "label": "RECOGNIZER_DISAGREEMENT",
            "eligible": True,
            "documentEvaluated": True,
        },
        {
            "profile": "p1",
            "variant": "v1",
            "label": "LINE_ORDER_MISMATCH",
            "eligible": False,
            "documentEvaluated": True,
        },
    ]
    table = build_joint_table(records)
    assert table["p1::v1"]["errorGroupCount"] == 2
    assert table["p1::v1"]["classCounts"]["RECOGNIZER_DISAGREEMENT"] == 1
    assert table["p1::v1"]["eligibleLineTokenGroups"] == 1
    assert "value" not in table["p1::v1"]


def test_report_is_diagnostic_only() -> None:
    rows = {
        "p1::v1": {
            "profile": "p1",
            "variant": "v1",
            "evaluatedDocuments": 15,
            "groups": 15,
            "eligibleLineTokenGroups": 10,
            "errorGroupCount": 15,
            "classCounts": {"RECOGNIZER_DISAGREEMENT": 15},
            "dominantErrorClass": "RECOGNIZER_DISAGREEMENT",
            "dominantErrorRate": 1.0,
        }
    }
    report = build_report(source_018v(), manifest(), rows, {})
    assert report["jointEvidence"]["available"] is True
    assert report["decision"]["profileVariantWinner"] is None
    assert report["decision"]["selectionEligible"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_prohibited_authorization_fails_closed() -> None:
    record = authorization()
    record["approval"]["selectorChangeAuthorized"] = True
    try:
        validate_authorization(record, "manifest-digest")
    except SystemExit as exc:
        assert "prohibited authorization" in str(exc)
    else:
        raise AssertionError("selector authorization must fail closed")
