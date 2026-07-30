import json
from pathlib import Path

import pytest

from apps.ocr_lab.api.heldout_dashboard import (
    load_heldout_dashboard,
    load_heldout_document_evidence,
    resolve_heldout_document,
    resolve_heldout_root,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def build_fixture(root: Path) -> None:
    write_json(
        root / "authorization.json",
        {
            "authorizedLocalDocumentsOnly": True,
            "processingRightsConfirmed": True,
        },
    )
    write_json(
        root / "manifest_private.json",
        {
            "datasetId": "real-heldout",
            "datasetDigest": "sha256:test",
            "containsRealPII": True,
            "predictionsVisibleDuringGroundTruthReview": False,
            "countsByFamily": {"CV": 1},
            "documents": [
                {
                    "documentId": "H16-C-001",
                    "documentFamily": "CV",
                    "sourcePath": "source/cv.jpg",
                    "sourceFormat": "JPG",
                    "sizeBytes": 3,
                }
            ],
        },
    )
    write_json(
        root / "reports" / "PHASE16_HELDOUT_RESULTS.json",
        {
            "documentCount": 1,
            "recognitionPolicyDigest": "sha256:policy",
            "parserVersion": "parser/1",
            "metricSpecVersion": "metrics/1",
            "overall": {"fieldExactMatchRate": 0.5},
            "byFamily": {"CV": {"documentCount": 1}},
            "decision": {"production": "NOT_PRODUCTION_READY"},
        },
    )
    source = root / "source" / "cv.jpg"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"jpg")
    write_json(
        root / "ground_truth" / "ground_truth_confirmed_private.json",
        {
            "documents": [
                {
                    "documentId": "H16-C-001",
                    "documentFamily": "CV",
                    "fields": {"fullName": "Synthetic Reviewer"},
                }
            ]
        },
    )
    write_json(
        root / "predictions" / "sealed_predictions_private.json",
        {
            "documents": [
                {
                    "documentId": "H16-C-001",
                    "documentFamily": "CV",
                    "documentType": "CV",
                    "fields": {
                        "fullName": {
                            "value": "Synthetic Review",
                            "status": "needs_review",
                        }
                    },
                    "summary": {"documentCompleteness": 0.5},
                }
            ]
        },
    )


def test_load_dashboard_exposes_aggregate_and_safe_document_metadata(
    tmp_path: Path,
) -> None:
    build_fixture(tmp_path)
    payload = load_heldout_dashboard(tmp_path)
    assert payload["documentCount"] == 1
    assert payload["containsRealPII"] is True
    assert payload["publicReleaseAuthorized"] is False
    assert payload["documents"] == [
        {
            "documentId": "H16-C-001",
            "documentFamily": "CV",
            "sourceFormat": "JPG",
            "sizeBytes": 3,
            "previewAvailable": True,
            "sourceAvailable": True,
        }
    ]


def test_resolve_document_rejects_path_traversal(tmp_path: Path) -> None:
    build_fixture(tmp_path)
    with pytest.raises(ValueError, match="Invalid"):
        resolve_heldout_document(tmp_path, "../authorization", preview=True)


def test_dashboard_requires_confirmed_local_processing_rights(
    tmp_path: Path,
) -> None:
    build_fixture(tmp_path)
    write_json(
        tmp_path / "authorization.json",
        {
            "authorizedLocalDocumentsOnly": True,
            "processingRightsConfirmed": False,
        },
    )
    with pytest.raises(PermissionError, match="not confirmed"):
        load_heldout_dashboard(tmp_path)


def test_default_root_is_private_sibling(tmp_path: Path) -> None:
    data_root = tmp_path / "baseline"
    data_root.mkdir()
    heldout_root = tmp_path / "paddleocr-hr-heldout-v1"
    heldout_root.mkdir()
    assert resolve_heldout_root(data_root, None) == heldout_root.resolve()


def test_load_document_evidence_returns_local_schema_and_both_sides(
    tmp_path: Path,
) -> None:
    build_fixture(tmp_path)
    payload = load_heldout_document_evidence(tmp_path, "H16-C-001")
    assert payload["schemaRef"] == "schemas/hr_document_families/cv.schema.json"
    assert payload["groundTruth"]["fields"]["fullName"] == "Synthetic Reviewer"
    assert payload["prediction"]["fields"]["fullName"]["status"] == "needs_review"
    assert payload["localOnly"] is True


def test_locked_replay_is_default_but_sealed_prediction_is_preserved(
    tmp_path: Path,
) -> None:
    build_fixture(tmp_path)
    write_json(
        tmp_path
        / "predictions"
        / "latest_replay_private"
        / "latest_replay_predictions_private.json",
        {
            "createdAt": "2026-07-29T12:00:00Z",
            "parserVersion": "parser/2",
            "recognitionPolicyDigest": "sha256:policy",
            "evaluationKind": "POST_GROUND_TRUTH_REPLAY_AUDIT",
            "promotionEligible": False,
            "documents": [
                {
                    "documentId": "H16-C-001",
                    "documentFamily": "CV",
                    "documentType": "CV",
                    "fields": {
                        "fullName": {
                            "value": "Synthetic Reviewer",
                            "status": "needs_review",
                        }
                    },
                }
            ],
        },
    )
    payload = load_heldout_document_evidence(tmp_path, "H16-C-001")
    assert payload["prediction"]["fields"]["fullName"]["value"] == (
        "Synthetic Reviewer"
    )
    assert payload["sealedPrediction"]["fields"]["fullName"]["value"] == (
        "Synthetic Review"
    )
    assert payload["predictionProvenance"]["defaultSource"] == "locked_replay"
    assert (
        payload["predictionProvenance"]["lockedReplay"]["promotionEligible"]
        is False
    )


def test_live_v5_replay_takes_priority_over_locked_replay(
    tmp_path: Path,
) -> None:
    build_fixture(tmp_path)
    write_json(
        tmp_path
        / "predictions"
        / "latest_live_v5_replay_private"
        / "latest_live_v5_predictions_private.json",
        {
            "createdAt": "2026-07-29T13:00:00Z",
            "parserVersion": "phase17-structured-hr-parser/2.0.0",
            "recognitionPolicyDigest": "sha256:policy",
            "evaluationKind": "POST_GROUND_TRUTH_LIVE_V5_REPLAY_AUDIT",
            "promotionEligible": False,
            "ocrPipeline": "PP-OCRv5 detector -> VietOCR",
            "documents": [
                {
                    "documentId": "H16-C-001",
                    "documentFamily": "CV",
                    "documentType": "CV",
                    "fields": {
                        "fullName": {
                            "value": "Synthetic V5 Result",
                            "status": "needs_review",
                        }
                    },
                }
            ],
        },
    )
    payload = load_heldout_document_evidence(tmp_path, "H16-C-001")
    assert payload["prediction"]["fields"]["fullName"]["value"] == (
        "Synthetic V5 Result"
    )
    assert payload["liveV5Prediction"]["fields"]["fullName"]["value"] == (
        "Synthetic V5 Result"
    )
    assert payload["predictionProvenance"]["defaultSource"] == "live_v5"
    assert payload["predictionProvenance"]["liveV5"]["promotionEligible"] is False
