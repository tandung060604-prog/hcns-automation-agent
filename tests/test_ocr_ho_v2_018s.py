from scripts.review_ocr_ho_v2_018s import review, validate_017i, validate_018r


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


def source_018r() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-018r-residence-profile-variant-review/1.0.0",
        "taskId": "OCR-HO-V2-018R",
        **scope(),
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "evidenceScope": {
            "residenceSpecificProfileVariantCrossTabAvailable": False
        },
        "decision": {
            "profileVariantWinner": None,
            "profileSelectorAuthorized": False,
            "variantSelectorAuthorized": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
        },
    }


def metric(ascii_count: int, strict_count: int, cer: float, der: float) -> dict:
    return {
        "evaluated": 15,
        "strictExactCount": strict_count,
        "asciiExactCount": ascii_count,
        "characterErrorCount": 100,
        "referenceCharacterCount": 581,
        "diacriticErrorCount": 20,
        "referenceDiacriticCount": 107,
        "strictExactMatch": strict_count / 15,
        "asciiExactMatch": ascii_count / 15,
        "cer": cer,
        "der": der,
    }


def source_017i() -> dict:
    rows = {
        "vietocr_vgg_transformer::lanczos_upscale": metric(2, 2, 0.50, 0.16),
        "vietocr_vgg_transformer::color_original": metric(2, 2, 0.50, 0.19),
    }
    for index in range(14):
        rows[f"synthetic_profile_{index}::synthetic_variant_{index}"] = metric(
            0, 0, 0.60, 0.30
        )
    profile = {
        "vietocr_vgg_transformer": {"placeOfResidence": {"oracleBest": metric(2, 2, 0.44, 0.12)}}
    }
    variant = {
        "lanczos_upscale": {
            "placeOfResidence": {"oracleBest": metric(2, 2, 0.50, 0.16)}
        }
    }
    return {
        "schemaVersion": "ocr-ho-v2-017i-recognizer-profile-variant-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-017I",
        **scope(),
        "diagnosticTargetFields": ["fullName", "placeOfOrigin", "placeOfResidence"],
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocols": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "ORACLE_PROFILE_VARIANT_ATTRIBUTION_ONLY",
        },
        "profileVariantDiagnostics": {
            key: {"placeOfResidence": {"oracleBest": value}} for key, value in rows.items()
        },
        "profileDiagnostics": {"byField": profile},
        "variantDiagnostics": {"byField": variant},
        "residenceCeiling": {
            "gateAsciiExactCount": 13,
            "profileOracleBestMaxAsciiExactCount": 2,
            "variantOracleBestMaxAsciiExactCount": 2,
            "profileOrVariantReachesGate": False,
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
        "decision": {
            "runtimeChanged": False,
            "counterfactualReplayAuthorized": False,
        },
    }


def test_validates_cross_tab_but_keeps_hold() -> None:
    report = review(source_018r(), source_017i(), {})
    assert report["decision"]["status"] == "RESIDENCE_PROFILE_VARIANT_CROSSTAB_VALIDATED_HOLD"
    assert report["decision"]["crossTabValidated"] is True
    assert report["residenceCeiling"]["profileOracleBestMaxAsciiExactCount"] == 2
    assert report["decision"]["profileVariantWinner"] is None
    assert report["gates"]["acceptedCoverage"] == 0


def test_rejects_gate_reaching_claim() -> None:
    bad = source_017i()
    bad["residenceCeiling"]["profileOracleBestMaxAsciiExactCount"] = 13
    try:
        validate_017i(bad)
    except SystemExit as exc:
        assert "ceiling mismatch" in str(exc)
    else:
        raise AssertionError("invalid residence ceiling must fail closed")


def test_rejects_selector_winner_in_018r() -> None:
    bad = source_018r()
    bad["decision"]["profileVariantWinner"] = "some-profile::some-variant"
    try:
        validate_018r(bad)
    except SystemExit as exc:
        assert "selector boundary" in str(exc)
    else:
        raise AssertionError("selector winner must fail closed")
