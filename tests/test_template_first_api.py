from __future__ import annotations

import http.client
import json
import sys
import threading
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from synthetic_fixtures import (
    administrative_image_bytes,
    administrative_jpeg_bytes,
    scanned_pdf_bytes,
    synthetic_text_pdf_bytes,
)
from test_template_first import docx_bytes, ielts_lines, leave_lines

import hcns_agent.templates.service as template_service
from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.bootstrap import build_default_intake
from hcns_agent.templates.registry import build_default_template_registry
from hcns_agent.templates.service import (
    TemplateProcessingService,
    TemplateTechnicalError,
    build_default_template_processing_service,
    build_local_template_processing_service,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from template_result_comparison import compare_template_result  # noqa: E402

import apps.ocr_lab.api.serve_dashboard_api as dashboard_api  # noqa: E402
from apps.ocr_lab.api.serve_dashboard_api import (  # noqa: E402
    DashboardHandler,
    UserOCRService,
)


def configure_handler(
    data_root: Path,
    processor: TemplateProcessingService | None = None,
) -> None:
    DashboardHandler.data_root = data_root
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
            "cv-v2",
            "ielts-certificate-v2",
            "leave-request-v1",
            "overtime-request-v1",
            "probation-contract-v2",
            "vietnam-citizen-id-front-v1",
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
        assert result["processing"]["timingsMs"]["ocr"] == 0
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


def test_current_file_comparison_is_private_and_reopenable(tmp_path: Path) -> None:
    configure_handler(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        boundary = "synthetic-template-boundary"
        upload = _multipart_payload(boundary, "leave.docx", docx_bytes(leave_lines()))
        connection.request(
            "POST",
            "/api/documents/process",
            body=upload,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(upload)),
            },
        )
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        document_id = result["data"]["documentId"]

        ground_truth = {
            name: value
            for name, value in result["data"].items()
            if name
            not in {
                "documentId",
                "documentType",
                "templateId",
                "templateVersion",
                "schemaVersion",
                "missingFields",
                "validationErrors",
                "confidence",
                "recommendedAction",
                "sourceFile",
            }
        }
        body = json.dumps(
            {"documentId": document_id, "groundTruth": ground_truth}
        ).encode("utf-8")
        connection.request(
            "POST",
            "/api/documents/compare",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        response = connection.getresponse()
        comparison = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert comparison["scope"] == "CURRENT_FILE"
        assert comparison["matchingPolicyVersion"] == "2.0.0"
        assert comparison["summary"]["decision"] == "PASS"
        assert comparison["summary"]["wrongFields"] == 0
        assert comparison["workflow"]["promotionAllowed"] is False

        comparison_path = (
            tmp_path
            / "user_uploads"
            / "sessions"
            / document_id
            / "template_first"
            / "comparison.json"
        )
        assert comparison_path.is_file()
        connection.request("GET", f"/api/documents/comparison?id={document_id}")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read().decode("utf-8")) == comparison
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_current_file_comparison_exposes_all_review_badges() -> None:
    result = {
        "documentType": "CV",
        "templateId": "cv-v2",
        "templateVersion": "2.0",
        "data": {
            "documentId": str(uuid.uuid4()),
            "full_name": "CANDIDATE SYNTHETIC",
            "skills": "Python Playwright extra",
            "email": "wrong@example.test",
            "phone_number": None,
            "address": "SYNTHETIC ADDRESS",
        },
        "quality": {
            "missingFields": ["phone_number"],
            "confidence": 0.8,
            "recommendedAction": "MANUAL_REVIEW",
        },
        "processing": {
            "usesOcr": False,
            "parserName": "docx/ooxml-native",
        },
    }
    comparison = compare_template_result(
        result,
        {
            "full_name": "CANDIDATE SYNTHETIC",
            "skills": "Python Playwright",
            "email": "synthetic@example.test",
            "phone_number": "0000000000",
        },
    )

    statuses = {field["name"]: field["status"] for field in comparison["fields"]}
    assert statuses == {
        "full_name": "EXACT",
        "skills": "ACCEPTED",
        "email": "MISMATCH",
        "phone_number": "MISSING",
        "address": "NEEDS_REVIEW",
    }
    assert comparison["summary"]["decision"] == "HOLD"
    assert comparison["summary"]["wrongFields"] == 2


