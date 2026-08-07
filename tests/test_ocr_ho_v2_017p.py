from scripts.analyze_ocr_ho_v2_017p import bottom_overflow, summarize_cases


def test_geometry_summary_is_aggregate_only() -> None:
    cases = [
        {
            "expectedLineCount": 2,
            "regionLineCount": 1,
            "sealedLineIdOverlapCount": 0,
            "regionSource": "phase11_10_geometry_line_segmentation",
            "normalizedBbox": "0.2800,0.7000,0.9800,0.9000",
            "maxValueLines": 2,
            "bottomOverflow": 1,
            "maxBottomOverflowPixels": 15,
            "cropLineVariantEntryCount": 4,
        },
        {
            "expectedLineCount": 2,
            "regionLineCount": 2,
            "sealedLineIdOverlapCount": 0,
            "regionSource": "phase11_10_geometry_line_segmentation",
            "normalizedBbox": "0.2800,0.7000,0.9800,0.9000",
            "maxValueLines": 2,
            "bottomOverflow": 0,
            "maxBottomOverflowPixels": 0,
            "cropLineVariantEntryCount": 8,
        },
    ]
    result = summarize_cases(cases)
    assert result["caseCount"] == 2
    assert result["expectedLineCount"] == 4
    assert result["regionLineCount"] == 3
    assert result["sealedLineIdOverlapRate"] == 0.0
    assert result["bottomOverflowCaseRate"] == 0.5
    assert result["cropLineVariantEntryCount"] == 12


def test_bottom_overflow_is_clamped_and_detected() -> None:
    assert bottom_overflow([[0, 1, 10, 12]], [0, 0, 10, 10]) == (1, 2)
    assert bottom_overflow([[0, 1, 10, 9]], [0, 0, 10, 10]) == (0, 0)
