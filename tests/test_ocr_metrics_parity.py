from __future__ import annotations

import hashlib
import unittest

from hcns_agent.application.ocr_metrics import (
    METRIC_SPEC_VERSION,
    evaluate_text_pairs,
)
from hcns_agent.application.recognition_benchmark import (
    VietnameseRecognitionBenchmark,
)
from hcns_agent.domain.recognition import (
    RecognitionGroundTruth,
    RecognitionGroundTruthCase,
    RecognitionPredictionCase,
    RecognitionSubmission,
)
from scripts.phase14_5_error_analysis import LineRecord, aggregate_metrics


class OcrMetricParityTests(unittest.TestCase):
    def test_phase14_and_public_benchmark_use_identical_metric_semantics(
        self,
    ) -> None:
        references = ("PHẠM THỊ LINH", "Quận 1", "CỘNG   HÒA")
        predictions = ("PHAM THI LINH", "quận 1", "CO\u0323̂NG HÒA")
        records = [
            LineRecord(
                document_key="synthetic",
                ground_truth=reference,
                primary=prediction,
                transformer="",
                paddle="",
                primary_confidence=0.5,
            )
            for reference, prediction in zip(
                references,
                predictions,
                strict=True,
            )
        ]

        phase14 = aggregate_metrics(records, list(predictions))
        report = VietnameseRecognitionBenchmark().evaluate(
            _ground_truth(references),
            _submission(predictions),
        )
        canonical = evaluate_text_pairs(list(zip(references, predictions, strict=True)))

        self.assertEqual(METRIC_SPEC_VERSION, phase14["metricSpecVersion"])
        self.assertEqual(
            report.metrics.exact_match_count,
            phase14["exactMatchCount"],
        )
        self.assertEqual(report.metrics.exact_match_rate, phase14["exactMatchRate"])
        self.assertEqual(report.metrics.character_error_rate, phase14["cer"])
        self.assertEqual(report.metrics.word_error_rate, phase14["wer"])
        self.assertEqual(
            report.metrics.diacritic_error_rate,
            phase14["diacriticErrorRate"],
        )
        self.assertEqual(
            canonical.casefold_exact_rate,
            phase14["casefoldExactMatchRate"],
        )

    def test_casefold_agreement_does_not_inflate_strict_exact_match(self) -> None:
        metrics = evaluate_text_pairs([("Nguyễn Thị Mai", "NGUYỄN THỊ MAI")])

        self.assertEqual(0.0, metrics.strict_exact_rate)
        self.assertEqual(1.0, metrics.casefold_exact_rate)


def _ground_truth(references: tuple[str, ...]) -> RecognitionGroundTruth:
    return RecognitionGroundTruth(
        dataset_id="synthetic-parity",
        dataset_version="1",
        content_digest="sha256:" + hashlib.sha256(b"metric-parity").hexdigest(),
        authorized_for_local_evaluation=True,
        cases=tuple(
            RecognitionGroundTruthCase(case_id=f"LINE-{index}", text=text)
            for index, text in enumerate(references, start=1)
        ),
    )


def _submission(predictions: tuple[str, ...]) -> RecognitionSubmission:
    return RecognitionSubmission(
        dataset_id="synthetic-parity",
        dataset_version="1",
        backend_name="synthetic",
        backend_version="1",
        model_identifier="synthetic",
        cases=tuple(
            RecognitionPredictionCase(
                case_id=f"LINE-{index}",
                text=text,
                confidence=0.5,
                duration_ms=1,
            )
            for index, text in enumerate(predictions, start=1)
        ),
    )


if __name__ == "__main__":
    unittest.main()
