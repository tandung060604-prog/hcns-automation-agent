from __future__ import annotations

from scripts.review_ocr_ho_v2_018d import review, validate_source

# ruff: noqa: E501


def source() -> dict[str, object]:
    fields = {
        name: {"ROI_MISS": 6 if name != "fullName" else 6, "PARSER_CONTAMINATION": 1}
        for name in ("fullName", "placeOfOrigin", "placeOfResidence")
    }
    fields["placeOfResidence"]["ROI_MISS"] = 5
    return {
        "schemaVersion": "ocr-ho-v2-018c-development-replay/1.0.0",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "acceptedCoverage": 0,
        "manualReviewOnly": True,
        "productionPromotionAllowed": False,
        "metrics": {
            "baseline_11_9_1": {"der": 0.114625},
            "candidate_11_10_2": {
                "der": 0.162055,
                "perField": {
                    name: {"asciiExactMatch": 0.4 if name != "fullName" else 0.933333}
                    for name in ("fullName", "placeOfOrigin", "placeOfResidence")
                },
            },
        },
        "gates": {"developmentRegressionGate": {"checks": {"snapshotMatched": False}}},
        "errorAnalyzer": {"candidate_11_10_2": {"classCountsByField": fields}},
        "roiDiagnostics": {
            "automaticDetector": {
                "fullName": {"correct": 8, "evaluated": 15, "accuracy": 0.533333},
                "placeOfOrigin": {"correct": 9, "evaluated": 15, "accuracy": 0.6},
                "placeOfResidence": {"correct": 10, "evaluated": 15, "accuracy": 0.666667},
            }
        },
        "exactRegressionCount": 1,
        "derBreakdown": {
            "baseline_11_9_1": {"diacriticErrorCount": 29},
            "candidate_11_10_2": {"referenceDiacriticCount": 253, "diacriticErrorCount": 41},
        },
    }


def evidence() -> dict[str, dict[str, object]]:
    empty = {"schemaVersion": "x", "datasetFamily": "CCCD", "datasetId": "DATA-HO-014", "documentCount": 15, "containsRawPII": False, "predictionOpened": False}
    return {
        "017O": {"evidence": {"residenceBoundaryMisses": {"bottomBoundary": {"caseRate": 0.6, "regionSourceCounts": {}},}, "globalBoundaryContext": {"categoryCounts": {}}}},
        "017I": {"residenceCeiling": {"profileOracleBestMaxAsciiExactCount": 2, "gateAsciiExactCount": 13}},
        "017K": {"aggregate": {"classCounts": {"LINE_ORDER_MISMATCH": 72}}},
        "018A": {"review": {"qualityImprovementProven": False}},
        "017D": {"metrics": {"counterfactual_017d": {"der": 0.16996}}},
        "017E": {"selectionAudit": {"eligibleSwitchCount": 0}},
        "017F": {"selectionAudit": {"changedFieldCount": 0}},
        **{key: empty for key in ("017M", "017N", "017P")},
    }


def test_review_selects_only_detector_crop_without_authorizing_change() -> None:
    report = review(source(), "source", evidence(), {})
    validate_source(source())
    assert report["decision"]["selectedLayer"] == "DETECTOR_CROP"
    assert report["selectedNextDiagnostic"]["taskId"] == "OCR-HO-V2-018E"
    assert report["selectedNextDiagnostic"]["replayAuthorized"] is False
    assert report["selectedNextDiagnostic"]["roiPatchAuthorized"] is False
    assert report["gates"]["acceptedCoverage"] == 0
