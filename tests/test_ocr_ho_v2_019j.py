from scripts.review_ocr_ho_v2_019j import build_report, validate_package, validate_source


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019i-replay-closure-review/1.0.0",
        "taskId": "OCR-HO-V2-019I",
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
        "lockReview": {"replayClosure": "PASS"},
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


def package() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019h-independent-evidence-package-manifest/1.0.0",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionGroundTruthIndependent": True,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "groundTruthCreatedFromPrediction": False,
        "evaluateOnceAuthorized": False,
        "heldoutOpened": False,
        "primaryRuntimeChanged": False,
        "predictionLock": {
            "sealed": True,
            "immutable": True,
            "localOnly": True,
            "sha256": "a" * 64,
            "lockedAt": "2026-08-10T00:00:00Z",
        },
        "groundTruthLock": {
            "sealed": True,
            "immutable": True,
            "localOnly": True,
            "sha256": "b" * 64,
            "lockedAt": "2026-08-10T00:01:00Z",
        },
    }


def test_no_new_package_stays_replay_closed() -> None:
    payload = source()
    validate_source(payload)
    report = build_report(payload, None, ["packageManifestMissing"], "source-digest", None)
    assert report["decision"]["status"] == "NEW_PACKAGE_NOT_FOUND_REPLAY_CLOSED_HOLD"
    assert report["decision"]["replayClosed"] is True
    assert report["decision"]["developmentReplayAuthorized"] is False


def test_valid_manifest_is_metadata_only_and_still_not_replay_authorized() -> None:
    assert validate_package(package()) == []
    report = build_report(source(), package(), [], "source-digest", "package-digest")
    assert report["decision"]["status"] == "NEW_PACKAGE_LOCKED_REPLAY_CLOSED_HOLD"
    assert report["decision"]["developmentReplayExecuted"] is False
