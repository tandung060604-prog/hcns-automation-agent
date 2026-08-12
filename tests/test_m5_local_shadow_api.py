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

from serve_dashboard_api import DashboardHandler, UserOCRService  # noqa: E402

from hcns_agent.adapters.camunda7.local_shadow_review import (  # noqa: E402
    LocalShadowReviewError,
    load_shadow_review_report,
)


def _report(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "milestone": "M5-CAM-001D",
                "evaluationKind": "m5-local-shadow-review-only",
                "mode": "LOCAL_SHADOW_REVIEW_ONLY",
                "passed": True,
                "documentCount": 3,
                "manualReviewCount": 3,
                "scanManualReviewCount": 1,
                "unsupportedManualReviewCount": 1,
                "idempotencyMismatchCount": 0,
                "duplicateReferenceCount": 0,
                "rawExposureCount": 0,
                "autoContinueCount": 0,
                "camundaProcessStartAttempts": 0,
                "realSideEffectCount": 0,
                "groundTruthUsed": False,
                "evaluateOnceArtifactTouched": False,
                "containsRawFieldValues": False,
                "promotionAllowed": False,
                "fields": {"full_name": "SYNTHETIC PRIVATE VALUE"},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_report_loader_whitelists_aggregate_only_values(tmp_path: Path) -> None:
    payload = load_shadow_review_report(str(_report(tmp_path / "report.json")))
    assert payload["documentCount"] == 3
    assert "fields" not in payload
    assert "SYNTHETIC PRIVATE VALUE" not in json.dumps(payload)


def test_report_loader_rejects_non_aggregate_report(tmp_path: Path) -> None:
    path = _report(tmp_path / "report.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["containsRawFieldValues"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalShadowReviewError, match="aggregate-only"):
        load_shadow_review_report(str(path))


def test_removed_m5_summary_endpoint_returns_not_found_without_mutation(tmp_path: Path) -> None:
    report = _report(tmp_path / "report.json")
    DashboardHandler.data_root = tmp_path
    DashboardHandler.cccd_heldout_root = None
    DashboardHandler.external_dataset_root = None
    DashboardHandler.m5_local_shadow_report = report
    DashboardHandler.native_indexes = {}
    DashboardHandler.user_ocr = UserOCRService(tmp_path)
    DashboardHandler.template_processor = None  # type: ignore[assignment]
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        connection.request("GET", "/m5/local-shadow-review/summary")
        response = connection.getresponse()
        response.read()
        assert response.status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
