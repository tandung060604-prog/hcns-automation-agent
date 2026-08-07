from scripts.review_ocr_ho_v2_017x import RULE, inspect_runtime, review


def source_017w() -> dict[str, object]:
    return {
        "candidateRule": RULE.copy(),
        "review": {
            "minimalSurfaceGate": "PASS",
            "patchAuthorized": False,
            "replayAuthorized": False,
        },
    }


RUNTIME = '''
def _geometry_line_bboxes():
    center_y <= bottom
    groups[: (1 if field_name == "fullName" else 2)]
    region["lineIds"] = geometry_ids
    geometry_bboxes, geometry_ids = _geometry_line_bboxes(...)
    region["regionSource"] = "phase11_10_geometry_line_segmentation"
    "phase11_10_detector_lines"
'''


def test_review_holds_when_geometry_guard_source_is_assigned_too_late() -> None:
    report = review(source_017w(), RUNTIME)
    assert report["implementationReview"]["guardPlacementGate"] == "HOLD"
    assert report["implementationReview"]["patchAuthorized"] is False
    assert report["decision"]["status"] == "IMPLEMENTATION_REVIEW_HOLD_GUARD_PLACEMENT"


def test_runtime_inspection_records_detector_and_geometry_paths() -> None:
    result = inspect_runtime(RUNTIME)
    assert result["markers"]["detectorPathPresent"] is True
    assert result["markers"]["geometryPathPresent"] is True
    assert result["geometryCallBeforeRegionSourceAssignment"] is True


def test_rule_drift_keeps_implementation_review_closed() -> None:
    source = source_017w()
    source["candidateRule"] = {**RULE, "maxBottomExtensionPixels": 16}
    report = review(source, RUNTIME)
    assert report["implementationReview"]["boundedRuleGate"] == "HOLD"
    assert report["implementationReview"]["patchAuthorized"] is False
