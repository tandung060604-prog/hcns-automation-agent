from scripts.review_ocr_ho_v2_019h import build_report, validate_package, validate_source


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019g-independent-package-intake/1.0.0",
        "taskId": "OCR-HO-V2-019G",
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
        "decision": {
            "developmentReplayAuthorized": False,
            "heldoutOpened": False,
            "evaluateOnceAuthorized": False,
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


def test_valid_independent_locks_are_ready_but_do_not_authorize_replay() -> None:
    payload = source()
    validate_source(payload)
    assert validate_package(package()) == []
    report = build_report(payload, package(), [], {})
    assert report["decision"]["status"] == "PACKAGE_LOCKED_READY_HOLD"
    assert report["decision"]["developmentReplayAuthorized"] is False


def test_missing_and_same_digest_package_fail_closed() -> None:
    payload = source()
    report = build_report(payload, None, ["packageManifestMissing"], {})
    assert report["decision"]["status"] == "PACKAGE_LOCK_NOT_READY_HOLD"
    invalid = package()
    invalid["groundTruthLock"]["sha256"] = invalid["predictionLock"]["sha256"]
    assert "distinctPredictionGroundTruthDigests" in validate_package(invalid)
