import hashlib
import json
from pathlib import Path
from unittest import TestCase

from jsonschema import Draft202012Validator

from hcns_agent.application.external_dataset import ExternalDatasetError
from scripts.build_external_dataset_typed_projection import (
    FIELD_SPECS,
    build_typed_projection,
)
from scripts.run_external_dataset_aggregate_pilot import build_aggregate_report


class ExternalDatasetData09Tests(TestCase):
    def test_typed_projection_preserves_source_and_normalizes_active_fields(self) -> None:
        ground_truth, inventory = _fixture()
        serialized = json.dumps(ground_truth, ensure_ascii=False, sort_keys=True).encode()
        ground_truth_sha256 = f"sha256:{hashlib.sha256(serialized).hexdigest()}"
        marker = {
            "datasetId": "synthetic-external",
            "contentDigest": inventory["dataset"]["contentDigest"],
            "groundTruthSha256": ground_truth_sha256,
            "predictionsOpened": False,
        }

        projection = build_typed_projection(
            ground_truth,
            inventory,
            marker,
            ground_truth_sha256=ground_truth_sha256,
        )

        contract = next(
            document for document in projection["documents"] if document["category"] == "contract"
        )
        fields = {field["name"]: field for field in contract["fields"]}
        self.assertEqual("03/08/2026", fields["contract_sign_date"]["sourceValue"])
        self.assertEqual("2026-08-03", fields["contract_sign_date"]["normalizedValue"])
        self.assertEqual(40, fields["weekly_hours"]["normalizedValue"])
        self.assertEqual(12750000, fields["probation_salary_monthly"]["normalizedValue"])
        self.assertEqual("NORMALIZED", fields["probation_salary_monthly"]["normalizationStatus"])

        cv = next(document for document in projection["documents"] if document["category"] == "cv")
        cv_fields = {field["name"]: field for field in cv["fields"]}
        self.assertEqual(2.5, cv_fields["years_experience"]["normalizedValue"])

        ielts = next(
            document for document in projection["documents"] if document["category"] == "ielts"
        )
        ielts_fields = {field["name"]: field for field in ielts["fields"]}
        self.assertEqual(6.5, ielts_fields["overall_score"]["normalizedValue"])
        self.assertEqual(
            "family_name_plus_first_name",
            ielts_fields["recipient_name"]["semantic"],
        )

        out_of_scope = next(
            document
            for document in projection["documents"]
            if document["scopeStatus"] == "OUT_OF_SCOPE"
        )
        self.assertTrue(
            all(field["normalizationStatus"] == "OUT_OF_SCOPE" for field in out_of_scope["fields"])
        )

    def test_aggregate_report_is_count_only_and_schema_valid(self) -> None:
        ground_truth, inventory = _fixture()
        serialized = json.dumps(ground_truth, ensure_ascii=False, sort_keys=True).encode()
        digest = f"sha256:{hashlib.sha256(serialized).hexdigest()}"
        projection = build_typed_projection(
            ground_truth,
            inventory,
            {
                "datasetId": "synthetic-external",
                "contentDigest": inventory["dataset"]["contentDigest"],
                "groundTruthSha256": digest,
                "predictionsOpened": False,
            },
            ground_truth_sha256=digest,
        )
        report = build_aggregate_report(projection)

        self.assertEqual(3, report["scope"]["activeDocumentCount"])
        self.assertEqual(29, report["scope"]["activeFieldCount"])
        self.assertEqual(1, report["scope"]["outOfScopeDocumentCount"])
        self.assertFalse(report["reportPolicy"]["containsRawFieldValues"])
        self.assertNotIn("Synthetic Candidate", json.dumps(report, ensure_ascii=False))
        self.assertNotIn("sourceValue", report)

        root = Path(__file__).parents[1]
        projection_schema = json.loads(
            (root / "schemas" / "external_dataset_typed_projection.schema.json").read_text(
                encoding="utf-8"
            )
        )
        report_schema = json.loads(
            (root / "schemas" / "external_dataset_aggregate_pilot.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator(projection_schema).validate(projection)
        Draft202012Validator(report_schema).validate(report)

    def test_projection_rejects_unsealed_ground_truth_or_open_predictions(self) -> None:
        ground_truth, inventory = _fixture()
        serialized = json.dumps(ground_truth, ensure_ascii=False, sort_keys=True).encode()
        digest = f"sha256:{hashlib.sha256(serialized).hexdigest()}"
        marker = {
            "datasetId": "synthetic-external",
            "contentDigest": inventory["dataset"]["contentDigest"],
            "groundTruthSha256": digest,
            "predictionsOpened": False,
        }
        ground_truth["dataset"]["groundTruthStatus"] = "DRAFT"
        with self.assertRaisesRegex(ExternalDatasetError, "SEALED"):
            build_typed_projection(ground_truth, inventory, marker, ground_truth_sha256=digest)

        ground_truth["dataset"]["groundTruthStatus"] = "SEALED"
        marker["predictionsOpened"] = True
        with self.assertRaisesRegex(ExternalDatasetError, "predictions"):
            build_typed_projection(ground_truth, inventory, marker, ground_truth_sha256=digest)


def _fixture() -> tuple[dict[str, object], dict[str, object]]:
    cases = [
        _case("contract-001", "contract", "DOCX", "EMPLOYMENT_CONTRACT", {
            "contract_sign_date": "03/08/2026",
            "effective_date": "Ngày 03 tháng 08 năm 2026",
            "probation_end_date": "03-10-2026",
            "weekly_hours": "40 giờ/tuần",
            "probation_salary_monthly": "12,75 triệu đồng/tháng",
            "employee_name": "Synthetic Candidate",
        }),
        _case("cv-001", "cv", "DOCX", "CV", {
            "full_name": "Synthetic Candidate",
            "years_experience": "2 năm 6 tháng",
        }),
        _case("cv-002", "cv", "PLAIN_TEXT", "CV", {}),
        _case("ielts-001", "ielts", "IMAGE", "CERTIFICATE", {
            "recipient_name": "CANDIDATE SYNTHETIC",
            "overall_score": "6,5",
            "issue_date": "2026-08-03",
        }),
    ]
    dataset = {
        "datasetId": "synthetic-external",
        "version": "v1",
        "contentDigest": "sha256:" + "a" * 64,
        "documentCount": len(cases),
        "groundTruthStatus": "SEALED",
    }
    inventory = {
        "schemaVersion": "1.0.0",
        "dataset": dataset.copy(),
        "cases": [
            {
                "caseId": case["caseId"],
                "category": case["category"],
                "sourceFormat": case["sourceFormat"],
                "documentType": case["documentType"],
                "pageCount": 1,
            }
            for case in cases
        ],
    }
    ground_truth = {
        "schemaVersion": "1.0.0",
        "dataset": dataset.copy(),
        "review": {
            "status": "CONFIRMED",
            "predictionBlindness": True,
        },
        "cases": cases,
    }
    return ground_truth, inventory


def _case(
    case_id: str,
    category: str,
    source_format: str,
    document_type: str,
    values: dict[str, object],
) -> dict[str, object]:
    out_of_scope = source_format in {"PLAIN_TEXT", "PPTX"} and category == "cv"
    return {
        "caseId": case_id,
        "category": category,
        "sourceFormat": source_format,
        "documentType": document_type,
        "fields": [
            {
                "name": name,
                "value": values.get(name),
                "reviewStatus": "PENDING" if out_of_scope else "CONFIRMED",
            }
            for name in FIELD_SPECS[category]
        ],
    }
