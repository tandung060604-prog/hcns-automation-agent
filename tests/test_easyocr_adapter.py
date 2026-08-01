from __future__ import annotations

from hcns_agent.adapters.easyocr import _group_readtext_results


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
