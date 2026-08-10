from __future__ import annotations

import json

import pytest

from hcns_agent.adapters.camunda7.local_shadow_review import (
    LocalShadowReviewError,
    project_local_prediction_record,
    run_local_shadow_review,
)


def _payload() -> dict[str, object]:
    return {
        "datasetDigest": "sha256:synthetic-data22",
        "localOnly": True,
        "reviewProjection": {
            "groundTruthUsed": False,
            "evaluateOnceArtifactTouched": False,
        },
        "documents": [
            {
                "caseId": "cv-001",
                "category": "cv",
                "predictedCategory": "cv",
                "sourceFormat": "IMAGE",
                "sourceFile": "SYNTHETIC-PII.pdf",
                "fields": {"full_name": "SYNTHETIC PERSON"},
            },
            {
                "caseId": "contract-001",
                "category": "contract",
                "predictedCategory": "contract",
                "sourceFormat": "DOCX",
                "fields": {"employee_name": "SYNTHETIC PERSON"},
            },
            {
                "caseId": "ielts-001",
                "category": "ielts",
                "predictedCategory": "ielts",
                "sourceFormat": "PLAIN_TEXT",
                "fields": {"candidate_id": "SECRET-VALUE"},
            },
        ],
    }


def test_shadow_review_is_manual_only_and_idempotent() -> None:
    report = run_local_shadow_review(_payload())

    assert report.passed is True
    assert report.document_count == 3
    assert report.manual_review_count == 3
    assert report.scan_manual_review_count == 1
    assert report.unsupported_manual_review_count == 1
    assert report.category_counts == {
        "CERTIFICATE": 1,
        "CV": 1,
        "EMPLOYMENT_CONTRACT": 1,
    }
    assert report.idempotency_mismatch_count == 0
    assert report.duplicate_reference_count == 0
    assert report.auto_continue_count == 0
    assert report.camunda_process_start_attempts == 0
    assert report.real_side_effect_count == 0
    rendered = json.dumps(report.as_dict())
    assert "SYNTHETIC PERSON" not in rendered
    assert "SECRET-VALUE" not in rendered


def test_projection_contains_only_opaque_scalar_variables() -> None:
    projection = project_local_prediction_record(
        _payload()["documents"][0],  # type: ignore[index]
        dataset_digest="sha256:synthetic-data22",
    )

    assert all(
        value is None or isinstance(value, (str, int, float, bool))
        for value in projection.variables.values()
    )
    assert "fields" not in projection.variables
    assert "sourceFile" not in projection.variables
    assert projection.variables["autoContinueEnabled"] is False
    assert projection.variables["recommendedAction"] == "MANUAL_REVIEW"


def test_ground_truth_or_evaluate_once_metadata_fails_closed() -> None:
    payload = _payload()
    metadata = payload["reviewProjection"]
    assert isinstance(metadata, dict)
    metadata["groundTruthUsed"] = True
    with pytest.raises(LocalShadowReviewError, match="GroundTruth"):
        run_local_shadow_review(payload)


def test_duplicate_case_ids_fail_closed() -> None:
    payload = _payload()
    documents = payload["documents"]
    assert isinstance(documents, list)
    documents.append(dict(documents[0]))
    with pytest.raises(LocalShadowReviewError, match="duplicate"):
        run_local_shadow_review(payload)
