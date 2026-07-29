from __future__ import annotations

from hcns_agent.application.phase14_7_evaluation import evaluate_phase14_7


def test_evaluation_is_aggregate_only_and_respects_sample_gate() -> None:
    cases = [
        {
            "caseId": "line-1",
            "predictions": {
                "vietocr_vgg_seq2seq": {
                    "text": "CONG HOA",
                    "confidence": 0.2,
                },
                "vietocr_vgg_transformer": {"text": "CỘNG HÒA"},
                "paddle_detector_raw": {"text": "CỘNG HÒA"},
            },
        },
        {
            "caseId": "line-2",
            "predictions": {
                "vietocr_vgg_seq2seq": {
                    "text": "DÒNG BỎ QUA",
                    "confidence": 0.9,
                },
                "vietocr_vgg_transformer": {"text": "DÒNG BỎ QUA"},
                "paddle_detector_raw": {"text": "DÒNG BỎ QUA"},
            },
        },
    ]
    snapshot = {
        "predictionsHiddenDuringReview": True,
        "groundTruthPresent": False,
        "queueDigest": "queue",
        "datasetDigest": "dataset",
        "datasetId": "synthetic",
        "documentCount": 8,
        "cases": cases,
    }
    ground_truth = {
        "groundTruthStatus": "USER_CONFIRMED_HELD_OUT_GROUND_TRUTH",
        "predictionsVisibleDuringReview": False,
        "confirmedAt": "2026-07-28T00:00:00+00:00",
        "queueDigest": "queue",
        "datasetDigest": "dataset",
        "cases": [
            {
                "caseId": "line-1",
                "status": "CONFIRMED",
                "confirmedTranscription": "CỘNG HÒA",
            },
            {
                "caseId": "line-2",
                "status": "SKIPPED",
                "confirmedTranscription": "",
            },
        ],
    }
    policy = {
        "policyId": "policy",
        "version": "1",
        "mode": "SHADOW_REVIEW_ONLY",
        "primaryConfidenceReviewThreshold": 0.4,
    }

    result = evaluate_phase14_7(
        snapshot=snapshot,
        ground_truth=ground_truth,
        policy=policy,
        minimum_document_count=15,
        evaluated_at="2026-07-28T00:00:00+00:00",
        snapshot_sha256="a" * 64,
        ground_truth_sha256="b" * 64,
        dataset_lock_sha256="c" * 64,
    )

    assert result["review"]["evaluatedConfirmedLineCount"] == 1
    assert result["review"]["skippedLineCount"] == 1
    assert result["decision"]["heldOutSampleGate"] == "INSUFFICIENT_DOCUMENTS"
    assert result["fixedPolicyReplay"]["baselineErrorsRecovered"] == 1
    rendered = str(result)
    assert "CỘNG HÒA" not in rendered
    assert "CONG HOA" not in rendered
