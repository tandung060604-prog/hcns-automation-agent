from scripts.review_ocr_ho_v2_019e import (
    quality_review,
    validate_authorization,
    validate_source,
)


def source() -> dict:
    rows = []
    for profile in ("p1", "p2", "p3", "p4"):
        for variant in ("v1", "v2", "v3", "v4"):
            rows.append(
                {
                    "profile": profile,
                    "variant": variant,
                    "evaluatedDocuments": 15,
                    "fieldQuality": {
                        field: {"oracleBest": {"asciiExactCount": 1}}
                        for field in ("fullName", "placeOfOrigin", "placeOfResidence")
                    },
                    "oracleVsBaseline": {
                        field: {
                            "strictNotWorse": False,
                            "asciiNotWorse": False,
                            "cerNotWorse": False,
                            "derNotWorse": False,
                        }
                        for field in ("fullName", "placeOfOrigin", "placeOfResidence")
                    },
                    "residenceLineClassCounts": {
                        "LINE_ID_MATCH": 8,
                        "LINE_ID_MISS": 5,
                        "LINE_ORDER_MISMATCH": 2,
                        "DUPLICATE_LINE": 0,
                    },
                    "residenceOracleAsciiExactCount": 1,
                    "residenceGateEligible": False,
                }
            )
    return {
        "schemaVersion": "ocr-ho-v2-019d-per-profile-quality-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-019D",
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
        "quality": {
            "profileCount": 4,
            "variantCount": 4,
            "profileVariantCombinationCount": 16,
            "profileVariants": rows,
        },
    }


def authorization() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019e-quality-matrix-review-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-019E",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "containsRawPII": False,
        "sealedManifestSha256": "manifest-digest",
        "source019dSha256": "source-digest",
        "approval": {
            "approved": True,
            "approverRole": "OCR_REVIEW_OWNER",
            "localOnly": True,
            "aggregateQualityMatrixReviewAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_quality_review_keeps_matrix_non_selective_and_aggregate_only() -> None:
    payload = source()
    validate_source(payload)
    result = quality_review(payload)
    assert result["profileVariantRows"] == 16
    assert result["fieldQualityRows"] == 48
    assert result["allFieldNonRegressionPassRows"] == 0
    assert result["residence"]["oracleAsciiExactMax"] == 1
    assert result["residence"]["gateQualifiedCombinationCount"] == 0
    assert result["residenceLineClassTotals"]["LINE_ID_MISS"] == 80


def test_authorization_fails_closed_on_digest_and_selector() -> None:
    validate_authorization(authorization(), "source-digest", "manifest-digest")
    record = authorization()
    record["source019dSha256"] = "wrong"
    try:
        validate_authorization(record, "source-digest", "manifest-digest")
    except SystemExit as exc:
        assert "authorization record invalid" in str(exc)
    else:
        raise AssertionError("source digest mismatch must fail closed")

    record = authorization()
    record["approval"]["selectorChangeAuthorized"] = True
    try:
        validate_authorization(record, "source-digest", "manifest-digest")
    except SystemExit as exc:
        assert "prohibited authorization" in str(exc)
    else:
        raise AssertionError("selector authorization must fail closed")
