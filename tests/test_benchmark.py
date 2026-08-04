from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path

from synthetic_fixtures import synthetic_cv_pdf_bytes

from hcns_agent.adapters.benchmark_json import (
    BenchmarkJsonError,
    load_ground_truth,
    load_submission,
    report_to_dict,
)
from hcns_agent.adapters.benchmark_runtime import LocalSourcePageCounter
from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.application.benchmark import (
    BenchmarkHarness,
    BenchmarkInputError,
    PromotionGate,
    compute_dataset_digest,
    prediction_case_from_idp_result,
    validate_authorized_manifest,
)
from hcns_agent.application.benchmark_runner import BenchmarkRunner, BenchmarkRunPolicy
from hcns_agent.benchmark_cli import main
from hcns_agent.bootstrap import build_default_pipeline
from hcns_agent.domain.documents import DocumentType
from hcns_agent.domain.evaluation import (
    BenchmarkSubmission,
    DataClassification,
    DatasetAuthorizationStatus,
    DatasetManifest,
    ExpectedField,
    GroundTruthCase,
    PredictedField,
    PredictionCase,
    PromotionEvidence,
    PromotionPolicy,
    PromotionStatus,
    StorageProtection,
)
from hcns_agent.domain.models import FieldStatus
from hcns_agent.domain.understanding import IdpResult, QualityStatus
from hcns_agent.ports.document_parser import DocumentSource

_SOURCE_DIGEST_1 = "sha256:" + "b" * 64
_SOURCE_DIGEST_2 = "sha256:" + "c" * 64


class BenchmarkHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = _manifest()
        self.ground_truth = _ground_truth()

    def test_metrics_are_per_type_per_field_and_aggregate_only(self) -> None:
        report = BenchmarkHarness().evaluate(
            self.manifest,
            self.ground_truth,
            _baseline_submission(),
        )

        self.assertEqual(2, report.case_count)
        self.assertEqual(0.5, report.classification.macro_f1)
        self.assertEqual(0.5, report.classification.unknown_rate)
        self.assertEqual(1, report.ocr.evaluated_cases)
        self.assertGreater(report.ocr.character_error_rate, 0.0)
        self.assertGreater(report.ocr.word_error_rate, 0.0)
        self.assertEqual(0.0, report.ocr.reading_order_accuracy)
        self.assertEqual(3, report.extraction.expected_count)
        self.assertEqual(2, report.extraction.predicted_count)
        self.assertEqual(1, report.extraction.exact_match_count)
        self.assertEqual(1, report.extraction.not_found_count)
        self.assertEqual(0, report.quality.sensitive_false_acceptance_count)
        self.assertEqual(0.5, report.quality.review_precision)
        self.assertEqual(10.0, report.system.latency_p50_ms)
        self.assertEqual(20.0, report.system.latency_p95_ms)

        serialized = json.dumps(report_to_dict(report), sort_keys=True)
        self.assertNotIn("Synthetic Candidate", serialized)
        self.assertNotIn("Python", serialized)
        self.assertNotIn("Incorrect Skill", serialized)
        self.assertNotIn("CURRICULUM VITAE", serialized)

    def test_case_set_must_match_exactly(self) -> None:
        incomplete = BenchmarkSubmission(
            dataset_id=self.manifest.dataset_id,
            dataset_version=self.manifest.version,
            backend_name="baseline",
            backend_version="1",
            model_identifiers=(),
            cases=(_baseline_submission().cases[0],),
        )
        with self.assertRaisesRegex(BenchmarkInputError, "case IDs"):
            BenchmarkHarness().evaluate(self.manifest, self.ground_truth, incomplete)

    def test_manifest_digest_and_authorization_are_enforced(self) -> None:
        validate_authorized_manifest(self.manifest, as_of=date(2026, 7, 27))
        invalid_manifest = DatasetManifest(
            dataset_id=self.manifest.dataset_id,
            version=self.manifest.version,
            content_digest="sha256:" + "0" * 64,
            purpose=self.manifest.purpose,
            rights_basis=self.manifest.rights_basis,
            data_owner=self.manifest.data_owner,
            approved_by=self.manifest.approved_by,
            approval_reference=self.manifest.approval_reference,
            approved_at=self.manifest.approved_at,
            retention_until=self.manifest.retention_until,
            authorization_status=self.manifest.authorization_status,
            storage_protection=self.manifest.storage_protection,
            data_classification=self.manifest.data_classification,
            document_count=self.manifest.document_count,
            page_count=self.manifest.page_count,
        )
        with self.assertRaisesRegex(BenchmarkInputError, "content_digest"):
            BenchmarkHarness().evaluate(
                invalid_manifest,
                self.ground_truth,
                _baseline_submission(),
            )

    def test_idp_result_uses_the_same_vendor_neutral_prediction_contract(self) -> None:
        result = build_default_pipeline(DeterministicMockOcrEngine()).execute(
            DocumentSource(
                document_id="SYN-M3-IDP",
                filename="unsupported.pdf",
                content=synthetic_cv_pdf_bytes(),
                source_reference="object://synthetic/SYN-M3-IDP",
            )
        )

        prediction = prediction_case_from_idp_result(result, latency_ms=12.5)

        self.assertEqual(result.document_id, prediction.case_id)
        self.assertIs(result.classification.document_type, prediction.document_type)
        self.assertEqual(result.quality.status, prediction.quality_status)
        self.assertEqual(
            [(field.name, field.status) for field in result.fields],
            [(field.name, field.status) for field in prediction.fields],
        )
        self.assertTrue(prediction.ocr_lines)

    def test_promotion_gate_accepts_verified_improvement(self) -> None:
        harness = BenchmarkHarness()
        baseline = harness.evaluate(
            self.manifest, self.ground_truth, _baseline_submission()
        )
        challenger = harness.evaluate(
            self.manifest, self.ground_truth, _challenger_submission()
        )
        policy = PromotionPolicy(
            minimum_field_exact_match_improvement=0.10,
            maximum_latency_p95_ms=30.0,
            maximum_review_rate_increase=0.0,
            maximum_failure_rate=0.0,
            minimum_benchmark_pages=30,
        )
        decision = PromotionGate(policy).evaluate(
            self.manifest,
            baseline,
            challenger,
            _approved_evidence(),
            as_of=date(2026, 7, 27),
        )

        self.assertIs(PromotionStatus.PROMOTE, decision.status)
        self.assertTrue(all(check.passed for check in decision.checks))

    def test_promotion_holds_on_sensitive_false_acceptance_or_missing_approval(self) -> None:
        harness = BenchmarkHarness()
        baseline = harness.evaluate(
            self.manifest, self.ground_truth, _baseline_submission()
        )
        unsafe = _challenger_submission(accept_sensitive=True)
        challenger = harness.evaluate(self.manifest, self.ground_truth, unsafe)
        decision = PromotionGate(
            PromotionPolicy(maximum_latency_p95_ms=30.0, maximum_failure_rate=0.0)
        ).evaluate(
            self.manifest,
            baseline,
            challenger,
            PromotionEvidence(
                contract_tests_passed=True,
                privacy_approved=False,
                license_approved=True,
                model_provenance_approved=True,
            ),
            as_of=date(2026, 7, 27),
        )

        failed_codes = {check.code for check in decision.checks if not check.passed}
        self.assertIs(PromotionStatus.HOLD, decision.status)
        self.assertIn("NO_SENSITIVE_FALSE_ACCEPTANCE_INCREASE", failed_codes)
        self.assertIn("PRIVACY_APPROVAL", failed_codes)


