from scripts.review_ocr_ho_v2_017z import PATCH_SURFACE, RULE, build_report, validate_record


def source() -> dict[str, object]:
    return {
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
    }


def valid_record(digest: str = "digest") -> dict[str, object]:
    return {
        "schemaVersion": "ocr-ho-v2-017z-runtime-patch-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-017Z",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "candidateVersion": "11.10.2",
        "containsRawPII": False,
        "sourceArtifactSha256": digest,
        "rule": RULE.copy(),
        "patchSurface": PATCH_SURFACE.copy(),
        "approval": {
            "approved": True,
            "approverRole": "OCR_REVIEW_OWNER",
            "approvedAt": "2026-08-07T15:00:00+07:00",
            "localOnly": True,
            "runtimePatchAuthorized": True,
            "primaryRuntimeChangeAuthorized": False,
            "selectorChangeAuthorized": False,
            "replayAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_missing_record_fails_closed() -> None:
    result = validate_record(None, "digest")
    assert result["status"] == "MISSING"
    assert result["runtimePatchAuthorized"] is False
    assert result["replayAuthorized"] is False


def test_matching_record_only_authorizes_development_patch() -> None:
    result = validate_record(valid_record(), "digest")
    assert result["status"] == "VALID_FOR_DEVELOPMENT_PATCH"
    assert result["runtimePatchAuthorized"] is True
    assert result["primaryRuntimeChangeAuthorized"] is False
    assert result["replayAuthorized"] is False


def test_replay_or_primary_runtime_authorization_invalidates_record() -> None:
    record = valid_record()
    record["approval"] = {**record["approval"], "replayAuthorized": True}
    result = validate_record(record, "digest")
    assert result["status"] == "INVALID"
    report = build_report(source(), "digest", record, "record-digest")
    assert report["decision"]["patchApplied"] is False
