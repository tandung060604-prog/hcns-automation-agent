from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from hcns_agent.adapters.recognition_json import (
    load_recognition_characters,
    load_recognition_ground_truth,
    load_recognition_submission,
)
from hcns_agent.application.recognition_benchmark import (
    VietnameseRecognitionBenchmark,
    audit_vietnamese_charset,
    required_vietnamese_extended_characters,
    strip_vietnamese_diacritics,
)
from hcns_agent.recognition_cli import main


class VietnameseRecognitionBenchmarkTests(unittest.TestCase):
    def test_diacritic_loss_is_measured_separately_from_base_letter_loss(self) -> None:
        ground_truth, submission = _contracts(
            references=("CỘNG HÒA", "KỸ NĂNG"),
            predictions=("CONG HOA", "KY NANG"),
            confidences=(0.99, 0.98),
        )

        report = VietnameseRecognitionBenchmark().evaluate(ground_truth, submission)

        self.assertGreater(report.metrics.character_error_rate, 0.0)
        self.assertGreater(report.metrics.diacritic_error_rate, 0.0)
        self.assertEqual(0.0, report.metrics.accepted_precision)
        self.assertEqual(2, report.metrics.accepted_count)

    def test_nfc_and_whitespace_are_normalized_without_removing_accents(self) -> None:
        ground_truth, submission = _contracts(
            references=("CỘNG   HÒA",),
            predictions=("CO\u0323̂NG HÒA",),
            confidences=(0.99,),
        )

        report = VietnameseRecognitionBenchmark().evaluate(ground_truth, submission)

        self.assertEqual(1.0, report.metrics.exact_match_rate)
        self.assertEqual(1, report.metrics.prediction_nfc_violation_count)
        self.assertEqual("CONG HOA", strip_vietnamese_diacritics("CỘNG HÒA"))

    def test_full_charset_contains_134_non_ascii_vietnamese_letters(self) -> None:
        required = "".join(required_vietnamese_extended_characters())
        report = audit_vietnamese_charset(required, model_identifier="synthetic-full")

        self.assertEqual(134, report.required_character_count)
        self.assertEqual(134, report.present_character_count)
        self.assertEqual(0, report.missing_character_count)
        self.assertEqual(1.0, report.coverage)


