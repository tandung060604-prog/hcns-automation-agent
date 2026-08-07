from __future__ import annotations

import hashlib
import json

import pytest

from scripts.audit_external_dataset_matching_policy import PolicyAuditError, audit_policy


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path):
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def test_policy_audit_is_create_only_and_non_promotional(tmp_path) -> None:
    prediction = tmp_path / "prediction.json"
    ground_truth = tmp_path / "ground_truth.json"
    source_report = tmp_path / "evaluate_once.json"
    source_marker = tmp_path / "EVALUATE_ONCE_LOCK.json"
    output = tmp_path / "policy_v2_audit.json"
    marker = tmp_path / "POLICY_V2_AUDIT_LOCK.json"
    _write(
        prediction,
        {
            "datasetId": "synthetic-policy-audit",
            "documents": [{
                "caseId": "cv-synthetic",
                "category": "cv",
                "predictedCategory": "cv",
                "processing": {"usesOcr": False, "recommendedAction": "USER_REVIEW"},
                "fields": {"full_name": {"value": "SYNTHETIC USER"}},
            }],
        },
    )
    _write(
        ground_truth,
        {"dataset": {"datasetId": "synthetic-policy-audit"}, "cases": [{
            "caseId": "cv-synthetic",
            "fields": [{"name": "full_name", "value": "Synthetic User"}],
        }]},
    )
    _write(source_report, {"evaluationKind": "heldout-evaluate-once", "decision": "HOLD"})
    _write(
        source_marker,
        {
            "evaluationKind": "heldout-evaluate-once",
            "evaluateOnceArtifactTouched": True,
            "promotionAllowed": False,
            "predictionSha256": _sha(prediction),
            "groundTruthSha256": _sha(ground_truth),
            "reportSha256": _sha(source_report),
        },
    )

    report, audit_marker = audit_policy(
        prediction,
        ground_truth,
        source_report,
        source_marker,
        output,
        marker,
    )

    assert report["evaluationKind"] == "posthoc-policy-audit"
    assert report["matchingPolicy"]["version"] == "2.0.0"
    assert report["promotionAllowed"] is False
    assert report["heldoutConsumed"] is True
    assert report["evaluateOnceArtifactTouched"] is False
    assert audit_marker["reportSha256"] == _sha(output)
    with pytest.raises(PolicyAuditError, match="already exists"):
        audit_policy(prediction, ground_truth, source_report, source_marker, output, marker)
