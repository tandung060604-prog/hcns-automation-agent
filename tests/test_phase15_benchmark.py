from __future__ import annotations

import unittest

from scripts.phase15_benchmark import (
    expected_field,
    flatten_value,
    metric_payload,
    table_counts,
)


class Phase15BenchmarkTests(unittest.TestCase):
    def test_nested_ground_truth_mapping_preserves_document_order(self) -> None:
        fields = {
            "contact": {
                "Email": "synthetic@example.test",
            },
            "skills": ["Kiểm thử", "Đối soát"],
        }

        present, email = expected_field(fields, ("contact.Email",))

        self.assertTrue(present)
        self.assertEqual("synthetic@example.test", email)
        self.assertEqual("Kiểm thử\nĐối soát", flatten_value(fields["skills"]))

    def test_table_accuracy_penalizes_missing_cells_and_rows(self) -> None:
        counts = table_counts(
            [["SYN-001", "Đạt"], ["SYN-002", "Đạt"]],
            [
                {
                    "rows": [
                        {"values": ["SYN-001", "Đạt"]},
                        {"values": ["SYN-002"]},
                    ]
                }
            ],
        )

        self.assertEqual(4, counts["expectedCellCount"])
        self.assertEqual(3, counts["exactCellCount"])
        self.assertEqual(1, counts["exactRowCount"])

    def test_family_metric_uses_canonical_text_metric(self) -> None:
        metrics = metric_payload(
            document_count=2,
            subtype_correct=1,
            family_correct=2,
            field_pairs=[
                ("NGUYỄN SYNTHETIC", "NGUYEN SYNTHETIC"),
                ("Đạt", "Đạt"),
            ],
            completeness=[0.5, 1.0],
            table_metrics=[
                {
                    "documentCount": 0,
                    "expectedRowCount": 0,
                    "exactRowCount": 0,
                    "expectedCellCount": 0,
                    "exactCellCount": 0,
                }
            ],
        )

        self.assertEqual(0.5, metrics["subtypeClassificationAccuracy"])
        self.assertEqual(1.0, metrics["familyClassificationAccuracy"])
        self.assertEqual(0.5, metrics["fieldExactMatchRate"])
        self.assertEqual(0.75, metrics["meanDocumentCompleteness"])
        self.assertGreater(metrics["fieldTextDer"], 0.0)


if __name__ == "__main__":
    unittest.main()
