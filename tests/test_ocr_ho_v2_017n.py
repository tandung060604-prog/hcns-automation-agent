from scripts.analyze_ocr_ho_v2_017n import ranked_categories, summarize_field


def test_boundary_summary_keeps_global_threshold_separate_from_field_signal() -> None:
    data = {
        "evaluated": 15,
        "autoHit": 10,
        "boundaryMiss": 5,
        "detectorMiss": 0,
        "cropMiss": 0,
        "categoryCounts": {"bottom_boundary": 3, "line_order": 1, "top_boundary": 1},
    }
    result = summarize_field(data)
    assert result["dominantCategory"] == "bottom_boundary"
    assert result["dominantCategoryRate"] == 0.6
    assert result["meets50PercentThreshold"] is True


def test_ranked_categories_ignores_zero_categories_and_is_deterministic() -> None:
    result = ranked_categories({"line_order": 7, "bottom_boundary": 8, "top_boundary": 0})
    assert result == [
        {"category": "bottom_boundary", "count": 8},
        {"category": "line_order", "count": 7},
    ]
