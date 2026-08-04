from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from synthetic_fixtures import (
    synthetic_contract_docx_bytes,
    synthetic_cv_pdf_bytes,
)

from apps.ocr_lab.api.phase12_ingestion import ingest_document
from apps.ocr_lab.api.phase15_idp import (
    classify_phase15_document,
    extract_phase15_document,
)


class Phase15NativeIntakeTests(unittest.TestCase):
    def test_native_pdf_and_docx_use_the_unified_pipeline(self) -> None:
        fixtures = (
            (
                "synthetic-cv.pdf",
                synthetic_cv_pdf_bytes(),
                "PDF",
                "NATIVE",
                "CV",
                "CV",
            ),
            (
                "synthetic-contract.docx",
                synthetic_contract_docx_bytes(),
                "DOCX",
                "NATIVE",
                "EMPLOYMENT_CONTRACT",
                "CONTRACT_DECISION",
            ),
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for (
                name,
                content,
                expected_format,
                expected_mode,
                expected_type,
                expected_family,
            ) in fixtures:
                with self.subTest(name=name):
                    path = root / name
                    path.write_bytes(content)
                    canonical = ingest_document(path)
                    classification = classify_phase15_document(canonical)
                    extraction = extract_phase15_document(
                        canonical,
                        classification,
                    )

                    self.assertEqual(expected_format, canonical["sourceFormat"])
                    self.assertEqual(expected_mode, canonical["ingestionMode"])
                    self.assertEqual(
                        expected_type,
                        classification["documentType"],
                    )
                    self.assertEqual(
                        expected_family,
                        classification["documentFamily"],
                    )
                    self.assertGreater(
                        extraction["summary"]["expectedFieldCount"],
                        0,
                    )
                    if expected_format == "XLSX":
                        self.assertGreater(len(extraction["tables"]), 0)


if __name__ == "__main__":
    unittest.main()
