from scripts.analyze_ocr_ho_v2_017m import classify_cohort, render_bucket


def candidate(line_id: int, value: str, *, line_order: int = 0) -> dict[str, object]:
    return {"lineId": line_id, "lineIds": [line_id], "lineOrder": line_order, "value": value}


def test_cohort_separates_auto_region_miss_from_oracle_token_class() -> None:
    status, label, eligible = classify_cohort((1,), "A", (), [candidate(2, "A")])
    assert status == "AUTO_REGION_MISS"
    assert label == "LINE_ID_MISS"
    assert eligible is False

    status, label, eligible = classify_cohort((1,), "A B", (1,), [candidate(1, "A C")])
    assert status == "AUTO_REGION_HIT"
    assert label == "RECOGNIZER_DISAGREEMENT"
    assert eligible is True


def test_render_bucket_keeps_aggregate_only_class_counts() -> None:
    bucket = {"groups": 2, "eligibleLineTokenGroups": 1, "classCounts": {"LINE_ID_MISS": 1}}
    result = render_bucket(bucket)
    assert result["groups"] == 2
    assert result["classCounts"]["LINE_ID_MISS"] == 1
    assert result["dominantErrorClass"] == "LINE_ID_MISS"
    assert result["dominantErrorRate"] == 1.0
