from __future__ import annotations

from scripts.run_m5_cam_005_contract_regression import run_regression


def test_m5_cam_005_contract_regression_passes_two_synthetic_fixtures() -> None:
    report = run_regression()

    assert report["passed"] is True
    assert report["fixtureCount"] == 2
    assert report["fixtureTypes"] == ["LEAVE_REQUEST", "OVERTIME_REQUEST"]
    assert report["scalarOnly"] is True
    assert report["opaqueReferenceOnly"] is True
    assert report["manualReviewCount"] == 2
    assert report["autoContinueCount"] == 0
    assert report["schemaWhitelistErrorCount"] == 0
    assert report["nonScalarValueCount"] == 0
    assert report["forbiddenPayloadRejectedCount"] == report["forbiddenPayloadCaseCount"]
    assert report["idempotencyMismatchCount"] == 0
    assert report["camundaProcessStartAttempts"] == 0
    assert report["hrisSideEffectCount"] == 0
    assert report["notificationSideEffectCount"] == 0
    assert report["containsRawFieldValues"] is False
    assert report["promotionAllowed"] is False
