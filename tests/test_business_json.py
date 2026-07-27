import json
from pathlib import Path
from unittest import TestCase

from synthetic_fixtures import synthetic_cv_pdf_bytes

from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.application.business_json import BusinessJsonBuilder
from hcns_agent.bootstrap import build_default_pipeline
from hcns_agent.ports.document_parser import DocumentSource

_ROOT = Path(__file__).resolve().parents[1]


class BusinessJsonContractTests(TestCase):
    def make_payload(self) -> dict[str, object]:
        result = build_default_pipeline(DeterministicMockOcrEngine()).execute(
            DocumentSource(
                document_id="SYNTHETIC-BUSINESS-JSON",
                filename="cv.pdf",
                content=synthetic_cv_pdf_bytes(),
                source_reference="object://synthetic/cv",
            )
        )
        return BusinessJsonBuilder().build(result)

    def test_business_json_is_versioned_and_contains_provenance_not_raw_file(self) -> None:
        payload = self.make_payload()

        self.assertEqual("2.0.0", payload["schemaVersion"])
        self.assertEqual("CV", payload["documentType"])
        self.assertNotIn("canonicalDocument", payload)
        self.assertNotIn("rawFile", payload)
        fields = payload["fields"]
        self.assertIsInstance(fields, list)
        first_field = fields[0]
        self.assertTrue(first_field["provenance"])
        self.assertEqual("PENDING", payload["reviewStatus"])

    def test_business_json_matches_required_schema_contract(self) -> None:
        schema = json.loads(
            (_ROOT / "schemas" / "business_document.schema.json").read_text(encoding="utf-8")
        )
        payload = self.make_payload()

        self.assertEqual(
            schema["properties"]["schemaVersion"]["const"],
            payload["schemaVersion"],
        )
        self.assertTrue(set(schema["required"]).issubset(payload))
