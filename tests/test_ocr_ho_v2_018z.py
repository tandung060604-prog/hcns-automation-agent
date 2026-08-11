from scripts.review_ocr_ho_v2_018z import (
    review,
    validate_authorization,
    validate_sources,
)


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


def source_018y() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018y-class-distribution-bounded-diagnostic-review/1.0.0",
        "taskId": "OCR-HO-V2-018Y",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "decision": {
            "selectedDiagnostic": "RESIDENCE_LINE_ID_MISS_BOUNDARY_ATTRIBUTION"
        },
        "distribution": {
            "classTotals": {"LINE_ID_MISS": 81},
            "lineIdMissRows": 16,
        },
    }


def source_018w() -> dict:
    rows = [
        {
            "evaluatedDocuments": 15,
            "classCounts": {"LINE_ID_MISS": 5},
        }
        for _ in range(16)
    ]
    return {
        "schemaVersion": (
            "ocr-ho-v2-018w-sealed-joint-residence-profile-variant-error-class-extractor/1.0.0"
        ),
        "taskId": "OCR-HO-V2-018W",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "jointEvidence": {"rows": rows},
    }


def source_017h() -> dict:
    entries = [
        {
            "field": "placeOfResidence",
            "category": "bottom_boundary",
            "missingExpectedLineCount": 2,
            "selectedLineCount": 1,
        },
        {
            "field": "placeOfResidence",
            "category": "bottom_boundary",
            "missingExpectedLineCount": 2,
            "selectedLineCount": 1,
        },
        {
            "field": "placeOfResidence",
            "category": "bottom_boundary",
            "missingExpectedLineCount": 2,
            "selectedLineCount": 2,
        },
        {
            "field": "placeOfResidence",
            "category": "multiple_boundary_sides",
            "missingExpectedLineCount": 1,
            "selectedLineCount": 2,
        },
        {
            "field": "placeOfResidence",
            "category": "line_order",
            "missingExpectedLineCount": 2,
            "selectedLineCount": 2,
        },
    ]
    return {
        "schemaVersion": "ocr-ho-v2-017h-roi-boundary-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-017H",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "automaticDetector": {
            "byField": {
                "placeOfResidence": {
                    "boundaryMiss": 5,
                    "autoHit": 10,
                    "lineSideCounts": {"bottom_boundary": 4, "left_boundary": 1, "top_boundary": 1},
                }
            }
        },
        "missDetailsAggregateOnly": entries,
    }


def source_017p() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-017p-residence-geometry-segmentation-boundary-review/1.0.0",
        "taskId": "OCR-HO-V2-017P",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "decision": {"roiPatchAuthorized": False},
        "evidence": {
            "bottomBoundaryCases": {
                "caseCount": 3,
                "bottomOverflowCaseCount": 2,
                "bottomOverflowCaseRate": 0.666667,
                "sealedLineIdOverlapRate": 0.0,
                "regionSourceCounts": {"phase11_10_geometry_line_segmentation": 3},
            },
            "priorGlobalBoundaryContext": {
                    "dominantCategory": "bottom_boundary",
                    "dominantCategoryRate": 0.444444,
                    "meets50PercentThreshold": False,
            },
        },
    }


def authorization() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018z-residence-line-id-boundary-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-018Z",
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
            "aggregateResidenceBoundaryAttributionAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_residence_boundary_attribution_stays_aggregate_only() -> None:
    sources = (source_018y(), source_018w(), source_017h(), source_017p())
    validate_sources(*sources)
    report = review(*sources, {})
    assert report["attribution"]["residenceBoundary"]["dominantCategory"] == "bottom_boundary"
    assert report["attribution"]["residenceBoundary"]["dominantCategoryRate"] == 0.6
    assert report["attribution"]["profileVariantLineIdMissGroups"] == 81
    assert report["attribution"]["crossTabAvailable"] is False
    assert report["decision"]["patchAuthorized"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_boundary_global_threshold_remains_separate() -> None:
    report = review(source_018y(), source_018w(), source_017h(), source_017p(), {})
    assert report["geometryCorroboration"]["globalPatchThresholdReached"] is False
    assert report["decision"]["profileVariantWinner"] is None
    assert report["decision"]["nextTask"] == "OCR-HO-V2-019A"


def test_authorization_requires_matching_manifest_and_no_selector() -> None:
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
