from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from phase11_10_cccd_v2 import _geometry_line_bboxes  # noqa: E402


def page(*boxes: list[list[int]]) -> dict[str, object]:
    return {"recognizedBoxes": list(boxes)}


def test_residence_geometry_guard_extends_bottom_by_at_most_15px() -> None:
    region = {
        "bbox": [280, 700, 980, 900],
        "regionSource": "phase11_10_geometry_line_segmentation",
    }
    boxes, ids = _geometry_line_bboxes(
        page([[500, 880], [800, 880], [800, 900], [500, 900]]),
        region,
        "placeOfResidence",
        (1000, 1000),
    )
    assert ids == [0]
    assert boxes[0][3] == 902


def test_detector_selected_path_does_not_receive_geometry_extension() -> None:
    region = {
        "bbox": [280, 700, 980, 900],
        "regionSource": "phase11_10_detector_lines",
    }
    boxes, ids = _geometry_line_bboxes(
        page([[500, 880], [800, 880], [800, 900], [500, 900]]),
        region,
        "placeOfResidence",
        (1000, 1000),
    )
    assert boxes == []
    assert ids == []


def test_geometry_guard_keeps_two_line_cap_and_line_ids() -> None:
    region = {
        "bbox": [280, 700, 980, 900],
        "regionSource": "phase11_10_geometry_line_segmentation",
    }
    boxes, ids = _geometry_line_bboxes(
        page(
            [[500, 800], [800, 800], [800, 820], [500, 820]],
            [[500, 840], [800, 840], [800, 860], [500, 860]],
            [[500, 870], [800, 870], [800, 890], [500, 890]],
        ),
        region,
        "placeOfResidence",
        (1000, 1000),
    )
    assert ids == [0, 1]
    assert len(boxes) == 2
