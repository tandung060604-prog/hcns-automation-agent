import json
from unittest import TestCase

from synthetic_fixtures import administrative_image_bytes

from hcns_agent.adapters.paddleocr import PaddleOcrEngine
from hcns_agent.ports.document_parser import DocumentSource


class _FakePredictor:
    def predict(self, image: object, **options: object) -> list[dict[str, object]]:
        if getattr(image, "shape", None) != (240, 640, 3):
            raise AssertionError("Unexpected normalized image")
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
        engine = PaddleOcrEngine(
            predictor=_FakePredictor(),
            image_converter=lambda image: _FakeImageInput(
                shape=(image.height, image.width, 3)
            ),
        )
        result = engine.recognize(
            DocumentSource(
                document_id="SYNTHETIC-001",
                filename="synthetic.png",
                content=administrative_image_bytes(),
            )
        )

        self.assertEqual("paddleocr/pp-ocrv5-vi", result.engine)
        self.assertEqual("HỒ SƠ SYNTHETIC", result.pages[0].lines[0].text)
        self.assertEqual(0.97, result.pages[0].lines[0].confidence)
        self.assertEqual((100.0, 20.0), result.pages[0].lines[0].box[2])
        self.assertEqual([], json.loads(result.model_manifest["roiRecovery"]))


class _FakeImageInput:
    def __init__(self, *, shape: tuple[int, int, int]) -> None:
        self.shape = shape
