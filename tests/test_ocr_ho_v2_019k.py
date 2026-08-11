from scripts.review_ocr_ho_v2_019k import build_report, validate_source


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019j-package-recheck/1.0.0",
        "taskId": "OCR-HO-V2-019J",
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
        "packageRecheck": {
            "inventoryResult": "NO_NEW_PACKAGE_FOUND",
            "newPackageAvailable": False,
            "newPackageLockValid": False,
        },
        "decision": {
            "replayClosed": True,
            "developmentReplayAuthorized": False,
            "developmentReplayExecuted": False,
            "heldoutOpened": False,
            "evaluateOnceAuthorized": False,
            "selectorEligible": False,
            "runtimeChanged": False,
            "promotionAllowed": False,
        },
    }


def test_no_package_keeps_replay_path_closed() -> None:
    payload = source()
    validate_source(payload)
    report = build_report(payload, "source-digest")
    assert report["decision"]["status"] == "REPLAY_PATH_CLOSED_NO_PACKAGE_HOLD"
    assert report["decision"]["replayClosed"] is True
    assert report["decision"]["developmentReplayAuthorized"] is False


def test_opened_prediction_fails_closed() -> None:
    payload = source()
    payload["predictionOpened"] = True
    try:
        validate_source(payload)
    except SystemExit as exc:
        assert "aggregate-only" in str(exc)
    else:
        raise AssertionError("opened prediction must fail closed")
