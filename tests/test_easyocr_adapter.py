from __future__ import annotations

from io import BytesIO

from PIL import Image

from hcns_agent.adapters.easyocr import (
    EASYOCR_CANVAS_SIZE,
    EASYOCR_MAG_RATIO,
    EasyOcrEngine,
    _group_readtext_results,
)
from hcns_agent.ports.document_parser import DocumentSource


class _Reader:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def readtext(self, _image: object, **kwargs: object) -> list[object]:
        self.kwargs = kwargs
        return []


def test_easyocr_groups_same_row_and_drops_contained_duplicate() -> None:
    lines = _group_readtext_results(
        [
            ([[0, 0], [80, 0], [80, 20], [0, 20]], "Bộ phận: Phòng", 0.9),
            ([[85, 0], [170, 0], [170, 20], [85, 20]], "Công nghệ", 0.9),
            ([[130, 0], [170, 0], [170, 20], [130, 20]], "nghệ", 0.7),
            ([[0, 40], [60, 40], [60, 60], [0, 60]], "Lý do", 0.9),
        ]
    )

    assert len(lines) == 2
    assert lines[0].text == "Bộ phận: Phòng Công nghệ"
    assert lines[1].text == "Lý do"


def test_easyocr_uses_bounded_scan_settings() -> None:
    image = Image.new("RGB", (32, 32), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    reader = _Reader()

    EasyOcrEngine(reader).recognize(
        DocumentSource(
            document_id="SYNTHETIC-EASYOCR",
            filename="page.png",
            content=output.getvalue(),
        )
    )

    assert reader.kwargs["canvas_size"] == EASYOCR_CANVAS_SIZE
    assert reader.kwargs["mag_ratio"] == EASYOCR_MAG_RATIO