class BenchmarkJsonTests(unittest.TestCase):
    def test_json_boundary_rejects_uncontracted_raw_content(self) -> None:
        payload = _ground_truth_payload()
        payload["rawText"] = "must-not-cross-boundary"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ground-truth.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(BenchmarkJsonError, "unsupported properties"):
                load_ground_truth(path)

    def test_json_boundary_and_cli_emit_no_raw_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ground_truth_path = root / "ground-truth.json"
            predictions_path = root / "predictions.json"
            challenger_path = root / "challenger.json"
            output_path = root / "report.json"
            comparison_path = root / "comparison.json"
            ground_truth_path.write_text(
                json.dumps(_ground_truth_payload(), ensure_ascii=False),
                encoding="utf-8",
            )
            predictions_path.write_text(
                json.dumps(_prediction_payload(), ensure_ascii=False),
                encoding="utf-8",
            )
            challenger_path.write_text(
                json.dumps(
                    _prediction_payload(_challenger_submission()),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest, cases = load_ground_truth(ground_truth_path)
            submission = load_submission(predictions_path)
            self.assertEqual("synthetic-m3", manifest.dataset_id)
            self.assertEqual(2, len(cases))
            self.assertEqual("baseline", submission.backend_name)

            exit_code = main(
                [
                    "evaluate",
                    "--ground-truth",
                    str(ground_truth_path),
                    "--predictions",
                    str(predictions_path),
                    "--output",
                    str(output_path),
                ]
            )
            report_text = output_path.read_text(encoding="utf-8")
            self.assertEqual(0, exit_code)
            self.assertNotIn("Synthetic Candidate", report_text)
            self.assertNotIn("Incorrect Skill", report_text)
            self.assertIn('"macroF1"', report_text)

            compare_exit_code = main(
                [
                    "compare",
                    "--ground-truth",
                    str(ground_truth_path),
                    "--baseline",
                    str(predictions_path),
                    "--challenger",
                    str(challenger_path),
                    "--output",
                    str(comparison_path),
                    "--contract-tests-passed",
                    "--privacy-approved",
                    "--license-approved",
                    "--model-provenance-approved",
                ]
            )
            comparison_text = comparison_path.read_text(encoding="utf-8")
            self.assertEqual(0, compare_exit_code)
            self.assertIn('"status": "PROMOTE"', comparison_text)
            self.assertNotIn("Synthetic Candidate", comparison_text)
            self.assertNotIn("CURRICULUM VITAE", comparison_text)

    def test_benchmark_schemas_are_valid_json(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        for name in (
            "benchmark_comparison.schema.json",
            "benchmark_ground_truth.schema.json",
            "benchmark_predictions.schema.json",
            "benchmark_report.schema.json",
        ):
            payload = json.loads((repository_root / "schemas" / name).read_text("utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", payload["$schema"])


class BenchmarkRunnerTests(unittest.TestCase):
    def test_runner_verifies_authorization_digest_hash_and_page_count(self) -> None:
        content = synthetic_cv_pdf_bytes()
        source_digest = "sha256:" + hashlib.sha256(content).hexdigest()
        ground_truth = (
            GroundTruthCase(
                case_id="SYN-RUN-001",
                source_relative_path="sources/unsupported.pdf",
                source_sha256=source_digest,
                page_count=30,
                document_type=DocumentType.UNKNOWN,
                fields=(ExpectedField("entry_count", 8),),
                expected_quality_status=QualityStatus.PASS,
                review_required=False,
            ),
        )
        manifest = _authorized_manifest("synthetic-run", ground_truth)
        backend = _FakeBenchmarkBackend()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "sources" / "unsupported.pdf"
            source_path.parent.mkdir()
            source_path.write_bytes(content)

            runner = BenchmarkRunner(
                _FixedPageCounter(30),
                policy=BenchmarkRunPolicy(require_outside_git=False),
            )
            submission = runner.run(
                manifest,
                ground_truth,
                backend,
                private_root=root,
                output_directory=root / "runs" / "fake",
            )

            self.assertEqual(manifest.dataset_id, submission.dataset_id)
            self.assertEqual((ground_truth[0].case_id,), tuple(
                case.case_id for case in submission.cases
            ))
            self.assertIsNone(submission.cases[0].failure_code)

            source_path.write_bytes(b"changed")
            with self.assertRaisesRegex(BenchmarkInputError, "digest mismatch"):
                runner.run(
                    manifest,
                    ground_truth,
                    backend,
                    private_root=root,
                    output_directory=root / "runs" / "second",
                )

    def test_local_page_counter_accepts_images(self) -> None:
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
        source = DocumentSource("SYN-PAGE", "page.png", buffer.getvalue())
        self.assertEqual(1, LocalSourcePageCounter().count_pages(source))


class _FixedPageCounter:
    def __init__(self, page_count: int) -> None:
        self._page_count = page_count

    def count_pages(self, source: DocumentSource) -> int:
        del source
        return self._page_count


class _FakeBenchmarkBackend:
    name = "fake-local"
    version = "1.0.0"
    model_identifiers = ("synthetic-model",)

    def process(
        self,
        source: DocumentSource,
        *,
        source_path: Path,
        output_directory: Path,
    ) -> IdpResult:
        del source_path, output_directory
        return build_default_pipeline(DeterministicMockOcrEngine()).execute(source)


def _authorized_manifest(
    dataset_id: str,
    ground_truth: tuple[GroundTruthCase, ...],
) -> DatasetManifest:
    return DatasetManifest(
        dataset_id=dataset_id,
        version="1.0.0",
        content_digest=compute_dataset_digest(dataset_id, "1.0.0", ground_truth),
        purpose="Synthetic benchmark runner regression",
        rights_basis="Project-generated synthetic data",
        data_owner="test-owner",
        approved_by="test-policy",
        approval_reference="TEST-AUTH-RUNNER",
        approved_at=date(2026, 7, 1),
        retention_until=date(2027, 7, 1),
        authorization_status=DatasetAuthorizationStatus.APPROVED,
        storage_protection=StorageProtection.ENTERPRISE_MANAGED,
        data_classification=DataClassification.PUBLIC,
        document_count=len(ground_truth),
        page_count=sum(case.page_count for case in ground_truth),
    )


def _manifest() -> DatasetManifest:
    ground_truth = _ground_truth()
    return DatasetManifest(
        dataset_id="synthetic-m3",
        version="1.0.0",
        content_digest=compute_dataset_digest(
            "synthetic-m3",
            "1.0.0",
            ground_truth,
        ),
        purpose="Synthetic benchmark contract regression",
        rights_basis="Project-generated synthetic data",
        data_owner="test-owner",
        approved_by="test-policy",
        approval_reference="TEST-AUTH-001",
        approved_at=date(2026, 7, 1),
        retention_until=date(2027, 7, 1),
        authorization_status=DatasetAuthorizationStatus.APPROVED,
        storage_protection=StorageProtection.ENTERPRISE_MANAGED,
        data_classification=DataClassification.PUBLIC,
        document_count=len(ground_truth),
        page_count=sum(case.page_count for case in ground_truth),
    )


def _ground_truth() -> tuple[GroundTruthCase, ...]:
    return (
        GroundTruthCase(
            case_id="SYN-M3-001",
            source_relative_path="sources/synthetic-cv.pdf",
            source_sha256=_SOURCE_DIGEST_1,
            page_count=20,
            document_type=DocumentType.CV,
            fields=(
                ExpectedField("full_name", "Synthetic Candidate", sensitive=True),
                ExpectedField("skills", "Python"),
            ),
            expected_quality_status=QualityStatus.REVIEW_REQUIRED,
            review_required=True,
            ocr_lines=("CURRICULUM VITAE", "Synthetic Candidate"),
        ),
        GroundTruthCase(
            case_id="SYN-M3-002",
            source_relative_path="sources/synthetic-unsupported.pdf",
            source_sha256=_SOURCE_DIGEST_2,
            page_count=20,
            document_type=DocumentType.EMPLOYEE_PROFILE,
            fields=(ExpectedField("entry_count", 8),),
            expected_quality_status=QualityStatus.PASS,
            review_required=False,
        ),
    )


def _baseline_submission() -> BenchmarkSubmission:
    return BenchmarkSubmission(
        dataset_id="synthetic-m3",
        dataset_version="1.0.0",
        backend_name="baseline",
        backend_version="rules-v1",
        model_identifiers=("mock-ocr-v1",),
        cases=(
            PredictionCase(
                case_id="SYN-M3-001",
                document_type=DocumentType.CV,
                fields=(
                    PredictedField(
                        "full_name",
                        "Synthetic Candidate",
                        FieldStatus.NEEDS_REVIEW,
                        True,
                    ),
                    PredictedField(
                        "skills",
                        "Incorrect Skill",
                        FieldStatus.ACCEPTED,
                        False,
                    ),
                ),
                quality_status=QualityStatus.REVIEW_REQUIRED,
                review_required=True,
                latency_ms=10.0,
                ocr_lines=("CURRICULUM VITAE", "Synthetic Candidat"),
            ),
            PredictionCase(
                case_id="SYN-M3-002",
                document_type=DocumentType.UNKNOWN,
                fields=(),
                quality_status=QualityStatus.REVIEW_REQUIRED,
                review_required=True,
                latency_ms=20.0,
            ),
        ),
    )


def _challenger_submission(*, accept_sensitive: bool = False) -> BenchmarkSubmission:
    sensitive_status = (
        FieldStatus.ACCEPTED if accept_sensitive else FieldStatus.NEEDS_REVIEW
    )
    return BenchmarkSubmission(
        dataset_id="synthetic-m3",
        dataset_version="1.0.0",
        backend_name="challenger",
        backend_version="rules-v2",
        model_identifiers=("mock-ocr-v2",),
        cases=(
            PredictionCase(
                case_id="SYN-M3-001",
                document_type=DocumentType.CV,
                fields=(
                    PredictedField(
                        "full_name", "Synthetic Candidate", sensitive_status, True
                    ),
                    PredictedField("skills", "Python", FieldStatus.ACCEPTED, False),
                ),
                quality_status=QualityStatus.REVIEW_REQUIRED,
                review_required=True,
                latency_ms=15.0,
                ocr_lines=("CURRICULUM VITAE", "Synthetic Candidate"),
            ),
            PredictionCase(
                case_id="SYN-M3-002",
                document_type=DocumentType.EMPLOYEE_PROFILE,
                fields=(
                    PredictedField("entry_count", 8, FieldStatus.ACCEPTED, False),
                ),
                quality_status=QualityStatus.PASS,
                review_required=False,
                latency_ms=25.0,
            ),
        ),
    )


def _approved_evidence() -> PromotionEvidence:
    return PromotionEvidence(
        contract_tests_passed=True,
        privacy_approved=True,
        license_approved=True,
        model_provenance_approved=True,
    )


def _ground_truth_payload() -> dict[str, object]:
    manifest = _manifest()
    return {
        "schemaVersion": "1.0.0",
        "manifest": {
            "datasetId": manifest.dataset_id,
            "version": manifest.version,
            "contentDigest": manifest.content_digest,
            "purpose": manifest.purpose,
            "rightsBasis": manifest.rights_basis,
            "dataOwner": manifest.data_owner,
            "approvedBy": manifest.approved_by,
            "approvalReference": manifest.approval_reference,
            "approvedAt": manifest.approved_at.isoformat(),
            "retentionUntil": manifest.retention_until.isoformat(),
            "authorizationStatus": manifest.authorization_status.value,
            "storageProtection": manifest.storage_protection.value,
            "dataClassification": manifest.data_classification.value,
            "documentCount": manifest.document_count,
            "pageCount": manifest.page_count,
        },
        "cases": [
            {
                "caseId": case.case_id,
                "sourceRelativePath": case.source_relative_path,
                "sourceSha256": case.source_sha256,
                "pageCount": case.page_count,
                "documentType": case.document_type.value,
                "fields": [
                    {
                        "name": field.name,
                        "value": field.value,
                        "sensitive": field.sensitive,
                    }
                    for field in case.fields
                ],
                "expectedQualityStatus": case.expected_quality_status.value,
                "reviewRequired": case.review_required,
                "ocrLines": list(case.ocr_lines),
            }
            for case in _ground_truth()
        ],
    }


def _prediction_payload(
    submission: BenchmarkSubmission | None = None,
) -> dict[str, object]:
    selected_submission = submission or _baseline_submission()
    return {
        "schemaVersion": "1.0.0",
        "datasetId": selected_submission.dataset_id,
        "datasetVersion": selected_submission.dataset_version,
        "backendName": selected_submission.backend_name,
        "backendVersion": selected_submission.backend_version,
        "modelIdentifiers": list(selected_submission.model_identifiers),
        "cases": [
            {
                "caseId": case.case_id,
                "documentType": case.document_type.value,
                "fields": [
                    {
                        "name": field.name,
                        "value": field.value,
                        "status": field.status.value,
                        "sensitive": field.sensitive,
                    }
                    for field in case.fields
                ],
                "qualityStatus": case.quality_status.value,
                "reviewRequired": case.review_required,
                "latencyMs": case.latency_ms,
                "failureCode": case.failure_code,
                "ocrLines": list(case.ocr_lines),
            }
            for case in selected_submission.cases
        ],
    }


if __name__ == "__main__":
    unittest.main()
