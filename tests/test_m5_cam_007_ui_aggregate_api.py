from __future__ import annotations

import hashlib
import http.client
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from serve_dashboard_api import DashboardHandler, UserOCRService  # noqa: E402

from hcns_agent.adapters.camunda7.local_shadow_review import (  # noqa: E402
    LocalShadowReviewError,
    load_m5_cam_006_smoke_report,
)


def _report(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "milestone": "M5-CAM-006",
                "evaluationKind": "localhost-api-phase15-bridge-read-only-smoke",
                "mode": "LOCAL_SYNTHETIC_READ_ONLY",
                "passed": True,
                "fixtureCount": 2,
                "getRequestCount": 2,
                "postRequestCount": 0,
                "httpMethodPolicy": "GET_ONLY",
                "phase15BridgeProjectionCount": 2,
                "manualReviewCount": 2,
                "autoContinueCount": 0,
                "scalarOnly": True,
                "opaqueReferenceOnly": True,
                "schemaWhitelistErrorCount": 0,
                "nonScalarValueCount": 0,
                "sourceMutationCount": 0,
                "camundaProcessStartAttempts": 0,
                "hrisSideEffectCount": 0,
                "notificationSideEffectCount": 0,
                "groundTruthUsed": False,
                "evaluateOnceArtifactTouched": False,
                "realCohortOpened": False,
                "containsRawFieldValues": False,
                "promotionAllowed": False,
                "fields": {"full_name": "SYNTHETIC PRIVATE VALUE"},
                "documentPath": "C:/private/raw.pdf",
            }
        ),
        encoding="utf-8",
    )
    return path


class M5Cam007UiAggregateApiTests(unittest.TestCase):
    def test_read_only_summary_has_no_raw_payload_or_mutation(self) -> None:
        # This test uses a real temporary directory without depending on any private artifact.
        import tempfile

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            report = _report(root_path / "report.json")
            source_digest = hashlib.sha256(report.read_bytes()).hexdigest()
            payload = load_m5_cam_006_smoke_report(str(report))
            self.assertEqual(payload["fixtureCount"], 2)
            self.assertNotIn("fields", json.dumps(payload))
            self.assertNotIn("documentPath", json.dumps(payload))
            self.assertNotIn("SYNTHETIC PRIVATE VALUE", json.dumps(payload))

            DashboardHandler.data_root = root_path
            DashboardHandler.cccd_heldout_root = None
            DashboardHandler.external_dataset_root = None
            DashboardHandler.m5_local_shadow_report = None
            DashboardHandler.m5_cam_006_smoke_report = report
            DashboardHandler.native_indexes = {}
            DashboardHandler.user_ocr = UserOCRService(root_path)
            DashboardHandler.template_processor = None  # type: ignore[assignment]
            server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for method in ("GET", "POST", "DELETE"):
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", server.server_port, timeout=10
                    )
                    connection.request(method, "/m5/cam-006/summary")
                    response = connection.getresponse()
                    body = response.read()
                    connection.close()
                    if method == "GET":
                        self.assertEqual(response.status, 200)
                        response_payload = json.loads(body)
                        self.assertEqual(response_payload["httpMethodPolicy"], "GET_ONLY")
                        self.assertNotIn("fields", body.decode())
                        self.assertNotIn("documentPath", body.decode())
                        self.assertNotIn("SYNTHETIC PRIVATE VALUE", body.decode())
                    else:
                        self.assertEqual(response.status, 405)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(), source_digest)

    def test_loader_rejects_promotion_or_raw_report(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as root:
            report = _report(Path(root) / "report.json")
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["containsRawFieldValues"] = True
            report.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(LocalShadowReviewError, "aggregate-only"):
                load_m5_cam_006_smoke_report(str(report))


if __name__ == "__main__":
    unittest.main()
