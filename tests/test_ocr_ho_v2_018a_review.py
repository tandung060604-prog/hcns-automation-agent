from __future__ import annotations

from scripts.review_ocr_ho_v2_018a import inspect_patch, review

AUTH = {
    "authorizationIntake": {
        "status": "VALID_FOR_DEVELOPMENT_PATCH",
        "runtimePatchAuthorized": True,
        "primaryRuntimeChangeAuthorized": False,
        "replayAuthorized": False,
    },
    "gates": {"productionPromotionAllowed": False},
}


RUNTIME = '''
geometry_bottom_extension = (
field_name == "placeOfResidence"
region.get("regionSource") == "phase11_10_geometry_line_segmentation"
dict(region, regionSource="phase11_10_geometry_line_segmentation")
field_name == "placeOfResidence" and not selected
"phase11_10_detector_lines"
groups[: (1 if field_name == "fullName" else 2)]
region["lineIds"] = geometry_ids
'''


def test_patch_inspection_requires_all_scope_markers() -> None:
    result = inspect_patch(RUNTIME)
    assert result["allRequiredMarkers"] is True


def test_review_records_shadow_patch_without_replay() -> None:
    report = review(AUTH, RUNTIME)
    assert report["review"]["shadowPatchApplied"] is True
    assert report["review"]["primaryRuntimeChanged"] is False
    assert report["review"]["replayAuthorized"] is False
    assert report["gates"]["manualReviewOnly"] is True


def test_missing_marker_keeps_patch_review_on_hold() -> None:
    report = review(AUTH, RUNTIME.replace('"phase11_10_detector_lines"', ""))
    assert report["review"]["shadowPatchApplied"] is False
    assert report["decision"]["status"] == "SHADOW_PATCH_REVIEW_HOLD"
