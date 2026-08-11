from scripts.review_ocr_ho_v2_019g import (
    build_report,
    validate_authorization,
    validate_package,
    validate_source,
)


def source() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019f-profile-variant-closure/1.0.0",
        "taskId": "OCR-HO-V2-019F",
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
        "decision": {
            "status": "PROFILE_VARIANT_SELECTION_PATH_CLOSED_HOLD",
            "selectorEligible": False,
            "patchReviewEligible": False,
            "promotionAllowed": False,
        },
    }


def authorization() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019g-independent-package-intake-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-019G",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "containsRawPII": False,
        "sealedManifestSha256": "manifest-digest",
        "source019fSha256": "source-digest",
        "approval": {
            "approved": True,
            "approverRole": "OCR_REVIEW_OWNER",
            "localOnly": True,
            "independentEvidencePackageIntakeAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def package() -> dict:
    return {
        "schemaVersion": "ocr-ho-v2-019g-independent-evidence-package-manifest/1.0.0",
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
        "groundTruthCreatedFromPrediction": False,
        "evaluateOnceAuthorized": False,
        "heldoutOpened": False,
        "primaryRuntimeChanged": False,
        "predictionLock": {
            "sealed": True,
            "immutable": True,
            "localOnly": True,
            "sha256": "prediction-digest",
            "lockedAt": "2026-08-10T00:00:00Z",
        },
        "groundTruthLock": {
            "sealed": True,
            "immutable": True,
            "localOnly": True,
            "sha256": "groundtruth-digest",
            "lockedAt": "2026-08-10T00:01:00Z",
        },
    }


def test_missing_package_stays_hold_and_valid_package_has_no_execution_authority() -> None:
    payload = source()
    validate_source(payload)
    report = build_report(payload, None, ["packageManifestMissing"], {})
    assert report["decision"]["status"] == "PACKAGE_NOT_READY_HOLD"
    assert report["decision"]["developmentReplayAuthorized"] is False
    assert validate_package(package()) == []


def test_authorization_and_package_digest_boundaries_fail_closed() -> None:
    validate_authorization(authorization(), "source-digest", "manifest-digest")
    record = authorization()
    record["source019fSha256"] = "wrong"
    try:
        validate_authorization(record, "source-digest", "manifest-digest")
    except SystemExit as exc:
        assert "authorization record invalid" in str(exc)
    else:
        raise AssertionError("source digest mismatch must fail closed")

    invalid = package()
    invalid["groundTruthCreatedFromPrediction"] = True
    assert "groundTruthCreatedFromPrediction" in validate_package(invalid)
