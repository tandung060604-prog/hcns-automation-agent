from __future__ import annotations

import unittest

from apps.ocr_lab.api.canonical_phase_metrics import aggregate_profile
from hcns_agent.application.ocr_metrics import (
    METRIC_SPEC_VERSION,
    evaluate_text_pairs,
)


class OcrLabPhaseMetricParityTests(unittest.TestCase):
    def test_private_phase_adapter_matches_canonical_metric_spec(self) -> None:
        cases = [
            {
                "groundTruth": "PHẠM THỊ LINH",
                "predictions": {
                    "candidate": {
                        "text": "PHAM THI LINH",
                        "durationMs": 2,
                    }
                },
            },
            {
                "groundTruth": "Quận 1",
                "predictions": {
                    "candidate": {
                        "text": "quận 1",
                        "durationMs": 4,
                    }
                },
            },
        ]

        phase = aggregate_profile(
            cases,
            "candidate",
            lambda case: str(case["groundTruth"]),
        )
        canonical = evaluate_text_pairs(
            [
                (
                    str(case["groundTruth"]),
                    str(case["predictions"]["candidate"]["text"]),
                )
                for case in cases
            ]
        )

        self.assertEqual(METRIC_SPEC_VERSION, phase["metricSpecVersion"])
        self.assertEqual(canonical.strict_exact_rate, phase["exactMatchRate"])
        self.assertEqual(canonical.casefold_exact_rate, phase["casefoldExactMatchRate"])
        self.assertEqual(canonical.character_error_rate, phase["cer"])
        self.assertEqual(canonical.word_error_rate, phase["wer"])
        self.assertEqual(canonical.diacritic_error_rate, phase["diacriticErrorRate"])
        self.assertEqual(3.0, phase["meanDurationMs"])
        self.assertEqual(4.0, phase["p95DurationMs"])


if __name__ == "__main__":
    unittest.main()
