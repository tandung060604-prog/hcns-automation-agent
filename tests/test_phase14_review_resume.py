from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.ocr_lab.api.phase14_review_store import (
    load_line_reviews,
    pending_case_ids,
    save_line_review,
)


class Phase14ReviewResumeTests(unittest.TestCase):
    def test_reload_resumes_at_first_unverified_case(self) -> None:
        cases = [
            {"caseId": f"{index:020x}"}
            for index in range(1, 310)
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "line_reviews.json"
            for case in cases[:172]:
                save_line_review(
                    path,
                    case_id=str(case["caseId"]),
                    ground_truth="synthetic confirmed line",
                    reviewed_at="2026-07-28T00:00:00+00:00",
                )

            reloaded = load_line_reviews(path)
            pending = pending_case_ids(cases, reloaded)

        self.assertEqual(172, len(reloaded["reviews"]))
        self.assertEqual(137, len(pending))
        self.assertEqual(cases[172]["caseId"], pending[0])

    def test_completed_queue_stays_empty_after_reload(self) -> None:
        cases = [{"caseId": f"{index:020x}"} for index in range(1, 4)]
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "line_reviews.json"
            for case in cases:
                save_line_review(
                    path,
                    case_id=str(case["caseId"]),
                    ground_truth="synthetic confirmed line",
                    reviewed_at="2026-07-28T00:00:00+00:00",
                )

            pending = pending_case_ids(cases, load_line_reviews(path))

        self.assertEqual([], pending)


if __name__ == "__main__":
    unittest.main()
