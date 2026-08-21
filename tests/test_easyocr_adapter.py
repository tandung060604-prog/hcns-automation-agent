from __future__ import annotations

from io import BytesIO

from PIL import Image

from hcns_agent.adapters.easyocr import (
    EASYOCR_CANVAS_SIZE,
    EASYOCR_DECODER,
    EASYOCR_LANGUAGE_PROFILE,
    EASYOCR_LAYOUT_RECOVERY_PROFILE,
    EASYOCR_MAG_RATIO,
    EASYOCR_TEXT_REPAIR_PROFILE,
    EasyOcrEngine,
    _group_readtext_results,
)
from hcns_agent.ports.document_parser import DocumentSource


class _Reader:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}
        self.image: object | None = None

    def readtext(self, image: object, **kwargs: object) -> list[object]:
        self.image = image
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


def test_easyocr_repairs_contextual_b2b_confusion() -> None:
    lines = _group_readtext_results(
        [
            ([[0, 0], [180, 0], [180, 20], [0, 20]], "Kinh doanh BZB", 0.9),
        ]
    )

    assert lines[0].text == "Kinh doanh B2B"


def test_easyocr_uses_bounded_scan_settings() -> None:
    image = Image.new("RGB", (32, 32), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    reader = _Reader()

    result = EasyOcrEngine(reader).recognize(
        DocumentSource(
            document_id="SYNTHETIC-EASYOCR",
            filename="page.png",
            content=output.getvalue(),
        )
    )

    assert reader.kwargs["canvas_size"] == EASYOCR_CANVAS_SIZE
    assert reader.kwargs["mag_ratio"] == EASYOCR_MAG_RATIO
    assert reader.kwargs["decoder"] == EASYOCR_DECODER
    assert result.model_manifest["languageProfile"] == EASYOCR_LANGUAGE_PROFILE
    assert result.model_manifest["textRepairProfile"] == EASYOCR_TEXT_REPAIR_PROFILE
    assert result.model_manifest["layoutRecoveryProfile"] == EASYOCR_LAYOUT_RECOVERY_PROFILE


def test_easyocr_rechecks_bounded_ielts_layout_regions() -> None:
    image = Image.new("RGB", (320, 240), "white")
    output = BytesIO()
    image.save(output, format="PNG")

    class _LayoutReader:
        def __init__(self) -> None:
            self.calls = 0

        def readtext(self, image: object, **kwargs: object) -> list[object]:
            self.calls += 1
            if self.calls == 1:
                return [
                    ([[10, 10], [90, 10], [90, 26], [10, 26]], "Family Name", 0.9),
                    ([[10, 80], [100, 80], [100, 96], [10, 96]], "Test Results", 0.9),
                ]
            return [([[200, 20], [280, 20], [280, 52], [200, 52]], "LE", 0.9)]

    reader = _LayoutReader()
    result = EasyOcrEngine(reader).recognize(
        DocumentSource(
            document_id="SYNTHETIC-IELTS-CROP",
            filename="page.png",
            content=output.getvalue(),
        )
    )

    assert reader.calls == 3
    assert any(line.text == "Family Name LE" for line in result.pages[0].lines)


def test_easyocr_accepts_vietnamese_english_candidate_profile() -> None:
    image = Image.new("RGB", (32, 32), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    reader = _Reader()

    result = EasyOcrEngine(
        reader,
        language_profile="vi-en",
    ).recognize(
        DocumentSource(
            document_id="BENCHMARK-EASYOCR-VI-EN",
            filename="page.png",
            content=output.getvalue(),
        )
    )

    assert result.engine == "easyocr/vi-en-greedy"
    assert result.model_manifest["languageProfile"] == "vi-en"


def test_easyocr_accepts_benchmark_scan_profile() -> None:
    image = Image.new("RGB", (32, 32), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    reader = _Reader()

    EasyOcrEngine(reader, canvas_size=2560, mag_ratio=1.3).recognize(
        DocumentSource(
            document_id="BENCHMARK-EASYOCR",
            filename="page.png",
            content=output.getvalue(),
        )
    )

    assert reader.kwargs["canvas_size"] == 2560
    assert reader.kwargs["mag_ratio"] == 1.3


def test_easyocr_accepts_beamsearch_candidate_without_changing_default() -> None:
    image = Image.new("RGB", (32, 32), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    reader = _Reader()

    result = EasyOcrEngine(reader, decoder="beamsearch").recognize(
        DocumentSource(
            document_id="BENCHMARK-EASYOCR-BEAMSEARCH",
            filename="page.png",
            content=output.getvalue(),
        )
    )

    assert reader.kwargs["decoder"] == "beamsearch"
    assert result.engine == "easyocr/vi-beamsearch"
    assert result.model_manifest["decoder"] == "beamsearch"


def test_easyocr_content_roi_profile_crops_and_reports_profile() -> None:
    image = Image.new("RGB", (100, 100), "white")
    for x in range(30, 60):
        for y in range(40, 70):
            image.putpixel((x, y), (0, 0, 0))
    output = BytesIO()
    image.save(output, format="PNG")
    reader = _Reader()

    result = EasyOcrEngine(
        reader,
        preprocess_profile="content-roi-autocontrast-v1",
    ).recognize(
        DocumentSource(
            document_id="BENCHMARK-EASYOCR-ROI",
            filename="page.png",
            content=output.getvalue(),
        )
    )

    assert reader.image is not None
    assert getattr(reader.image, "shape", (0, 0))[:2] == (46, 46)
    assert result.model_manifest["preprocessProfile"] == "content-roi-autocontrast-v1"
