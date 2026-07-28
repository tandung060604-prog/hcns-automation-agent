from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.phase13_2_recognition import (
    LineCandidate,
    select_candidates,
    select_recognizer,
)


class Phase132CorpusTests(unittest.TestCase):
    def test_selection_is_deterministic_and_prioritizes_vietnamese_lines(self) -> None:
        candidates = tuple(
            LineCandidate(
                source_path=Path(f"synthetic-{index // 4}.pdf"),
                source_relative_path=f"synthetic-{index // 4}.pdf",
                source_sha256="sha256:" + "a" * 64,
                page_index=0,
                bbox=(0.0, float(index), 100.0, float(index + 1)),
                text=f"Dòng tổng hợp {index}",
                has_extended_vietnamese=index < 9,
                selection_key=f"{20 - index:064d}",
            )
            for index in range(12)
        )

        first = select_candidates(candidates, max_cases=10)
        second = select_candidates(candidates, max_cases=10)

        self.assertEqual(first, second)
        self.assertEqual(9, sum(case.has_extended_vietnamese for case in first))


class Phase132SelectionTests(unittest.TestCase):
    def test_challenger_requires_exact_and_der_not_worse_than_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline = root / "baseline.json"
            challenger = root / "challenger.json"
            output = root / "selection.json"
            _write_report(
                baseline,
                model="paddle",
                exact=0.25,
                der=0.50,
                precision=0.30,
                latency=10,
            )
            _write_report(
                challenger,
                model="vietocr",
                exact=0.60,
                der=0.15,
                precision=0.70,
                latency=20,
            )

            with redirect_stdout(StringIO()):
                select_recognizer(
                    report_paths=(baseline, challenger),
                    baseline_model="paddle",
                    output_path=output,
                    overwrite=False,
                )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("SELECTED_FOR_PILOT", payload["status"])
            self.assertEqual("vietocr", payload["selectedModel"])

    def test_tradeoff_that_worsens_der_is_held(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline = root / "baseline.json"
            challenger = root / "challenger.json"
            output = root / "selection.json"
            _write_report(
                baseline,
                model="paddle",
                exact=0.25,
                der=0.20,
                precision=0.30,
                latency=10,
            )
            _write_report(
                challenger,
                model="challenger",
                exact=0.60,
                der=0.30,
                precision=0.70,
                latency=20,
            )

            with redirect_stdout(StringIO()):
                select_recognizer(
                    report_paths=(baseline, challenger),
                    baseline_model="paddle",
                    output_path=output,
                    overwrite=False,
                )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("HOLD", payload["status"])
            self.assertIsNone(payload["selectedModel"])


def _write_report(
    path: Path,
    *,
    model: str,
    exact: float,
    der: float,
    precision: float,
    latency: float,
) -> None:
    path.write_text(
        json.dumps(
            {
                "datasetId": "synthetic-lines",
                "datasetVersion": "1",
                "datasetContentDigest": "sha256:" + "b" * 64,
                "backendName": model,
                "backendVersion": "1",
                "modelIdentifier": model,
                "metrics": {
                    "exactMatchRate": exact,
                    "diacriticErrorRate": der,
                    "acceptedPrecision": precision,
                    "latencyP95Ms": latency,
                },
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
