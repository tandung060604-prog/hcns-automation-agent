from __future__ import annotations

import http.client
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from test_template_first import docx_bytes, leave_lines

from hcns_agent.templates.service import build_default_template_processing_service

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from apps.ocr_lab.api.serve_dashboard_api import (  # noqa: E402
    DashboardHandler,
    UserOCRService,
)


def configure_handler(data_root: Path) -> None:
    DashboardHandler.data_root = data_root
    DashboardHandler.heldout_root = None
    DashboardHandler.native_indexes = {}
    DashboardHandler.user_ocr = UserOCRService(data_root)
    DashboardHandler.template_processor = build_default_template_processing_service()


def test_template_endpoints_process_docx_without_ocr(tmp_path: Path) -> None:
    configure_handler(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request("GET", "/api/templates")
        response = connection.getresponse()
        templates_payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert [item["templateId"] for item in templates_payload["templates"]] == [
            "leave-request-v1",
            "overtime-request-v1",
        ]

        boundary = "synthetic-template-boundary"
        payload = _multipart_payload(
            boundary,
            "opaque.docx",
            docx_bytes(leave_lines()),
        )
        connection.request(
            "POST",
            "/api/documents/process",
            body=payload,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(payload)),
            },
        )
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert result["status"] == "SUCCESS"
        assert result["templateId"] == "leave-request-v1"
        assert result["quality"]["recommendedAction"] == "AUTO_CONTINUE"
        reference = Path(result["camundaVariables"]["extractedDataReference"])
        assert (tmp_path / reference).is_file()

        document_id = result["data"]["documentId"]
        connection.request("DELETE", f"/user/session?id={document_id}")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read().decode("utf-8")) == {"deleted": True}
        assert not (tmp_path / reference).exists()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_template_endpoint_rejects_non_docx_separately(tmp_path: Path) -> None:
    configure_handler(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        boundary = "synthetic-template-boundary"
        payload = _multipart_payload(boundary, "unsupported.pdf", b"%PDF-synthetic")
        connection.request(
            "POST",
            "/api/documents/process",
            body=payload,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(payload)),
            },
        )
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        assert response.status == 415
        assert result["status"] == "REJECT_UNSUPPORTED"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_template_endpoint_maps_unexpected_parser_failure_to_technical_error(
    tmp_path: Path,
) -> None:
    configure_handler(tmp_path)

    class FailingProcessor:
        def process(
            self,
            source: object,
            *,
            result_reference: str | None = None,
        ) -> object:
            raise RuntimeError("synthetic parser failure")

    DashboardHandler.template_processor = FailingProcessor()  # type: ignore[assignment]
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        boundary = "synthetic-template-boundary"
        payload = _multipart_payload(boundary, "opaque.docx", docx_bytes(leave_lines()))
        connection.request(
            "POST",
            "/api/documents/process",
            body=payload,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(payload)),
            },
        )
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        assert response.status == 500
        assert result == {
            "status": "TECHNICAL_ERROR",
            "recommendedAction": "TECHNICAL_ERROR",
            "errorCode": "TEMPLATE_PROCESSING_FAILED",
        }
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _multipart_payload(boundary: str, filename: str, content: bytes) -> bytes:
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("ascii")
    return header + content + f"\r\n--{boundary}--\r\n".encode("ascii")
