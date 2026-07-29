from __future__ import annotations

import unittest

from apps.ocr_lab.api.phase15_review import apply_phase15_field_review


class Phase15FieldReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.extraction = {
            "fields": {
                "employeeName": {
                    "value": "NGUYN VAN A",
                    "normalizedValue": "NGUYN VAN A",
                    "confidence": 0.78,
                    "status": "needs_review",
                    "validation": {"valid": True, "method": "label_value"},
                    "evidence": {"sourceKind": "ocr", "pageIndex": 0},
                },
                "employeeId": {
                    "value": None,
                    "normalizedValue": None,
                    "confidence": None,
                    "status": "not_found",
                    "validation": {"valid": False, "method": "label_value"},
                    "evidence": None,
                },
            },
            "tables": [],
            "summary": {},
        }

    def test_review_creates_human_evidence_and_recomputes_summary(self) -> None:
        reviewed, corrected = apply_phase15_field_review(
            self.extraction,
            {
                "employeeName": "NGUYỄN VĂN A",
                "employeeId": "EMP-001",
            },
            reviewed_at="2026-07-28T00:00:00+00:00",
        )

        self.assertEqual(2, corrected)
        self.assertEqual("accepted", reviewed["fields"]["employeeName"]["status"])
        self.assertEqual(
            "human_review",
            reviewed["fields"]["employeeName"]["evidence"]["sourceKind"],
        )
        self.assertEqual(1.0, reviewed["summary"]["documentCompleteness"])
        self.assertTrue(reviewed["summary"]["readyForAutomaticUse"])
        self.assertEqual("NGUYN VAN A", self.extraction["fields"]["employeeName"]["value"])

    def test_review_requires_the_complete_field_set(self) -> None:
        with self.assertRaisesRegex(ValueError, "every Phase 15 field"):
            apply_phase15_field_review(
                self.extraction,
                {"employeeName": "NGUYỄN VĂN A"},
                reviewed_at="2026-07-28T00:00:00+00:00",
            )

    def test_blank_confirmed_value_remains_not_found(self) -> None:
        reviewed, _ = apply_phase15_field_review(
            self.extraction,
            {"employeeName": "NGUYỄN VĂN A", "employeeId": ""},
            reviewed_at="2026-07-28T00:00:00+00:00",
        )

        self.assertEqual("not_found", reviewed["fields"]["employeeId"]["status"])
        self.assertFalse(reviewed["summary"]["readyForAutomaticUse"])


if __name__ == "__main__":
    unittest.main()
