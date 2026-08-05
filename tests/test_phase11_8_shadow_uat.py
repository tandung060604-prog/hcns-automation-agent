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

from ocr_ho_v2_diagnostic import document as diagnostic_document  # noqa: E402
from ocr_ho_v2_diagnostic import save as save_diagnostic  # noqa: E402
from phase11_5_cccd import FIELD_ORDER  # noqa: E402
from phase11_8_shadow_uat import (  # noqa: E402
    load_shadow_document,
    load_shadow_summary,
    save_shadow_review,
)
from serve_dashboard_api import DashboardHandler, UserOCRService  # noqa: E402

SESSION_ID = "11111111-1111-4111-8111-111111111111"


def _field(value: str, *, changed: bool = False) -> dict[str, object]:
    return {
        "value": value,
        "asciiValue": value,
        "status": "needs_review",
        "asciiStatus": "needs_review",
        "confidence": 0.88,
        "errorSignals": [],
        "selectionMode": (
            "phase11_5_baseline_preserved" if not changed else "phase11_8_token_consensus"
        ),
        "evidence": {
            "pageIndex": 0,
            "bbox": [1, 2, 30, 40],
            "candidates": [
                {"profile": "paddle_ppocrv5", "value": "synthetic-private"},
                {"profile": "easyocr_vi", "value": "synthetic-private"},
            ],
        },
    }


