from __future__ import annotations

import http.client
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from cccd_heldout_review import (  # noqa: E402
    FIELD_ORDER,
    evaluate_once,
    load_evaluation_document,
    load_review_document,
    load_review_summary,
    lock_ground_truth,
    save_review,
    set_review_disposition,
)

from apps.ocr_lab.api.serve_dashboard_api import (  # noqa: E402
    DashboardHandler,
    UserOCRService,
)


def build_root(tmp_path: Path) -> Path:
    root = tmp_path / "cccd-heldout"
    (root / "source").mkdir(parents=True)
    (root / "ground_truth").mkdir()
    (root / "predictions").mkdir()
    (root / "source" / "CCCD-HO-001.jpg").write_bytes(b"synthetic image")
    (root / "authorization.json").write_text(
        json.dumps(
            {
                "authorizedLocalDocumentsOnly": True,
                "processingRightsConfirmed": True,
            }
        ),
        encoding="utf-8",
    )
    (root / "manifest_private.json").write_text(
        json.dumps(
            {
                "documentCount": 1,
                "datasetId": "synthetic-heldout",
                "datasetDigest": "sha256:test",
                "records": [
                    {
                        "documentId": "CCCD-HO-001",
                        "documentIndex": 1,
                        "sourcePath": "source/CCCD-HO-001.jpg",
                        "sourceFormat": "IMAGE",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "ground_truth" / "review_queue_private.json").write_text(
        json.dumps(
            {
                "groundTruthStatus": "PENDING_HUMAN_CONFIRMATION",
                "datasetId": "synthetic-heldout",
                "datasetDigest": "sha256:test",
                "documentCount": 1,
                "documents": [
                    {
                        "documentId": "CCCD-HO-001",
                        "fields": {
                            name: {"value": "", "notPresent": False}
                            for name in FIELD_ORDER
                        },
                        "status": "PENDING",
                        "verificationAssertions": {
                            "comparedWithImage": False,
                            "allTextChecked": False,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return root


def complete_payload() -> dict[str, object]:
    return {
        "fields": {
            name: (
                {"value": "", "notPresent": True}
                if name == "dateOfExpiry"
                else {"value": f"synthetic-{name}", "notPresent": False}
            )
            for name in FIELD_ORDER
        },
        "assertions": {"comparedWithImage": True, "allTextChecked": True},
    }


def test_review_is_fail_closed_until_all_fields_are_confirmed(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    summary = load_review_summary(root)
    assert summary["groundTruthStatus"] == "PENDING_HUMAN_CONFIRMATION"
    assert summary["canLock"] is False
    assert summary["predictionsHiddenDuringReview"] is True

    saved = save_review(root, "CCCD-HO-001", complete_payload())
    assert saved["reviewStatus"] == "REVIEWED"
    summary = load_review_summary(root)
    assert summary["canLock"] is True
    detail = load_review_document(root, "CCCD-HO-001")
    assert detail["predictionsHidden"] is True
    assert "prediction" not in detail
    with pytest.raises(ValueError, match="Post-evaluation output"):
        load_evaluation_document(root, "CCCD-HO-001")

    locked = lock_ground_truth(root, confirm=True)
    assert locked == {
        "locked": True,
        "groundTruthStatus": "CONFIRMED",
        "documentCount": 1,
        "sourceDocumentCount": 1,
        "excludedDocumentCount": 0,
        "predictionsOpened": False,
    }
    summary = load_review_summary(root)
    assert summary["groundTruthStatus"] == "CONFIRMED"
    assert summary["canEvaluate"] is True
    with pytest.raises(ValueError, match="already locked"):
        save_review(root, "CCCD-HO-001", complete_payload())
    with pytest.raises(ValueError, match="already locked"):
        lock_ground_truth(root, confirm=True)


def test_save_requires_image_assertions_and_nonempty_or_absent_fields(
    tmp_path: Path,
) -> None:
    root = build_root(tmp_path)
    payload = complete_payload()
    payload["assertions"] = {"comparedWithImage": True, "allTextChecked": False}
    with pytest.raises(ValueError, match="Full text"):
        save_review(root, "CCCD-HO-001", payload)

    payload = complete_payload()
    payload["fields"] = {
        name: {"value": "", "notPresent": False} for name in FIELD_ORDER
    }
    with pytest.raises(ValueError, match="Enter a value"):
        save_review(root, "CCCD-HO-001", payload)


def test_out_of_scope_back_is_excluded_without_faking_missing_fields(
    tmp_path: Path,
) -> None:
    root = build_root(tmp_path)
    disposition = set_review_disposition(
        root,
        "CCCD-HO-001",
        "OUT_OF_SCOPE_BACK",
        "back_side_outside_front_schema",
    )
    assert disposition["metricIncluded"] is False
    summary = load_review_summary(root)
    assert summary["documentCount"] == 0
    assert summary["sourceDocumentCount"] == 1
    assert summary["excludedDocumentCount"] == 1
    assert summary["canLock"] is False
    detail = load_review_document(root, "CCCD-HO-001")
    assert detail["disposition"] == "OUT_OF_SCOPE_BACK"
    assert detail["reviewStatus"] == "EXCLUDED"
    assert all(not field["notPresent"] for field in detail["fields"].values())
    with pytest.raises(ValueError, match="out of scope"):
        save_review(root, "CCCD-HO-001", complete_payload())
    with pytest.raises(ValueError, match="At least one"):
        lock_ground_truth(root, confirm=True)


def test_local_review_api_exposes_source_and_no_prediction(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    DashboardHandler.data_root = tmp_path
    DashboardHandler.cccd_heldout_root = root
    DashboardHandler.native_indexes = {}
    DashboardHandler.user_ocr = UserOCRService(tmp_path)
    DashboardHandler.template_processor = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_port, timeout=10
    )
    try:
        connection.request("GET", "/cccd-heldout/review/summary")
        response = connection.getresponse()
        summary = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert summary["predictionsHiddenDuringReview"] is True
        assert "prediction" not in summary

        connection.request(
            "GET",
            "/cccd-heldout/review/document?id=CCCD-HO-001&mode=detail",
        )
        response = connection.getresponse()
        detail = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert detail["predictionsHidden"] is True
        assert "prediction" not in detail

        disposition_body = json.dumps(
            {
                "disposition": "OUT_OF_SCOPE_BACK",
                "reason": "back_side_outside_front_schema",
            }
        ).encode("utf-8")
        connection.request(
            "POST",
            "/cccd-heldout/review/disposition?id=CCCD-HO-001",
            body=disposition_body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(disposition_body)),
            },
        )
        response = connection.getresponse()
        disposition_result = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert disposition_result["metricIncluded"] is False

        connection.request(
            "GET",
            "/cccd-heldout/review/document?id=CCCD-HO-001&mode=preview",
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.read() == b"synthetic image"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_evaluate_once_reads_only_locked_ground_truth_and_sealed_prediction(
    tmp_path: Path,
) -> None:
    root = build_root(tmp_path)
    save_review(root, "CCCD-HO-001", complete_payload())
    lock_ground_truth(root, confirm=True)
    prediction_fields = {
        name: {"value": f"synthetic-{name}", "status": "accepted"}
        for name in FIELD_ORDER
        if name != "dateOfExpiry"
    }
    (root / "predictions" / "sealed_predictions_private.json").write_text(
        json.dumps(
            {
                "predictionsHiddenDuringGroundTruthReview": True,
                "groundTruthPresent": False,
                "documents": [
                    {
                        "documentId": "CCCD-HO-001",
                        "phase11_5": {"fields": prediction_fields},
                        "phase11_6": {"fields": prediction_fields},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = evaluate_once(
        root,
        python_executable=sys.executable,
        script_path=ROOT / "scripts" / "evaluate_cccd_heldout_once.py",
    )
    assert result["evaluationKind"] == "BLINDED_EVALUATE_ONCE"
    assert result["documentCount"] == 1
    assert (root / "evaluation" / "evaluate_once_private.json").is_file()
    evaluated_detail = load_evaluation_document(root, "CCCD-HO-001")
    assert evaluated_detail["localOnly"] is True
    assert evaluated_detail["fields"]["identityNumber"]["comparison"]["phase11_6"][
        "status"
    ] == "EXACT"
    assert evaluated_detail["fields"]["dateOfExpiry"]["comparison"]["phase11_6"][
        "status"
    ] == "NOT_IN_SOURCE"
    assert evaluated_detail["fields"]["identityNumber"]["phase11_6"]["evidence"][
        "candidateCount"
    ] == 0
    with pytest.raises(FileExistsError, match="already run"):
        evaluate_once(
            root,
            python_executable=sys.executable,
            script_path=ROOT / "scripts" / "evaluate_cccd_heldout_once.py",
        )
