"""Seed synthetic sources and start demo process instances on a local Camunda.

Writes synthetic DOCX files into the private source root expected by the
External Task worker (HCNS_CAMUNDA_PRIVATE_ROOT/user_uploads/sessions), starts
one leave and one overtime process instance through the Camunda REST API and
completes the initial "Cung cấp tài liệu HCNS" user task so the flow advances
until the next human or external task.

No real PII is used; every value is synthetic.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcns_agent.adapters.camunda7.dry_run import _leave_lines, _overtime_lines  # noqa: E402


def docx_bytes(lines: list[str]) -> bytes:
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>" for line in lines
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        f"{paragraphs}<w:sectPr/></w:body></w:document>"
    )
    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def seed_document(private_root: Path, reference: str, lines: list[str]) -> Path:
    directory = private_root / "user_uploads" / "sessions" / reference / "input"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "document.docx"
    path.write_bytes(docx_bytes(lines))
    return path


def _post_json(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: float = 30.0,
) -> Any:
    request = Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content = response.read()
    except HTTPError as error:
        raise RuntimeError(f"Camunda REST returned HTTP {error.code}: {path}") from error
    except URLError as error:
        raise RuntimeError("Camunda engine is unavailable") from error
    return json.loads(content.decode("utf-8")) if content else {}


def _get_json(
    base_url: str,
    path: str,
    *,
    timeout_seconds: float = 30.0,
) -> Any:
    request = Request(
        base_url.rstrip("/") + path,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content = response.read()
    except HTTPError as error:
        raise RuntimeError(f"Camunda REST returned HTTP {error.code}: {path}") from error
    except URLError as error:
        raise RuntimeError("Camunda engine is unavailable") from error
    return json.loads(content.decode("utf-8")) if content else {}


def start_process_instance(
    base_url: str,
    *,
    application_id: str,
    document_reference: str,
    declared_document_type: str,
) -> str:
    payload = {
        "variables": {
            "applicationId": {"value": application_id, "type": "String"},
            "documentReference": {"value": document_reference, "type": "String"},
            "declaredDocumentType": {
                "value": declared_document_type,
                "type": "String",
            },
        }
    }
    result = _post_json(
        base_url,
        "/process-definition/key/hr_document_agent_mvp_v2/start",
        payload,
    )
    return result["id"]


def complete_user_task(
    base_url: str,
    task_id: str,
    variables: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {}
    if variables:
        payload["variables"] = {
            name: {"value": value, "type": _camunda_type(value)}
            for name, value in variables.items()
        }
    _post_json(base_url, f"/task/{task_id}/complete", payload)


def _camunda_type(value: Any) -> str:
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Long"
    if isinstance(value, float):
        return "Double"
    return "String"


def submit_task(base_url: str, process_instance_id: str) -> str | None:
    tasks = _get_json(base_url, f"/task?processInstanceId={process_instance_id}&sortBy=created&sortOrder=asc")
    if not tasks:
        return None
    return tasks[0]["id"]


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine-rest-url",
        default="http://localhost:8080/engine-rest",
    )
    parser.add_argument(
        "--private-root",
        type=Path,
        default=ROOT / ".private" / "camunda",
        help="HCNS_CAMUNDA_PRIVATE_ROOT for the worker",
    )
    args = parser.parse_args()

    base_url = args.engine_rest_url.rstrip("/")
    private_root = args.private_root.resolve()
    private_root.mkdir(parents=True, exist_ok=True)

    cases = (
        ("leave-01", "LEAVE_REQUEST", _leave_lines()),
        ("overtime-01", "OVERTIME_REQUEST", _overtime_lines()),
    )
    started: list[dict[str, str]] = []
    for application_id, doc_type, lines in cases:
        reference = f"demo-{application_id}"
        seed_document(private_root, reference, lines)
        process_id = start_process_instance(
            base_url,
            application_id=f"APP-{application_id}",
            document_reference=reference,
            declared_document_type=doc_type,
        )
        started.append(
            {"applicationId": f"APP-{application_id}", "processInstanceId": process_id}
        )
        time.sleep(1)
        task_id = submit_task(base_url, process_id)
        if task_id is not None:
            complete_user_task(
                base_url,
                task_id,
                {
                    "applicationId": f"APP-{application_id}",
                    "documentReference": reference,
                    "declaredDocumentType": doc_type,
                },
            )

    print(json.dumps({"privateRoot": str(private_root), "instances": started}, indent=2))
    print(
        "\nOpen Camunda Cockpit: http://localhost:8080/camunda/\n"
        "Run the worker in another terminal: scripts/run_camunda_worker.sh"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
