from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hcns_agent.application.phase14_7_protocol import (
    CONFIRMED,
    PENDING,
    apply_review_update,
    bbox_balanced_bounds,
    compute_queue_digest,
    next_pending_case,
    public_review_case,
    validate_review_queue,
    verify_hidden_snapshot,
)


def queue_fixture() -> dict:
    cases = [
        {
            "caseId": "case-a",
            "documentId": "SYNTHETIC-DOC-A",
            "pageIndex": 0,
            "lineIndex": 0,
            "box": [[5, 5], [40, 5], [40, 15], [5, 15]],
            "cropPath": "ground_truth/private_phase14_7/crops/a.png",
            "pageRenderPath": "ground_truth/private_phase14_7/pages/a.jpg",
            "cropSha256": "a" * 64,
            "status": PENDING,
            "confirmedTranscription": "",
            "reviewer": "",
            "reviewedAt": "",
        },
        {
            "caseId": "case-b",
            "documentId": "SYNTHETIC-DOC-B",
            "pageIndex": 0,
            "lineIndex": 0,
            "box": [[5, 5], [40, 5], [40, 15], [5, 15]],
            "cropPath": "ground_truth/private_phase14_7/crops/b.png",
            "pageRenderPath": "ground_truth/private_phase14_7/pages/b.jpg",
            "cropSha256": "b" * 64,
            "status": PENDING,
            "confirmedTranscription": "",
            "reviewer": "",
            "reviewedAt": "",
        },
    ]
    return {
        "predictionsVisibleDuringReview": False,
        "lineCount": len(cases),
        "queueDigest": compute_queue_digest(cases),
        "cases": cases,
    }


def test_bbox_balanced_bounds_matches_locked_padding() -> None:
    bounds = bbox_balanced_bounds(
        [[10, 20], [90, 20], [90, 40], [10, 40]],
        image_width=100,
        image_height=60,
    )
    assert bounds == (6, 18, 94, 42)


def test_review_queue_rejects_prediction_suggestions() -> None:
    queue = queue_fixture()
    queue["cases"][0]["draftTranscription"] = "MODEL OUTPUT"
    with pytest.raises(ValueError, match="recognizer output"):
        validate_review_queue(queue)


def test_confirmed_case_is_not_returned_after_refresh() -> None:
    queue = queue_fixture()
    first = next_pending_case(queue)
    assert first is not None
    apply_review_update(
        queue,
        case_id="case-a",
        status=CONFIRMED,
        transcription="  CỘNG HÒA  ",
        reviewer="reviewer",
        reviewed_at="2026-07-28T00:00:00+00:00",
    )
    resumed = next_pending_case(queue)
    assert resumed is not None
    assert resumed["caseId"] == "case-b"
    assert queue["cases"][0]["confirmedTranscription"] == "CỘNG HÒA"


def test_public_case_contains_no_ground_truth_or_prediction() -> None:
    payload = public_review_case(queue_fixture()["cases"][0])
    assert "confirmedTranscription" not in payload
    assert "predictions" not in payload
    assert "draftTranscription" not in payload


def test_hidden_snapshot_must_match_status_and_sha_lock(tmp_path: Path) -> None:
    queue = queue_fixture()
    artifact = tmp_path / "phase14_7_hidden_predictions_private.json"
    artifact.write_bytes(b'{"private":true}\n')
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    status = {
        "status": "BLINDED_PREDICTIONS_READY",
        "predictionsHiddenDuringReview": True,
        "queueDigest": queue["queueDigest"],
        "lineCount": queue["lineCount"],
        "privateArtifactSha256": digest,
    }
    verify_hidden_snapshot(
        queue=queue,
        status=status,
        private_artifact_path=artifact,
        lock_text=(
            f"{digest}  predictions/"
            "phase14_7_hidden_predictions_private.json\n"
        ),
    )
