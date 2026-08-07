from scripts.analyze_ocr_ho_v2_017o import summarize_residence


def test_residence_bottom_boundary_summary_is_aggregate_only() -> None:
    entries = [
        {
            "category": "bottom_boundary",
            "missingExpectedLineCount": 2,
            "selectedLineCount": 1,
            "regionSource": "phase11_10_geometry_line_segmentation",
        },
        {
            "category": "bottom_boundary",
            "missingExpectedLineCount": 2,
            "selectedLineCount": 1,
            "regionSource": "phase11_10_geometry_line_segmentation",
        },
        {
            "category": "bottom_boundary",
            "missingExpectedLineCount": 2,
            "selectedLineCount": 2,
            "regionSource": "phase11_10_geometry_line_segmentation",
        },
        {
            "category": "line_order",
            "missingExpectedLineCount": 2,
            "selectedLineCount": 2,
            "regionSource": "phase11_10_detector_lines",
        },
    ]
    result = summarize_residence(entries)
    assert result["bottomBoundary"]["caseCount"] == 3
    assert result["bottomBoundary"]["caseRate"] == 0.75
    assert result["bottomBoundary"]["missingExpectedLineCount"] == 6
    assert result["bottomBoundary"]["selectedLineCount"] == 4
    assert result["bottomBoundary"]["lineRetentionRate"] == 0.4
    assert result["bottomBoundary"]["regionSourceCounts"] == {
        "phase11_10_geometry_line_segmentation": 3
    }
