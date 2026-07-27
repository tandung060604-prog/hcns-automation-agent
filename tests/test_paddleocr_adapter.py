from pathlib import Path
from unittest import TestCase

from hcns_agent.adapters.paddleocr import PaddleOcrEngine
from hcns_agent.domain.models import HrDocument


class _FakePredictor:
    def predict(self, path: str, **options: object) -> list[dict[str, object]]:
        if not path.endswith("synthetic.png"):
            raise AssertionError("Unexpected input path")
        if options.get("use_doc_unwarping") is not False:
            raise AssertionError("Unsafe default options")
        return [
            {
                "rec_texts": ["HỒ SƠ SYNTHETIC"],
                "rec_scores": [0.97],
                "rec_polys": [[[0, 0], [100, 0], [100, 20], [0, 20]]],
            }
        ]


class PaddleOcrAdapterTests(TestCase):
    def test_normalizes_vendor_result_without_loading_models(self) -> None:
        engine = PaddleOcrEngine(predictor=_FakePredictor())
        result = engine.recognize(
            HrDocument(document_id="SYNTHETIC-001", path=Path("synthetic.png"))
        )

        self.assertEqual("paddleocr/pp-ocrv5-vi", result.engine)
        self.assertEqual("HỒ SƠ SYNTHETIC", result.pages[0].lines[0].text)
        self.assertEqual(0.97, result.pages[0].lines[0].confidence)
        self.assertEqual((100.0, 20.0), result.pages[0].lines[0].box[2])

