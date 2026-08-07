from scripts.analyze_ocr_ho_v2_017s import (
    aggregate_mapping,
    box_to_xyxy,
    field_mapping,
    independent_lines,
)


def test_box_conversion_accepts_xyxy_and_polygon() -> None:
    assert box_to_xyxy([4, 8, 20, 30]) == (4.0, 8.0, 20.0, 30.0)
    assert box_to_xyxy([[20, 30], [4, 30], [4, 8], [20, 8]]) == (4.0, 8.0, 20.0, 30.0)


def test_independent_line_index_is_separate_from_text() -> None:
    source = {
        "pages": [
            {
                "lines": [
                    {"lineIndex": 4, "box": [0, 0, 10, 10], "primary": {"text": "secret"}},
                    {"lineIndex": 4, "box": [0, 0, 10, 10]},
                    {"lineIndex": 9, "box": [[0, 20], [10, 20], [10, 30], [0, 30]]},
                ]
            }
        ]
    }
    lines, duplicates = independent_lines(source)
    assert sorted(lines) == [4, 9]
    assert duplicates == 1


def test_field_mapping_reports_line_overlap_and_region_attribution() -> None:
    result = field_mapping(
        [4, 9],
        {"lineBboxes": [[0, 0, 10, 10], [0, 20, 10, 30]]},
        {4: (0.0, 0.0, 10.0, 10.0), 9: (0.0, 20.0, 10.0, 30.0)},
    )
    assert result["independentLineIdOverlapCount"] == 2
    assert result["independentLineIdOverlapRate"] == 1.0
    assert result["expectedRegionMappedLineCount"] == 2


def test_aggregate_mapping_is_count_only() -> None:
    result = aggregate_mapping(
        [
            {
                "expectedLineCount": 2,
                "independentLineIdOverlapCount": 2,
                "expectedRegionMappedLineCount": 1,
            },
            {
                "expectedLineCount": 1,
                "independentLineIdOverlapCount": 0,
                "expectedRegionMappedLineCount": 0,
            },
        ]
    )
    assert result["fieldCount"] == 2
    assert result["expectedLineCount"] == 3
    assert result["independentLineIdOverlapRate"] == round(2 / 3, 6)
