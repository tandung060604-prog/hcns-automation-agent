from __future__ import annotations

from scripts.review_ocr_ho_v2_018b import REPLAY_SCOPE, build_report, validate_record

SOURCE = {"candidateVersion": "11.10.2", "baselineVersion": "11.9.1"}


def valid_record(digest: str = "digest") -> dict[str, object]:
    return {
        "schemaVersion": "ocr-ho-v2-018b-development-replay-authorization-record/1.0.0",
        "taskId": "OCR-HO-V2-018B",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "containsRawPII": False,
        "sourceArtifactSha256": digest,
        "replayScope": REPLAY_SCOPE.copy(),
        "approval": {
            "approved": True,
            "approverRole": "OCR_REVIEW_OWNER",
            "approvedAt": "2026-08-07T16:30:00+07:00",
            "localOnly": True,
            "developmentReplayAuthorized": True,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "selectorChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
    }


def test_missing_record_fails_closed() -> None:
    result = validate_record(None, "digest")
    assert result["status"] == "MISSING"
    assert result["developmentReplayAuthorized"] is False
    assert result["heldoutEvaluationAuthorized"] is False


def test_matching_record_only_authorizes_development_replay() -> None:
    result = validate_record(valid_record(), "digest")
    assert result["status"] == "VALID_FOR_DEVELOPMENT_REPLAY"
    assert result["developmentReplayAuthorized"] is True
    assert result["evaluateOnceAuthorized"] is False
    assert result["primaryRuntimeChangeAuthorized"] is False


def test_heldout_or_evaluate_once_scope_invalidates_record() -> None:
    record = valid_record()
    record["replayScope"] = {**record["replayScope"], "heldoutEvaluation": True}
    result = validate_record(record, "digest")
    assert result["status"] == "INVALID"
    report = build_report(SOURCE, "digest", record, "record-digest")
    assert report["decision"]["replayExecuted"] is False
    assert report["decision"]["heldoutOpened"] is False
