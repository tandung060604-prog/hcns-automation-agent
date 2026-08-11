from scripts.review_ocr_ho_v2_019i import build_report, validate_source


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019h-independent-package-lock-review/1.0.0",
        "taskId": "OCR-HO-V2-019H",
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
        "gtUsedForAttribution": False,
        "sourceDigests": {"sealedManifestDigest": "manifest-digest"},
        "packageReview": {
            "packageAvailable": False,
            "packageLockReady": False,
            "validationFailures": ["packageManifestMissing"],
            "packageMetadataOnly": True,
            "predictionOrGroundTruthOpened": False,
        },
        "decision": {
            "selectorEligible": False,
            "runtimeChanged": False,
            "developmentReplayAuthorized": False,
            "heldoutOpened": False,
            "evaluateOnceAuthorized": False,
            "promotionAllowed": False,
        },
        "gates": {
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
        },
    }


def test_missing_package_closes_replay_fail_closed() -> None:
    payload = source()
    validate_source(payload)
    report = build_report(payload, "source-digest")
    assert report["decision"]["status"] == "INDEPENDENT_PACKAGE_ABSENT_REPLAY_CLOSED_HOLD"
    assert report["decision"]["replayClosed"] is True
    assert report["decision"]["developmentReplayAuthorized"] is False


def test_source_with_opened_prediction_is_rejected() -> None:
    payload = source()
    payload["predictionOpened"] = True
    try:
        validate_source(payload)
    except SystemExit as exc:
        assert "aggregate-only" in str(exc)
    else:
        raise AssertionError("opened prediction must fail closed")