def test_api_rejects_non_local_host_header(tmp_path: Path) -> None:
    configure_handler(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request("GET", "/health", headers={"Host": "attacker.example"})
        response = connection.getresponse()
        assert response.status == 400
        assert json.loads(response.read().decode("utf-8")) == {
            "error": "Local dashboard Host header is required"
        }
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_health_exposes_active_template_runtime_without_document_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(template_service, "find_spec", lambda name: object())
    configure_handler(
        tmp_path,
        build_local_template_processing_service(ocr_backend="easyocr"),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        upload = payload["userUpload"]
        assert upload["runtimeProfile"] == "template-first"
        assert upload["templateOcrBackend"] == "easyocr"
        assert upload["templateOcrProfile"] == "easyocr/vi-greedy"
        assert upload["backendAvailable"] is True
        assert len(upload["pipelines"]) == 6
        assert set(upload["pipelines"][0]) == {
            "documentType",
            "templateId",
            "templateVersion",
            "parserId",
            "parserVersion",
            "supportedFileTypes",
            "lifecycle",
        }
        serialized = json.dumps(upload)
        assert "sourceFile" not in serialized
        assert "documentId" not in serialized
        assert "private" not in serialized.casefold()
        assert "paddleOcrAvailable" in upload
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_camunda_json_endpoint_rejects_oversized_body(tmp_path: Path) -> None:
    configure_handler(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.putrequest("POST", "/api/camunda/start")
        connection.putheader("Host", f"127.0.0.1:{server.server_port}")
        connection.putheader("Content-Type", "application/json")
        connection.putheader(
            "Content-Length",
            str(dashboard_api.MAX_REVIEW_BYTES + 1),
        )
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 413
        assert json.loads(response.read().decode("utf-8")) == {
            "error": "Request body is empty or exceeds 2 MB"
        }
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_camunda_start_accepts_contract_cv_and_ielts_with_opaque_variables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_handler(tmp_path)
    monkeypatch.setenv("HCNS_CAMUNDA_PRIVATE_ROOT", str(tmp_path))
    posted: list[tuple[str, dict[str, object]]] = []
    process_ids = iter(["process-cv", "process-contract", "process-ielts"])

    def fake_post(url: str, payload: dict[str, object]) -> object:
        posted.append((url, payload))
        if url.endswith("/process-definition/key/hr_document_agent_mvp_v2/start"):
            return {"id": next(process_ids)}
        return None

    def fake_get(url: str) -> object:
        if "task?processInstanceId=" in url and url.endswith("&taskDefinitionKey=Submit"):
            return [{"id": f"submit-{len(posted)}"}]
        raise AssertionError(url)

    monkeypatch.setattr(dashboard_api, "_camunda_post", fake_post)
    monkeypatch.setattr(dashboard_api, "_camunda_get", fake_get)
    documents = [
        ("cv.docx", docx_bytes(["CURRICULUM VITAE", "Kinh nghiem: QA", "Ky nang: Python"]), "CV"),
        (
            "contract.docx",
            docx_bytes(["HOP DONG THU VIEC", "THOI GIAN THU VIEC: 60 ngay", "MUC LUONG: 10000000"]),
            "EMPLOYMENT_CONTRACT",
        ),
        ("ielts.pdf", synthetic_text_pdf_bytes(ielts_lines()), "CERTIFICATE"),
    ]
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        responses: list[dict[str, object]] = []
        for index, (filename, content, expected_type) in enumerate(documents):
            boundary = f"camunda-family-{index}"
            upload = _multipart_payload(boundary, filename, content)
            connection.request(
                "POST",
                "/api/documents/process",
                body=upload,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(len(upload)),
                },
            )
            response = connection.getresponse()
            result = json.loads(response.read().decode("utf-8"))
            assert response.status == 200, result
            assert result["documentType"] == expected_type

            body = json.dumps({"documentId": result["data"]["documentId"]})
            connection.request(
                "POST",
                "/api/camunda/start",
                body=body,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200, payload
            responses.append(payload)

        assert [item["processInstanceId"] for item in responses] == [
            "process-cv",
            "process-contract",
            "process-ielts",
        ]
        assert all(
            item["performance"]["schemaVersion"] == "hcns-stage-timing/1.0.0"
            and item["performance"]["timingsMs"]["camunda"] >= 0
            for item in responses
        )
        starts = [payload for url, payload in posted if url.endswith("/start")]
        assert [
            item["variables"]["declaredDocumentType"]["value"]  # type: ignore[index]
            for item in starts
        ] == ["CV", "EMPLOYMENT_CONTRACT", "CERTIFICATE"]
        assert all(set(item["variables"]) == {  # type: ignore[arg-type]
            "applicationId", "documentReference", "declaredDocumentType"
        } for item in starts)
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_camunda_start_rejects_unsupported_type_and_private_root_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_handler(tmp_path)
    document_id = str(uuid.uuid4())
    monkeypatch.setattr(
        DashboardHandler.user_ocr,
        "template_result",
        lambda _: {"documentType": "CITIZEN_ID"},
    )
    monkeypatch.setattr(
        DashboardHandler.user_ocr,
        "template_source",
        lambda _: tmp_path / "private-source.docx",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        body = json.dumps({"documentId": document_id})
        connection.request(
            "POST",
            "/api/camunda/start",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 400
        assert payload == {
            "error": "Document type is not available for Camunda local shadow"
        }

        monkeypatch.setattr(
            DashboardHandler.user_ocr,
            "template_result",
            lambda _: {"documentType": "CV"},
        )
        monkeypatch.setenv("HCNS_CAMUNDA_PRIVATE_ROOT", str(tmp_path / "other-root"))
        connection.request(
            "POST",
            "/api/camunda/start",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 400
        assert payload == {
            "error": "HCNS_CAMUNDA_PRIVATE_ROOT must match the dashboard data root"
        }
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_camunda_case_status_exposes_only_safe_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_handler(tmp_path)

    def fake_get(url: str) -> object:
        process_id = "process-active" if "process-active" in url else "process-rejected"
        if "/task?" in url:
            return ([{"id": "task-hr", "taskDefinitionKey": "HRReview", "name": "HR review"}]
                    if process_id == "process-active" else [])
        if "/incident?" in url:
            return []
        if "/history/process-instance/" in url:
            return {"state": "ACTIVE" if process_id == "process-active" else "COMPLETED"}
        if "/history/variable-instance?" in url:
            variables: list[dict[str, str]] = [
                {"name": "applicationId", "value": "LOCAL-CASE"},
                {"name": "declaredDocumentType", "value": "CV"},
                {"name": "ignoredRawValue", "value": "must-not-be-returned"},
            ]
            if process_id == "process-rejected":
                variables.append({"name": "hrReviewDecision", "value": "REJECTED"})
            return variables
        raise AssertionError(url)

    monkeypatch.setattr(dashboard_api, "_camunda_get", fake_get)
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        expected = [
            ("process-active", "AWAITING_HR_REVIEW", "task-hr"),
            ("process-rejected", "REJECTED", None),
        ]
        for process_id, state, task_id in expected:
            connection.request("GET", f"/api/camunda/case?id={process_id}")
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["state"] == state
            assert payload["taskId"] == task_id
            assert payload["documentType"] == "CV"
            assert payload["incidentCount"] == 0
            assert "ignoredRawValue" not in payload

        connection.request("GET", "/api/camunda/case?id=bad/id")
        response = connection.getresponse()
        assert response.status == 400
        assert json.loads(response.read().decode("utf-8")) == {
            "error": "Camunda process instance id is invalid"
        }
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_local_camunda_queue_and_employee_review_use_opaque_reference(
    tmp_path: Path, monkeypatch: object
) -> None:
    configure_handler(tmp_path)
    posted: list[tuple[str, dict[str, object]]] = []

    def fake_get(url: str) -> object:
        if "processDefinitionKey" in url:
            return [{"id": "task-1", "taskDefinitionKey": "UserReview", "name": "Confirm"}]
        if url.endswith("/variables"):
            return {
                "documentReference": {"value": "00000000-0000-0000-0000-000000000001"},
                "documentType": {"value": "LEAVE_REQUEST"},
            }
        if url.endswith("/task/task-1"):
            return {"id": "task-1", "taskDefinitionKey": "UserReview", "assignee": None}
        raise AssertionError(url)

    def fake_post(url: str, payload: dict[str, object]) -> None:
        posted.append((url, payload))
        return None

    monkeypatch.setattr(dashboard_api, "_camunda_get", fake_get)  # type: ignore[attr-defined]
    monkeypatch.setattr(dashboard_api, "_camunda_post", fake_post)  # type: ignore[attr-defined]
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request("GET", "/api/camunda/queue")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read().decode("utf-8")) == {
            "queue": [{
                "taskId": "task-1", "role": "employee", "taskName": "Confirm",
                "documentId": "00000000-0000-0000-0000-000000000001",
                "documentType": "LEAVE_REQUEST", "created": "", "inspectable": False,
            }]
        }
        body = json.dumps({"taskId": "task-1", "role": "employee", "decision": "UNRESOLVED"})
        connection.request(
            "POST",
            "/api/camunda/review",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read().decode("utf-8")) == {
            "status": "COMPLETED",
            "decision": "UNRESOLVED",
        }
        assert posted == [
            ("http://127.0.0.1:8080/engine-rest/task/task-1/claim", {"userId": "local-employee"}),
            (
                "http://127.0.0.1:8080/engine-rest/task/task-1/complete",
                {"variables": {"userReviewDecision": {"value": "UNRESOLVED", "type": "String"}}},
            ),
        ]
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
        payload = _multipart_payload(boundary, "unsupported.doc", b"synthetic")
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


def test_template_endpoint_accepts_ielts_image_with_local_ocr(
    tmp_path: Path,
) -> None:
    ocr = DeterministicMockOcrEngine(text="\n".join(ielts_lines()), confidence=0.94)
    configure_handler(
        tmp_path,
        TemplateProcessingService(
            intake=build_default_intake(ocr),
            registry=build_default_template_registry(),
            ocr_engine=ocr,
        ),
    )
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
        assert result["templateId"] == "ielts-certificate-v2"
        assert result["processing"]["sourceFormat"] == "IMAGE"
        assert result["processing"]["usesOcr"] is True
        assert result["processing"]["timingSchemaVersion"] == "hcns-stage-timing/1.0.0"
        assert set(result["processing"]["timingsMs"]) == {
            "intake",
            "ocr",
            "template",
            "serviceTotal",
            "persistence",
            "total",
        }
        assert all(
            isinstance(value, (int, float)) and value >= 0
            for value in result["processing"]["timingsMs"].values()
        )
        assert result["processing"]["timingsMs"]["ocr"] == 1
        performance_path = (
            tmp_path
            / "user_uploads"
            / "sessions"
            / result["data"]["documentId"]
            / "template_first"
            / "performance.json"
        )
        performance = json.loads(performance_path.read_text(encoding="utf-8"))
        assert set(performance) == {"schemaVersion", "timingsMs"}
        assert "Candidate name" not in json.dumps(performance)
        assert result["quality"]["recommendedAction"] == "MANUAL_REVIEW"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_template_endpoint_rejects_image_for_native_only_template(
    tmp_path: Path,
) -> None:
    ocr = DeterministicMockOcrEngine(text="\n".join(leave_lines()), confidence=0.94)
    configure_handler(
        tmp_path,
        TemplateProcessingService(
            intake=build_default_intake(ocr),
            registry=build_default_template_registry(),
            ocr_engine=ocr,
        ),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        boundary = "synthetic-template-boundary"
        upload = _multipart_payload(
            boundary,
            "leave.png",
            administrative_image_bytes(),
        )
        connection.request(
            "POST",
            "/api/documents/process",
            body=upload,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(upload)),
            },
        )
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        assert response.status == 422
        assert result["errorCode"] == "Template does not support this file type"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    ("filename", "content", "ocr_text", "expected_template", "expected_format"),
    [
        (
            "cv.docx",
            docx_bytes(["CURRICULUM VITAE", "Kinh nghiem: Synthetic", "Ky nang: Python"]),
            "",
            "cv-v2",
            "DOCX",
        ),
        (
            "cv.pdf",
            synthetic_text_pdf_bytes(
                ["CURRICULUM VITAE", "Kinh nghiem: Synthetic", "Ky nang: Python"]
            ),
            "",
            "cv-v2",
            "PDF_TEXT",
        ),
        (
            "probation-contract.docx",
            docx_bytes(["HOP DONG THU VIEC", "THOI GIAN THU VIEC: 60 ngay", "MUC LUONG: 10000000"]),
            "",
            "probation-contract-v2",
            "DOCX",
        ),
        (
            "probation-contract.pdf",
            synthetic_text_pdf_bytes(
                [
                    "HOP DONG THU VIEC",
                    "THOI GIAN THU VIEC: 60 ngay",
                    "MUC LUONG: 10000000",
                ]
            ),
            "",
            "probation-contract-v2",
            "PDF_TEXT",
        ),
        (
            "ielts.pdf",
            synthetic_text_pdf_bytes(ielts_lines()),
            "",
            "ielts-certificate-v2",
            "PDF_TEXT",
        ),
        (
            "ielts.png",
            administrative_image_bytes(),
            "\n".join(ielts_lines()),
            "ielts-certificate-v2",
            "IMAGE",
        ),
        (
            "ielts.jpg",
            administrative_jpeg_bytes(),
            "\n".join(ielts_lines()),
            "ielts-certificate-v2",
            "IMAGE",
        ),
    ],
)
def test_template_endpoint_smoke_supported_family_formats(
    tmp_path: Path,
    filename: str,
    content: bytes,
    ocr_text: str,
    expected_template: str,
    expected_format: str,
) -> None:
    ocr = DeterministicMockOcrEngine(text=ocr_text, confidence=0.94)
    configure_handler(
        tmp_path,
        TemplateProcessingService(
            intake=build_default_intake(ocr),
            registry=build_default_template_registry(),
            ocr_engine=ocr,
        ),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        boundary = "synthetic-template-boundary"
        upload = _multipart_payload(boundary, filename, content)
        connection.request(
            "POST",
            "/api/documents/process",
            body=upload,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(upload)),
            },
        )
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        assert response.status == 200, result
        assert result["templateId"] == expected_template
        assert result["processing"]["sourceFormat"] == expected_format
        assert result["processing"]["originalFileName"] == filename
        assert result["processing"]["processedAt"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_template_endpoint_reports_when_image_ocr_is_unavailable(
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
