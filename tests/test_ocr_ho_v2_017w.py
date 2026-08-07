from scripts.review_ocr_ho_v2_017w import RULE, review


def source_017t() -> dict[str, object]:
    return {
        "candidateRule": RULE.copy(),
        "gateReview": {"reconciliationGate": "PASS"},
    }


def source_017v(*, authorized: bool = True) -> dict[str, object]:
    return {
        "authorizationIntake": {
            "status": "VALID_FOR_PATCH_REVIEW" if authorized else "MISSING",
            "patchReviewAuthorized": authorized,
            "patchAuthorized": False,
            "replayAuthorized": False,
        },
        "gates": {"productionPromotionAllowed": False},
    }


def test_review_accepts_only_bounded_authorized_surface() -> None:
    report = review(source_017t(), source_017v())
    assert report["review"]["minimalSurfaceGate"] == "PASS"
    assert report["review"]["patchAuthorized"] is False
    assert report["review"]["replayAuthorized"] is False
    assert report["gates"]["manualReviewOnly"] is True


def test_review_holds_without_patch_review_authorization() -> None:
    report = review(source_017t(), source_017v(authorized=False))
    assert report["review"]["authorizationGate"] == "HOLD"
    assert report["decision"]["status"] == "PATCH_SURFACE_REVIEW_HOLD"


def test_review_rejects_rule_scope_drift() -> None:
    source = source_017t()
    source["candidateRule"] = {**RULE, "maxBottomExtensionPixels": 16}
    report = review(source, source_017v())
    assert report["review"]["reconciliationGate"] == "HOLD"
    assert report["review"]["patchAuthorized"] is False