class RecognitionJsonTests(unittest.TestCase):
    def test_paddle_inference_yaml_character_dictionary_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            model_path = Path(temporary_directory) / "inference.yml"
            model_path.write_text(
                "PostProcess:\n"
                "  name: CTCLabelDecode\n"
                "  character_dict:\n"
                "  - A\n"
                "  - Ễ\n"
                "  - đ\n",
                encoding="utf-8",
            )

            characters = load_recognition_characters(model_path)

            self.assertEqual("AỄđ", characters)

    def test_recognition_schemas_are_valid_json(self) -> None:
        schema_root = Path(__file__).resolve().parents[1] / "schemas"
        for filename in (
            "recognition_ground_truth.schema.json",
            "recognition_predictions.schema.json",
            "recognition_report.schema.json",
        ):
            payload = json.loads((schema_root / filename).read_text(encoding="utf-8"))
            self.assertEqual(
                "https://json-schema.org/draft/2020-12/schema",
                payload["$schema"],
            )
            self.assertEqual("object", payload["type"])

    def test_cli_report_is_aggregate_only_and_contains_no_raw_text(self) -> None:
        reference = "ĐƠN XIN NGHỈ PHÉP"
        prediction = "DON XIN NGHI PHEP"
        digest = "sha256:" + hashlib.sha256(b"synthetic-lines").hexdigest()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ground_truth_path = root / "ground-truth.json"
            prediction_path = root / "prediction.json"
            report_path = root / "report.json"
            ground_truth_path.write_text(
                json.dumps(
                    {
                        "datasetId": "synthetic-vi-lines",
                        "datasetVersion": "1",
                        "contentDigest": digest,
                        "authorizedForLocalEvaluation": True,
                        "cases": [{"caseId": "LINE-001", "text": reference}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            prediction_path.write_text(
                json.dumps(
                    {
                        "datasetId": "synthetic-vi-lines",
                        "datasetVersion": "1",
                        "backendName": "synthetic",
                        "backendVersion": "1",
                        "modelIdentifier": "synthetic-no-diacritics",
                        "cases": [
                            {
                                "caseId": "LINE-001",
                                "text": prediction,
                                "confidence": 0.99,
                                "durationMs": 5,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "evaluate",
                    "--ground-truth",
                    str(ground_truth_path),
                    "--predictions",
                    str(prediction_path),
                    "--output",
                    str(report_path),
                ]
            )

            self.assertEqual(0, exit_code)
            serialized = report_path.read_text(encoding="utf-8")
            self.assertNotIn(reference, serialized)
            self.assertNotIn(prediction, serialized)
            self.assertIn('"diacriticErrorRate"', serialized)

    def test_private_input_contracts_round_trip(self) -> None:
        ground_truth, submission = _contracts(
            references=("PHIẾU THÔNG TIN",),
            predictions=("PHIEU THONG TIN",),
            confidences=(0.9,),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ground_truth_path = root / "ground-truth.json"
            prediction_path = root / "prediction.json"
            ground_truth_path.write_text(
                json.dumps(
                    {
                        "datasetId": ground_truth.dataset_id,
                        "datasetVersion": ground_truth.dataset_version,
                        "contentDigest": ground_truth.content_digest,
                        "authorizedForLocalEvaluation": True,
                        "cases": [{"caseId": "LINE-001", "text": "PHIẾU THÔNG TIN"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            prediction_path.write_text(
                json.dumps(
                    {
                        "datasetId": submission.dataset_id,
                        "datasetVersion": submission.dataset_version,
                        "backendName": submission.backend_name,
                        "backendVersion": submission.backend_version,
                        "modelIdentifier": submission.model_identifier,
                        "cases": [
                            {
                                "caseId": "LINE-001",
                                "text": "PHIEU THONG TIN",
                                "confidence": 0.9,
                                "durationMs": 5,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            loaded_ground_truth = load_recognition_ground_truth(ground_truth_path)
            loaded_submission = load_recognition_submission(prediction_path)

            self.assertEqual(ground_truth, loaded_ground_truth)
            self.assertEqual(submission, loaded_submission)


def _contracts(
    *,
    references: tuple[str, ...],
    predictions: tuple[str, ...],
    confidences: tuple[float, ...],
):
    from hcns_agent.domain.recognition import (
        RecognitionGroundTruth,
        RecognitionGroundTruthCase,
        RecognitionPredictionCase,
        RecognitionSubmission,
    )

    cases = tuple(
        RecognitionGroundTruthCase(case_id=f"LINE-{index:03d}", text=text)
        for index, text in enumerate(references, start=1)
    )
    predicted_cases = tuple(
        RecognitionPredictionCase(
            case_id=f"LINE-{index:03d}",
            text=text,
            confidence=confidence,
            duration_ms=5.0,
        )
        for index, (text, confidence) in enumerate(
            zip(predictions, confidences, strict=True),
            start=1,
        )
    )
    digest = "sha256:" + hashlib.sha256(b"synthetic-lines").hexdigest()
    return (
        RecognitionGroundTruth(
            dataset_id="synthetic-vi-lines",
            dataset_version="1",
            content_digest=digest,
            authorized_for_local_evaluation=True,
            cases=cases,
        ),
        RecognitionSubmission(
            dataset_id="synthetic-vi-lines",
            dataset_version="1",
            backend_name="synthetic",
            backend_version="1",
            model_identifier="synthetic-model",
            cases=predicted_cases,
        ),
    )


if __name__ == "__main__":
    unittest.main()
