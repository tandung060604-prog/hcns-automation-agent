from scripts.extract_ocr_ho_v2_019b import (
    build_cross_tab,
    validate_authorization,
)


def authorization() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019b-independent-residence-crosstab-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-019B",
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
            "independentResidenceCrossTabAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def manifest() -> dict:
    return {
        "documents": [
            {"fields": {"placeOfResidence": {"lineIds": [12, 13]}}},
            {"fields": {"placeOfResidence": {"lineIds": [12, 13]}}},
        ]
    }


def test_cross_tab_emits_counts_only_and_separates_boundary_cohort() -> None:
    candidates = [
        {
            "candidates": {
                "placeOfResidence": [
                    {"profile": "p1", "variant": "line_a", "lineIds": [12]},
                    {"profile": "p1", "variant": "line_a", "lineIds": [13]},
                    {"profile": "p2", "variant": "line_b", "lineIds": [12]},
                ]
            }
        },
        {
            "candidates": {
                "placeOfResidence": [
                    {"profile": "p1", "variant": "line_a", "lineIds": [12, 13]},
                ]
            }
        },
    ]
    result = build_cross_tab(manifest(), candidates, {1: "bottom_boundary"})
    assert result["boundaryAttributedLineIdMissGroups"] == 1
    assert result["lineIdClassTotals"]["LINE_ID_MISS"] == 1
    assert result["rows"] == [
        {
            "profile": "p2",
            "variant": "b",
            "boundaryCategory": "bottom_boundary",
            "lineIdMissGroups": 1,
        }
    ]
    assert all("value" not in row and "text" not in row for row in result["rows"])


def test_authorization_digest_and_selector_boundaries_fail_closed() -> None:
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
