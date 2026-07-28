from __future__ import annotations

import unittest
from pathlib import Path

from scripts.phase14_6_heldout_protocol import (
    evaluate_once,
    seal_predictions,
)
from scripts.validate_phase14_6_lock import load_and_validate_lock


class Phase146HeldOutProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.lock = load_and_validate_lock(
            root / "config" / "phase14_6_benchmark_lock.json"
        )

    def test_seal_rejects_ground_truth_leakage(self) -> None:
        payload = _predictions()
        payload["cases"][0]["groundTruth"] = "synthetic leak"

        with self.assertRaisesRegex(ValueError, "must not contain Ground Truth"):
            seal_predictions(
                payload,
                self.lock,
                lock_digest="a" * 64,
                source_digest="b" * 64,
            )

    def test_fixed_policy_evaluation_is_single_spec_and_aggregate_only(self) -> None:
        sealed = seal_predictions(
            _predictions(),
            self.lock,
            lock_digest="a" * 64,
            source_digest="b" * 64,
        )
        truth = {
            "groundTruthStatus": "USER_CONFIRMED_HELD_OUT_GROUND_TRUTH",
            "predictionsVisibleDuringReview": False,
            "confirmedAt": "2026-07-28T00:00:00+00:00",
            "datasetDigest": "sha256:synthetic",
            "cases": [
                {"caseId": "LINE-001", "groundTruth": "PHẠM THỊ LINH"},
                {"caseId": "LINE-002", "groundTruth": "QUẬN 1"},
            ],
        }

        result = evaluate_once(
            sealed,
            truth,
            self.lock,
            sealed_digest="c" * 64,
            ground_truth_digest="d" * 64,
        )
        rendered = str(result)

        self.assertEqual(1, result["evaluationRunCount"])
        self.assertFalse(result["thresholdRetuned"])
        self.assertFalse(result["policy"]["autoReplaceSelectedText"])
        self.assertNotIn("PHẠM THỊ LINH", rendered)
        self.assertNotIn("QUẬN 1", rendered)


def _predictions() -> dict:
    cases = [
        {
            "caseId": "LINE-001",
            "predictions": {
                "vietocr_vgg_seq2seq": {
                    "text": "PHAM THI LINH",
                    "confidence": 0.2,
                },
                "vietocr_vgg_transformer": {"text": "PHẠM THỊ LINH"},
                "paddle_detector_raw": {"text": "PHẠM THỊ LINH"},
            },
        },
        {
            "caseId": "LINE-002",
            "predictions": {
                "vietocr_vgg_seq2seq": {
                    "text": "QUẬN 1",
                    "confidence": 0.9,
                },
                "vietocr_vgg_transformer": {"text": "QUẬN 1"},
                "paddle_detector_raw": {"text": "QUN 1"},
            },
        },
    ]
    return {
        "datasetId": "synthetic-heldout",
        "datasetDigest": "sha256:synthetic",
        "documentCount": 15,
        "lineCount": len(cases),
        "cases": cases,
    }


if __name__ == "__main__":
    unittest.main()
