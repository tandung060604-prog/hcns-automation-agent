from __future__ import annotations

import unittest

from apps.ocr_lab.api.run_phase14_8_session import line_decision


class Phase148SessionPolicyTests(unittest.TestCase):
    def test_exact_primary_transformer_agreement_only_marks_verified(self) -> None:
        decision = line_decision(
            "Nguyễn Thị Synthetic",
            0.91,
            "Nguyễn   Thị Synthetic",
        )

        self.assertEqual("verified", decision["status"])
        self.assertEqual("Nguyễn Thị Synthetic", decision["selectedText"])
        self.assertFalse(decision["autoReplacementApplied"])

    def test_disagreement_preserves_seq2seq_and_requires_review(self) -> None:
        decision = line_decision(
            "NGUYỄN SYNTHETIC",
            0.87,
            "Nguyễn Synthetic",
        )

        self.assertEqual("needs_review", decision["status"])
        self.assertEqual("NGUYỄN SYNTHETIC", decision["selectedText"])
        self.assertEqual("vietocr_vgg_seq2seq", decision["selectedProfile"])


if __name__ == "__main__":
    unittest.main()
