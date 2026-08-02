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
            version="2026-07-31-dec17acb",
            source_commit="dec17acbe2b409e0aa5daeb4db820d3e95d05bdf",
        )
        validate_mapping(inventory, mapping)
        mapping["datasetVersion"] = "drifted"
        with self.assertRaisesRegex(ExternalDatasetError, "version"):
            validate_mapping(inventory, mapping)


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
