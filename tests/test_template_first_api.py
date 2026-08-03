from __future__ import annotations

import http.client
import json
import sys
import threading
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

from synthetic_fixtures import administrative_image_bytes, scanned_pdf_bytes
from test_template_first import docx_bytes, leave_lines

from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.bootstrap import build_default_intake
from hcns_agent.templates.registry import build_default_template_registry
from hcns_agent.templates.service import (
    TemplateProcessingService,
    TemplateTechnicalError,
    build_default_template_processing_service,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from apps.ocr_lab.api.serve_dashboard_api import (  # noqa: E402
    DashboardHandler,
    UserOCRService,
)


def configure_handler(
    data_root: Path,
    processor: TemplateProcessingService | None = None,
) -> None:
    DashboardHandler.data_root = data_root
    DashboardHandler.heldout_root = None
    DashboardHandler.cccd_heldout_root = None
    DashboardHandler.native_indexes = {}
    DashboardHandler.user_ocr = UserOCRService(data_root)
    DashboardHandler.template_processor = (
        processor or build_default_template_processing_service()
    )


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
        document_content = docx_bytes(leave_lines())
        payload = _multipart_payload(
            boundary,
            "opaque.docx",
            document_content,
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
        legacy_dir = tmp_path / "user_uploads" / "sessions" / "legacy-session"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "result.json").write_text(
            json.dumps({"documentType": "OTHER_HR_DOCUMENT"}),
            encoding="utf-8",
        )
        connection.request("GET", "/api/documents/sessions")
        response = connection.getresponse()
        sessions_payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert sessions_payload["sessions"] == [
            {
                "documentId": document_id,
                "createdAt": sessions_payload["sessions"][0]["createdAt"],
                "originalFileName": "opaque.docx",
                "documentType": "LEAVE_REQUEST",
                "templateId": "leave-request-v1",
                "templateVersion": "1.0",
                "status": "SUCCESS",
                "recommendedAction": "AUTO_CONTINUE",
                "confidence": 1.0,
                "sourceFormat": "DOCX",
                "usesOcr": False,
                "parserName": "docx/ooxml-native",
            }
        ]

        connection.request("GET", f"/api/documents/result?id={document_id}")
        response = connection.getresponse()
        stored_result = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert stored_result == result

        connection.request("GET", f"/api/documents/source?id={document_id}")
        response = connection.getresponse()
        stored_source = response.read()
        assert response.status == 200
        assert response.getheader("Content-Type") == (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        )
        assert stored_source == document_content

        connection.request("DELETE", f"/user/session?id={document_id}")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read().decode("utf-8")) == {"deleted": True}
        assert not (tmp_path / reference).exists()

        connection.request("GET", "/api/documents/sessions")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read().decode("utf-8")) == {"sessions": []}
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_api_root_redirects_to_local_dashboard(tmp_path: Path) -> None:
    configure_handler(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        response.read()
        assert response.status == 307
        assert response.getheader("Location") == "http://localhost:3000"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_template_preview_renders_pdf_and_preserves_image(tmp_path: Path) -> None:
    configure_handler(tmp_path)
    session_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    sources = [
        ("document.pdf", scanned_pdf_bytes(), "image/png"),
        ("document.png", administrative_image_bytes(), "image/png"),
    ]
    for session_id, (filename, content, _) in zip(session_ids, sources, strict=True):
        session_dir = tmp_path / "user_uploads" / "sessions" / session_id
        (session_dir / "input").mkdir(parents=True)
        (session_dir / "template_first").mkdir()
        (session_dir / "input" / filename).write_bytes(content)
        (session_dir / "template_first" / "result.json").write_text(
            json.dumps({"documentType": "LEAVE_REQUEST"}),
            encoding="utf-8",
        )

    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        for session_id, (_, content, expected_type) in zip(
            session_ids,
            sources,
            strict=True,
        ):
            connection.request("GET", f"/api/documents/preview?id={session_id}")
            response = connection.getresponse()
            preview = response.read()
            assert response.status == 200
            assert response.getheader("Content-Type") == expected_type
            assert preview.startswith(b"\x89PNG\r\n\x1a\n")
            if content.startswith(b"\x89PNG"):
                assert preview == content
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_template_endpoint_rejects_unsupported_extension_separately(
    tmp_path: Path,
) -> None:
    configure_handler(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        boundary = "synthetic-template-boundary"
        payload = _multipart_payload(boundary, "unsupported.txt", b"synthetic")
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
        assert result["errorCode"] == "SUPPORTED_TEMPLATE_FORMAT_REQUIRED"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_template_endpoint_processes_image_with_injected_ocr(
    tmp_path: Path,
) -> None:
    ocr = DeterministicMockOcrEngine(
        text="\n".join(leave_lines()),
        confidence=0.91,
    )
    processor = TemplateProcessingService(
        intake=build_default_intake(ocr),
        registry=build_default_template_registry(),
        ocr_engine=ocr,
    )
    configure_handler(tmp_path, processor)
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        boundary = "synthetic-template-boundary"
        payload = _multipart_payload(
            boundary,
            "synthetic-camera.png",
            administrative_image_bytes(),
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
        assert result["documentType"] == "LEAVE_REQUEST"
        assert result["processing"]["sourceFormat"] == "IMAGE"
        assert result["processing"]["usesOcr"] is True
        assert result["quality"]["recommendedAction"] == "MANUAL_REVIEW"
        assert "OCR_REVIEW_REQUIRED" in result["quality"]["validationErrors"]
        document_id = result["data"]["documentId"]
        connection.request("GET", f"/api/documents/source?id={document_id}")
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "image/png"
        assert response.read() == administrative_image_bytes()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_template_endpoint_reports_unavailable_ocr_as_service_unavailable(
    tmp_path: Path,
) -> None:
    configure_handler(tmp_path)

    class UnavailableOcrProcessor:
        def process(
            self,
            source: object,
            *,
            result_reference: str | None = None,
        ) -> object:
            raise TemplateTechnicalError("OCR_RUNTIME_UNAVAILABLE")

    DashboardHandler.template_processor = UnavailableOcrProcessor()  # type: ignore[assignment]
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        boundary = "synthetic-template-boundary"
        payload = _multipart_payload(
            boundary,
            "synthetic-camera.png",
            administrative_image_bytes(),
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
        assert response.status == 503
        assert result["errorCode"] == "OCR_RUNTIME_UNAVAILABLE"
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
