from scripts.analyze_ocr_ho_v2_018v import review


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


def source_u() -> dict:
    return {
        "evidence": {
            "residenceAutoRegionHitCohort": {
                "field": "placeOfResidence",
                "cohort": "AUTO_REGION_HIT",
                "groups": 160,
                "eligibleLineTokenGroups": 127,
                "errorGroupCount": 160,
                "classCounts": {"RECOGNIZER_DISAGREEMENT": 116},
                "recognizerDisagreementRateAmongErrorGroups": 0.725,
            }
        }
    }


def source_s() -> dict:
    return {
        "residenceCeiling": {
            "gateAsciiExactCount": 13,
            "profileOracleBestMaxAsciiExactCount": 2,
            "variantOracleBestMaxAsciiExactCount": 2,
            "profileOrVariantReachesGate": False,
        }
    }


def source_p() -> dict:
    aggregate = {
        "groups": 10,
        "eligibleLineTokenGroups": 8,
        "errorGroupCount": 9,
        "classCounts": {
            "LINE_ID_MISS": 0,
            "LINE_ORDER_MISMATCH": 1,
            "TOKEN_OMISSION": 0,
            "TOKEN_EXTRA": 0,
            "TOKEN_SWAP": 0,
            "DUPLICATE_LINE": 0,
            "RECOGNIZER_DISAGREEMENT": 8,
        },
        "dominantErrorClass": "RECOGNIZER_DISAGREEMENT",
        "dominantErrorRate": 0.889,
    }
    return {
        "byProfile": {f"profile_{i}": {"autoRegionHit": aggregate} for i in range(4)},
        "byVariant": {f"variant_{i}": {"autoRegionHit": aggregate} for i in range(4)},
    }


def intake() -> dict:
    return {"authorizationIntake": {"status": "VALID_FOR_PROFILE_VARIANT_ERROR_CLASS_REVIEW"}}


def test_review_keeps_missing_joint_cross_tab_closed() -> None:
    report = review(source_u(), source_s(), source_p(), intake(), {})
    assert report["decision"]["status"] == "PROFILE_VARIANT_ERROR_CLASS_REVIEW_HOLD"
    assert report["decision"]["evidenceReviewExecuted"] is True
    assert report["decision"]["profileVariantByResidenceErrorClassAvailable"] is False
    assert report["decision"]["profileVariantWinner"] is None
    assert report["decision"]["selectorChanged"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_review_does_not_treat_all_target_aggregates_as_residence_specific() -> None:
    report = review(source_u(), source_s(), source_p(), intake(), {})
    assert (
        report["evidence"]["allTargetFieldProfileAggregates"]["scope"]
        == "ALL_TARGET_FIELDS_NOT_RESIDENCE_SPECIFIC"
    )
    assert report["evidence"]["jointEvidenceBoundary"]["selectionEligible"] is False
