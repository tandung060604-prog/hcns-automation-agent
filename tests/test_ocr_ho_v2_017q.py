from scripts.review_ocr_ho_v2_017q import derive_rule


def source() -> dict[str, object]:
    return {
        "evidence": {
            "bottomBoundaryCases": {
                "caseCount": 3,
                "maxBottomOverflowPixels": 15,
                "normalizedBboxCounts": {"0.28,0.70,0.98,0.90": 3},
                "maxValueLinesCounts": {"2": 3},
            }
        },
        "candidateRule": {"sealedLineIdOverlapRate": 0.0},
    }


def test_rule_is_bottom_only_and_does_not_remap_line_ids() -> None:
    rule = derive_rule(source())
    assert rule["name"] == "GEOMETRY_REGION_BOTTOM_EXTEND_TO_OBSERVED_LINE_BBOX"
    assert rule["maxBottomExtensionPixels"] == 15
    assert rule["preserveMaxValueLines"] == 2
    assert rule["lineIdRemapping"] is False
    assert rule["patchAuthorized"] is False
    assert rule["replayAuthorized"] is False
