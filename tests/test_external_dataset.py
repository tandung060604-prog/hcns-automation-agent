import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from jsonschema import Draft202012Validator
from synthetic_fixtures import synthetic_pptx_bytes

from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.application.external_dataset import (
    ExternalDatasetError,
    inventory_dataset,
    read_inventory,
    validate_inventory,
    validate_mapping,
    write_inventory,
)
from hcns_agent.bootstrap import build_default_intake
from hcns_agent.domain.documents import DocumentType, SourceFormat
from hcns_agent.ports.document_parser import DocumentSource
from scripts.prepare_external_dataset_ground_truth import (
    build_ground_truth_draft,
    preserve_all_review_state,
    preserve_non_contract_reviews,
)


class ExternalDatasetInventoryTests(TestCase):
    def setUp(self) -> None:
        temp_parent = Path("C:/tmp") if os.name == "nt" and Path("C:/tmp").is_dir() else None
        self.temp = TemporaryDirectory(dir=str(temp_parent) if temp_parent else None)
        self.root = Path(self.temp.name)
        (self.root / "cv").mkdir()
        (self.root / "contract").mkdir()
        (self.root / "ielts").mkdir()
        (self.root / "cv" / "sample.txt").write_text(
            "CV\nHọ tên: Synthetic Person\nKỹ năng: Python\n",
            encoding="utf-8",
        )
        (self.root / "contract" / "sample.txt").write_text(
            "HỢP ĐỒNG THỬ VIỆC\nHọ tên: Synthetic Person\n",
            encoding="utf-8",
        )
        (self.root / "ielts" / "sample.pptx").write_bytes(synthetic_pptx_bytes())
        (self.root / "README.md").write_text("ignored", encoding="utf-8")
        (self.root / "gen_cv.py").write_text("ignored", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_inventory_excludes_readme_and_generators_and_is_reproducible(self) -> None:
        first = inventory_dataset(
            self.root,
            dataset_id="synthetic-external",
            version="v1",
            source_commit="a" * 40,
        )
        second = inventory_dataset(
            self.root,
            dataset_id="synthetic-external",
            version="v1",
            source_commit="a" * 40,
        )

        self.assertEqual(first, second)
        self.assertEqual(3, first["dataset"]["documentCount"])
        self.assertNotIn("README.md", json.dumps(first))
        validate_inventory(self.root, first)

    def test_inventory_rejects_source_drift(self) -> None:
        inventory = inventory_dataset(
            self.root,
            dataset_id="synthetic-external",
            version="v1",
            source_commit="b" * 40,
        )
        (self.root / "cv" / "sample.txt").write_text("tampered", encoding="utf-8")

        with self.assertRaisesRegex(ExternalDatasetError, "digest mismatch"):
            validate_inventory(self.root, inventory)

    def test_inventory_round_trip_and_schema(self) -> None:
        inventory = inventory_dataset(
            self.root,
            dataset_id="synthetic-external",
            version="v1",
            source_commit="c" * 40,
        )
        with TemporaryDirectory() as output:
            path = Path(output) / "inventory.json"
            write_inventory(path, inventory)
            loaded = read_inventory(path)
        schema = json.loads(
            Path(__file__).parents[1]
            .joinpath("schemas", "external_dataset_inventory.schema.json")
            .read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(loaded)

    def test_contract_mapping_is_schema_valid_and_covers_all_categories(self) -> None:
        root = Path(__file__).parents[1]
        mapping_path = root / "config" / "external_dataset_mapping.json"
        schema_path = root / "schemas" / "external_dataset_mapping.schema.json"
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(mapping)
        self.assertEqual(
            {"cv", "contract", "ielts"},
            {str(item["category"]) for item in mapping["mappings"]},
        )

        inventory = inventory_dataset(
            self.root,
            dataset_id="vuhocpublic-data",
            version="2026-08-03-contract-probation",
            source_commit="dec17acbe2b409e0aa5daeb4db820d3e95d05bdf",
        )
        validate_mapping(inventory, mapping)
        mapping["datasetVersion"] = "drifted"
        with self.assertRaisesRegex(ExternalDatasetError, "version"):
            validate_mapping(inventory, mapping)

    def test_certificate_schema_and_ground_truth_draft_are_versioned(self) -> None:
        root = Path(__file__).parents[1]
        mapping = json.loads(
            (root / "config" / "external_dataset_mapping.json").read_text(encoding="utf-8")
        )
        inventory = inventory_dataset(
            self.root,
            dataset_id="vuhocpublic-data",
            version="2026-08-03-contract-probation",
            source_commit="dec17acbe2b409e0aa5daeb4db820d3e95d05bdf",
        )
        draft = build_ground_truth_draft(inventory, mapping)
        draft_schema = json.loads(
            (root / "schemas" / "external_dataset_ground_truth.schema.json").read_text(
                encoding="utf-8"
            )
        )
        certificate_schema = json.loads(
            (
                root
                / "schemas"
                / "hr_document_families"
                / "certificate.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(certificate_schema)
        Draft202012Validator(draft_schema).validate(draft)

        self.assertEqual("DRAFT", draft["dataset"]["groundTruthStatus"])
        self.assertTrue(draft["review"]["predictionBlindness"])
        certificate_case = next(
            case for case in draft["cases"] if case["documentType"] == "CERTIFICATE"
        )
        self.assertEqual(
            [
                "recipient_name",
                "credential_id",
                "credential_type",
                "overall_score",
                "issue_date",
            ],
            [field["name"] for field in certificate_case["fields"]],
        )
        self.assertIn(
            "family name + first name",
            certificate_schema["properties"]["payload"]["properties"]["fields"]["properties"][
                "recipient_name"
            ]["description"],
        )
        self.assertTrue(all(field["value"] is None for field in certificate_case["fields"]))
        contract_case = next(
            case for case in draft["cases"] if case["documentType"] == "EMPLOYMENT_CONTRACT"
        )
        self.assertEqual(14, len(contract_case["fields"]))
        self.assertEqual(
            "probation_salary_monthly",
            contract_case["fields"][11]["name"],
        )
        certificate_mapping = next(
            item for item in mapping["mappings"] if item["category"] == "ielts"
        )
        self.assertEqual(
            "schemas/hr_document_families/certificate.schema.json",
            certificate_mapping["schemaRef"],
        )

        probation_schema = json.loads(
            (
                root
                / "schemas"
                / "hr_document_families"
                / "probation_contract.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(probation_schema)
        contract_mapping = next(
            item for item in mapping["mappings"] if item["category"] == "contract"
        )
        self.assertEqual(
            "schemas/hr_document_families/probation_contract.schema.json",
            contract_mapping["schemaRef"],
        )
        self.assertIn("reduced 14-field", contract_mapping["mappingNote"])

    def test_contract_replacement_preserves_non_contract_review_state(self) -> None:
        root = Path(__file__).parents[1]
        mapping = json.loads(
            (root / "config" / "external_dataset_mapping.json").read_text(encoding="utf-8")
        )
        inventory = inventory_dataset(
            self.root,
            dataset_id="vuhocpublic-data",
            version="2026-08-03-contract-probation",
            source_commit="dec17acbe2b409e0aa5daeb4db820d3e95d05bdf",
        )
        previous = build_ground_truth_draft(inventory, mapping)
        cv_case = next(case for case in previous["cases"] if case["caseId"] == "cv-001")
        cv_case["fields"][0].update(value="reviewed", reviewStatus="CONFIRMED")
        cv_case["reviewRequired"] = False
        contract_case = next(
            case for case in previous["cases"] if case["caseId"] == "contract-001"
        )
        contract_case["fields"][0].update(value="stale", reviewStatus="CONFIRMED")
        previous["review"].update(status="CONFIRMED", reviewer="independent-reviewer")

        updated = preserve_non_contract_reviews(
            build_ground_truth_draft(inventory, mapping), previous
        )
        updated_cv = next(case for case in updated["cases"] if case["caseId"] == "cv-001")
        updated_contract = next(
            case for case in updated["cases"] if case["caseId"] == "contract-001"
        )
        self.assertEqual("reviewed", updated_cv["fields"][0]["value"])
        self.assertFalse(updated_cv["reviewRequired"])
        self.assertIsNone(updated_contract["fields"][0]["value"])
        self.assertEqual("PENDING", updated_contract["fields"][0]["reviewStatus"])
        self.assertEqual("IN_PROGRESS", updated["review"]["status"])

    def test_schema_migration_preserves_matching_contract_fields(self) -> None:
        root = Path(__file__).parents[1]
        mapping = json.loads(
            (root / "config" / "external_dataset_mapping.json").read_text(encoding="utf-8")
        )
        inventory = inventory_dataset(
            self.root,
            dataset_id="vuhocpublic-data",
            version="2026-08-03-contract-probation",
            source_commit="dec17acbe2b409e0aa5daeb4db820d3e95d05bdf",
        )
        previous = build_ground_truth_draft(inventory, mapping)
        old_contract = next(
            case for case in previous["cases"] if case["caseId"] == "contract-001"
        )
        old_contract["fields"][0].update(value="kept", reviewStatus="CONFIRMED")
        old_contract["reviewRequired"] = False

        migrated = preserve_all_review_state(build_ground_truth_draft(inventory, mapping), previous)
        migrated_contract = next(
            case for case in migrated["cases"] if case["caseId"] == "contract-001"
        )
        migrated_cv = next(case for case in migrated["cases"] if case["caseId"] == "cv-001")
        self.assertEqual("kept", migrated_contract["fields"][0]["value"])
        self.assertTrue(migrated_contract["reviewRequired"])
        self.assertEqual(10, len(migrated_cv["fields"]))
        self.assertFalse(migrated_cv["reviewRequired"])


class ExternalDatasetIntakeTests(TestCase):
    def test_plain_text_and_folder_mapping_reach_generic_contracts(self) -> None:
        intake = build_default_intake(DeterministicMockOcrEngine())
        contract = intake.execute(
            DocumentSource(
                document_id="contract-001",
                filename="contract.txt",
                content="HỢP ĐỒNG THỬ VIỆC\nHọ tên: Synthetic Person\n".encode(),
            )
        )
        self.assertIs(SourceFormat.PLAIN_TEXT, contract.source_format)
        self.assertEqual(1, len(contract.content.pages))

        from hcns_agent.bootstrap import build_default_understanding

        result = build_default_understanding().execute(contract)
        self.assertIs(DocumentType.EMPLOYMENT_CONTRACT, result.classification.document_type)
