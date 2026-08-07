from scripts.review_ocr_ho_v2_017y import RULE, resolve_guard, review


def source_017x() -> dict[str, object]:
    return {
        "candidateRule": RULE.copy(),
        "implementationReview": {
            "guardPlacementGate": "HOLD",
            "patchAuthorized": False,
            "replayAuthorized": False,
        },
    }


RUNTIME = '''
selected = choices[:max_lines]
geometry_bboxes, geometry_ids = _geometry_line_bboxes(...)
region["regionSource"] = "phase11_10_geometry_line_segmentation"
'''


def test_guard_insertion_is_between_selection_and_geometry_fallback() -> None:
    result = resolve_guard(RUNTIME)
    assert result["placementResolved"] is True
    assert result["guardCondition"] == "field_name == placeOfResidence and not selected"
    assert result["detectorSelectedLinesUntouched"] is True


def test_review_resolves_guard_without_authorizing_patch_or_replay() -> None:
    report = review(source_017x(), RUNTIME)
    assert report["resolution"]["guardPlacementGate"] == "PASS"
    assert report["resolution"]["implementationApplied"] is False
    assert report["resolution"]["patchAuthorized"] is False
    assert report["resolution"]["replayAuthorized"] is False


def test_rule_drift_keeps_guard_resolution_closed() -> None:
    source = source_017x()
    source["candidateRule"] = {**RULE, "maxBottomExtensionPixels": 16}
    report = review(source, RUNTIME)
    assert report["resolution"]["ruleScopeGate"] == "HOLD"
    assert report["resolution"]["patchAuthorized"] is False
