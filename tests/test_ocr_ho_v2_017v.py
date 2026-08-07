from scripts.review_ocr_ho_v2_017v import RULE, build_report, validate_record


def valid_record(digest: str = "digest") -> dict[str, object]:
    return {
        "schemaVersion": "ocr-ho-v2-017v-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-017V",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "candidateVersion": "11.10.2",
        "containsRawPII": False,
        "sourceArtifactSha256": digest,
        "rule": RULE.copy(),
        "approval": {
            "approved": True,
            "approverRole": "OCR_REVIEW_OWNER",
            "approvedAt": "2026-08-07T10:00:00Z",
            "localOnly": True,
            "productionPromotionAllowed": False,
            "replayAuthorized": False,
        },
    }


def test_missing_record_fails_closed() -> None:
    result = validate_record(None, "digest")
    assert result["status"] == "MISSING"
    assert result["patchReviewAuthorized"] is False
    assert result["patchAuthorized"] is False
    assert result["replayAuthorized"] is False


def test_matching_record_is_only_for_separate_patch_review() -> None:
    result = validate_record(valid_record(), "digest")
    assert result["status"] == "VALID_FOR_PATCH_REVIEW"
    assert result["patchReviewAuthorized"] is True
    assert result["patchAuthorized"] is False
    assert result["replayAuthorized"] is False


def test_source_digest_match_is_case_insensitive() -> None:
    result = validate_record(valid_record("ABCDEF"), "abcdef")
    assert result["status"] == "VALID_FOR_PATCH_REVIEW"


def test_source_digest_mismatch_invalidates_record() -> None:
    result = validate_record(valid_record(), "different")
    assert result["status"] == "INVALID"
    assert result["patchReviewAuthorized"] is False


def test_report_keeps_manual_review_and_promotion_closed() -> None:
    source = {
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
    }
    report = build_report(source, "digest", None, None)
    assert report["decision"]["status"] == "AUTHORIZATION_RECORD_REQUIRED"
    assert report["decision"]["recommendedNextTask"] == "OCR-HO-V2-017V"
    assert report["gates"]["manualReviewOnly"] is True
    assert report["gates"]["productionPromotionAllowed"] is False