def build_root(tmp_path: Path) -> Path:
    root = tmp_path / "development-archive"
    session = root / "user_uploads-sessions" / SESSION_ID
    (session / "input").mkdir(parents=True)
    (session / "phase11_5").mkdir()
    (session / "phase11_8_v2").mkdir()
    (root / "output" / "phase11" / "reports").mkdir(parents=True)
    (session / "input" / "document.jpg").write_bytes(b"synthetic image")
    baseline_fields = {name: _field(f"baseline-{name}") for name in FIELD_ORDER}
    candidate_fields = {name: _field(f"baseline-{name}") for name in FIELD_ORDER}
    candidate_fields["placeOfOrigin"] = _field("candidate-origin", changed=True)
    (session / "phase11_5" / "identity_card.json").write_text(
        json.dumps({"fields": baseline_fields}), encoding="utf-8"
    )
    (session / "phase11_8_v2" / "field_consensus.json").write_text(
        json.dumps(
            {
                "schemaVersion": "11.8.1",
                "policyLock": {"recognitionPolicySha256": "sha256:test"},
                "identityCard": {"fields": candidate_fields},
            }
        ),
        encoding="utf-8",
    )
    (session / "result.json").write_text(
        json.dumps(
            {
                "sessionId": SESSION_ID,
                "source": {
                    "originalFileName": "synthetic-cccd.jpg",
                    "format": "JPG",
                    "pageCount": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    report_path = (
        root / "output" / "phase11" / "reports" / "CCCD_OCR_HO_V2_008_DEVELOPMENT_COMPARISON.json"
    )
    report_path.write_text(
        json.dumps(
            {
                "candidateVersion": "11.8.1",
                "policyId": "phase11.8-v2-address-token-consensus",
                "datasetRole": "DEVELOPMENT_REGRESSION",
                "targetFields": ["placeOfOrigin", "placeOfResidence"],
                "protectedFields": ["identityNumber", "fullName"],
                "metrics": {"baseline_phase11_5": {"strictFieldExactMatch": 0.6}},
                "promotionGate": {
                    "status": "DEVELOPMENT_PASS",
                    "productionPromotionAllowed": False,
                    "schemaErrorCount": 0,
                    "manualReviewFieldCount": 8,
                },
            }
        ),
        encoding="utf-8",
    )
    return root


def test_shadow_summary_and_detail_never_load_ground_truth(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    summary = load_shadow_summary(root)
    assert summary["localOnly"] is True
    assert summary["groundTruthLoaded"] is False
    assert summary["documentCount"] == 1
    assert summary["documents"][0]["reviewDecision"] == "PENDING"

    detail = load_shadow_document(root, SESSION_ID)
    assert detail["groundTruthLoaded"] is False
    assert detail["fields"]["placeOfOrigin"]["changed"] is True
    assert detail["fields"]["placeOfOrigin"]["candidate"]["evidence"]["candidateCount"] == 2
    assert "groundTruth" not in detail


def test_shadow_review_requires_source_assertions_and_persists_private_review(
    tmp_path: Path,
) -> None:
    root = build_root(tmp_path)
    with pytest.raises(ValueError, match="assertions"):
        save_shadow_review(root, SESSION_ID, {"decision": "APPROVE_SHADOW", "assertions": {}})
    result = save_shadow_review(
        root,
        SESSION_ID,
        {
            "decision": "APPROVE_SHADOW",
            "assertions": {
                "comparedWithSource": True,
                "checkedChangedFields": True,
                "confirmedManualReview": True,
            },
            "note": "synthetic note",
        },
    )
    assert result["saved"] is True
    assert load_shadow_summary(root)["reviewCounts"]["APPROVE_SHADOW"] == 1
    assert load_shadow_document(root, SESSION_ID)["review"]["decision"] == "APPROVE_SHADOW"


def test_shadow_uat_api_exposes_preview_detail_and_review(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    DashboardHandler.data_root = tmp_path
    DashboardHandler.heldout_root = None
    DashboardHandler.cccd_heldout_root = None
    DashboardHandler.ocr_ho_shadow_root = root
    DashboardHandler.external_dataset_root = None
    DashboardHandler.external_dataset_inventory = None
    DashboardHandler.external_dataset_ground_truth = None
    DashboardHandler.external_dataset_typed_projection = None
    DashboardHandler.external_dataset_typed_approval = None
    DashboardHandler.external_dataset_typed_report = None
    DashboardHandler.native_indexes = {}
    DashboardHandler.user_ocr = UserOCRService(tmp_path)
    DashboardHandler.template_processor = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request("GET", "/ocr-ho-v2/shadow/summary")
        response = connection.getresponse()
        summary = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert summary["groundTruthLoaded"] is False

        connection.request(
            "GET",
            f"/ocr-ho-v2/shadow/document?id={SESSION_ID}&mode=detail",
        )
        response = connection.getresponse()
        detail = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert detail["candidateVersion"] == "11.8.1"

        connection.request(
            "GET",
            f"/ocr-ho-v2/shadow/document?id={SESSION_ID}&mode=preview",
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.read() == b"synthetic image"

        body = json.dumps(
            {
                "decision": "NEEDS_FOLLOWUP",
                "assertions": {
                    "comparedWithSource": True,
                    "checkedChangedFields": True,
                    "confirmedManualReview": True,
                },
            }
        ).encode("utf-8")
        connection.request(
            "POST",
            f"/ocr-ho-v2/shadow/review?id={SESSION_ID}",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        response = connection.getresponse()
        saved = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert saved["decision"] == "NEEDS_FOLLOWUP"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_diagnostic_ground_truth_is_prediction_blind_and_validates_line_ids(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    session = root / "user_uploads-sessions" / SESSION_ID
    result = json.loads((session / "result.json").read_text(encoding="utf-8"))
    result["phase11"] = {
        "pages": [
            {
                "recognizedBoxes": [
                    [[1, 1], [2, 1], [2, 2], [1, 2]],
                    [[3, 3], [4, 3], [4, 4], [3, 4]],
                ]
            }
        ]
    }
    (session / "result.json").write_text(json.dumps(result), encoding="utf-8")
    payload = diagnostic_document(root, SESSION_ID)
    assert payload["predictionLoaded"] is False
    assert payload["predictionOpened"] is False
    with pytest.raises(ValueError, match="Prediction-blind"):
        save_diagnostic(
            root, SESSION_ID, {"predictionOpened": True, "fields": {}, "assertions": {}}
        )
    with pytest.raises(ValueError, match="assertions"):
        save_diagnostic(root, SESSION_ID, {"fields": {}, "assertions": {}})
    saved = save_diagnostic(
        root,
        SESSION_ID,
        {
            "fields": {
                name: {"value": "synthetic", "lineIds": [0]}
                for name in ("fullName", "placeOfOrigin", "placeOfResidence")
            },
            "assertions": {
                "comparedWithSource": True,
                "allTextChecked": True,
                "linesChecked": True,
            },
        },
    )
    assert saved["promotionEligible"] is False
