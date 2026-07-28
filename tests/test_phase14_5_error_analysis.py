from __future__ import annotations

import unittest

from scripts.phase14_5_error_analysis import (
    LineRecord,
    build_analysis,
    conditional_prediction,
)


def _record(
    *,
    document: str,
    ground_truth: str,
    primary: str,
    transformer: str,
    paddle: str,
    confidence: float = 0.9,
) -> LineRecord:
    return LineRecord(
        document_key=document,
        ground_truth=ground_truth,
        primary=primary,
        transformer=transformer,
        paddle=paddle,
        primary_confidence=confidence,
    )


class Phase145FallbackTests(unittest.TestCase):
    def test_transformer_paddle_agreement_is_review_candidate(self) -> None:
        record = _record(
            document="synthetic-a",
            ground_truth="đơn xin nghỉ phép",
            primary="don xin nghi phep",
            transformer="đơn xin nghỉ phép",
            paddle="đơn xin nghỉ phép",
        )

        prediction, reason = conditional_prediction(record, threshold=0.8)

        self.assertEqual("đơn xin nghỉ phép", prediction)
        self.assertEqual("transformer_paddle_agreement", reason)

    def test_low_confidence_primary_exposes_paddle_candidate(self) -> None:
        record = _record(
            document="synthetic-a",
            ground_truth="nhân viên",
            primary="nhan vien",
            transformer="nhan viên",
            paddle="nhân viên",
            confidence=0.4,
        )

        prediction, reason = conditional_prediction(record, threshold=0.8)

        self.assertEqual("nhân viên", prediction)
        self.assertEqual("low_primary_confidence_paddle_candidate", reason)

    def test_aggregate_output_does_not_retain_private_text_or_document_keys(
        self,
    ) -> None:
        records = [
            _record(
                document=f"synthetic-{index}",
                ground_truth="quyết định",
                primary="quyet dinh",
                transformer="quyết định",
                paddle="quyết định",
            )
            for index in range(3)
        ]

        payload = build_analysis(
            records,
            {
                "groundTruthStatus": "USER_REVIEWED_CROP_GROUND_TRUTH",
                "predictionSource": "SYNTHETIC_TEST",
            },
            "a" * 64,
        )
        rendered = str(payload)

        self.assertFalse(payload["containsRealPII"])
        self.assertNotIn("quyết định", rendered)
        self.assertNotIn("synthetic-0", rendered)
        self.assertNotIn(
            "exact", payload["primaryErrorAnalysis"]["categoryCounts"]
        )
        self.assertEqual("SHADOW_REVIEW_ONLY", payload["recommendedPolicy"]["status"])
        self.assertFalse(
            payload["recommendedPolicy"]["autoAcceptChangedCandidate"]
        )


if __name__ == "__main__":
    unittest.main()
