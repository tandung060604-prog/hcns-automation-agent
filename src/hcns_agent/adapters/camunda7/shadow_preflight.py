"""Local-only synthetic preflight for the Camunda M5 shadow workflow.

This module deliberately has no bridge to the web intake.  It creates only two
synthetic native DOCX sources under a caller-owned private root, deploys the
checked-in BPMN/DMN, and proves the review-first path end to end.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from html import escape
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

from hcns_agent.adapters.camunda7.client import (
    Camunda7ExternalTaskClient,
    Camunda7RestConfig,
    CamundaRestError,
    UrllibCamundaRestTransport,
)
from hcns_agent.adapters.camunda7.contract import (
    PROCESS_VARIABLE_WHITELIST,
    ProcessValue,
)
from hcns_agent.adapters.camunda7.runtime import (
    JsonFileTemplateResultStore,
    LocalSessionDocumentSourceStore,
    build_m4_worker,
)
from hcns_agent.adapters.camunda7.worker import Camunda7ExternalTaskWorker
from hcns_agent.templates.service import build_default_template_processing_service

_PROCESS_DEFINITION_KEY = "hr_document_agent_mvp_v2"
_SUBMIT_TASK_KEY = "Submit"
_USER_REVIEW_TASK_KEY = "UserReview"
_SCALAR_TYPES = (str, int, float, bool, type(None))


class Camunda7ShadowPreflightGateway:
    """Small REST client for deployment and task APIs not used by the worker."""

    def __init__(self, config: Camunda7RestConfig) -> None:
        self._config = config
        self._base_url = config.base_url.rstrip("/") + "/"
        self._authorization_header = config.authorization_header
        self._timeout_seconds = config.timeout_seconds

    def deploy(self, bpmn_path: Path, dmn_path: Path) -> str:
        for path in (bpmn_path, dmn_path):
            if not path.is_file():
                raise ValueError(f"Camunda deployment asset is missing: {path.name}")
        response = self._multipart_post(
            "/deployment/create",
            fields={
                "deployment-name": "hcns-m5-shadow-preflight",
                "deployment-source": "hcns-local-shadow-preflight",
                "enable-duplicate-filtering": "true",
                "deploy-changed-only": "true",
            },
            files={bpmn_path.name: bpmn_path, dmn_path.name: dmn_path},
        )
        deployment_id = response.get("id") if isinstance(response, dict) else None
        if not isinstance(deployment_id, str) or not deployment_id:
            raise CamundaRestError("Camunda deployment response is invalid")
        return deployment_id

    def start_process(self, variables: Mapping[str, ProcessValue]) -> str:
        response = self._json_request(
            "POST",
            f"/process-definition/key/{_PROCESS_DEFINITION_KEY}/start",
            {"variables": _encode_variables(variables)},
        )
        instance_id = response.get("id") if isinstance(response, dict) else None
        if not isinstance(instance_id, str) or not instance_id:
            raise CamundaRestError("Camunda process start response is invalid")
        return instance_id

    def find_task(self, process_instance_id: str, definition_key: str) -> str | None:
        response = self._json_request(
            "GET",
            "/task?"
            + urlencode(
                {
                    "processInstanceId": _opaque_id(process_instance_id),
                    "taskDefinitionKey": definition_key,
                }
            ),
        )
        if not isinstance(response, list):
            raise CamundaRestError("Camunda task response is invalid")
        if not response:
            return None
        task_id = response[0].get("id") if isinstance(response[0], dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise CamundaRestError("Camunda task id is invalid")
        return task_id

    def claim_task(self, task_id: str, user_id: str) -> None:
        self._json_request(
            "POST",
            f"/task/{_opaque_id(task_id)}/claim",
            {"userId": user_id},
        )

    def complete_task(
        self,
        task_id: str,
        variables: Mapping[str, ProcessValue],
    ) -> None:
        self._json_request(
            "POST",
            f"/task/{_opaque_id(task_id)}/complete",
            {"variables": _encode_variables(variables)},
        )

    def process_finished(self, process_instance_id: str) -> bool:
        response = self._json_request(
            "GET",
            f"/history/process-instance/{_opaque_id(process_instance_id)}",
        )
        if not isinstance(response, dict):
            raise CamundaRestError("Camunda historic process response is invalid")
        return isinstance(response.get("endTime"), str)

    def history_variables(self, process_instance_id: str) -> Mapping[str, ProcessValue]:
        response = self._json_request(
            "GET",
            "/history/variable-instance?"
            + urlencode({"processInstanceId": _opaque_id(process_instance_id)}),
        )
        if not isinstance(response, list):
            raise CamundaRestError("Camunda historic variable response is invalid")
        variables: dict[str, ProcessValue] = {}
        for item in response:
            if not isinstance(item, dict):
                raise CamundaRestError("Camunda historic variable entry is invalid")
            name = item.get("name")
            value = item.get("value")
            if not isinstance(name, str) or not name:
                raise CamundaRestError("Camunda historic variable name is invalid")
            if not isinstance(value, _SCALAR_TYPES):
                raise CamundaRestError("Camunda historic variables must be scalar")
            variables[name] = value
        return variables

    def _json_request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return self._request(method, path, data=data, headers=headers)

    def _multipart_post(
        self,
        path: str,
        *,
        fields: Mapping[str, str],
        files: Mapping[str, Path],
    ) -> object:
        boundary = f"----hcns-{uuid.uuid4().hex}"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend(
                (
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    value.encode(),
                    b"\r\n",
                )
            )
        for name, source in files.items():
            chunks.extend(
                (
                    f"--{boundary}\r\n".encode(),
                    (
                        "Content-Disposition: form-data; "
                        f'name="{name}"; filename="{source.name}"\r\n'
                    ).encode(),
                    b"Content-Type: application/octet-stream\r\n\r\n",
                    source.read_bytes(),
                    b"\r\n",
                )
            )
        chunks.append(f"--{boundary}--\r\n".encode())
        return self._request(
            "POST",
            path,
            data=b"".join(chunks),
            headers={
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None,
        headers: Mapping[str, str],
    ) -> object:
        request_headers = dict(headers)
        if self._authorization_header:
            request_headers["Authorization"] = self._authorization_header
        request = Request(
            urljoin(self._base_url, path.lstrip("/")),
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                content = response.read()
        except HTTPError as error:
            raise CamundaRestError(f"Camunda REST returned HTTP {error.code}") from error
        except URLError as error:
            raise CamundaRestError("Camunda REST is unavailable") from error
        if not content:
            return {}
        try:
            return json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CamundaRestError("Camunda REST returned invalid JSON") from error


@dataclass(frozen=True, slots=True)
class ShadowPreflightCaseReport:
    case_id: str
    document_type: str
    reached_user_review: bool
    completed: bool
    duration_seconds: float
    auto_continue_observed: bool
    hris_simulated: bool
    notification_simulated: bool


@dataclass(frozen=True, slots=True)
class ShadowPreflightReport:
    deployment_completed: bool
    cases: tuple[ShadowPreflightCaseReport, ...]
    auto_continue_count: int
    raw_exposure_count: int
    duplicate_result_artifacts: int
    unreconciled_cases: int
    real_side_effect_count: int

    @property
    def passed(self) -> bool:
        return (
            self.deployment_completed
            and len(self.cases) == 2
            and all(case.reached_user_review and case.completed for case in self.cases)
            and all(case.duration_seconds < 60 for case in self.cases)
            and self.auto_continue_count == 0
            and self.raw_exposure_count == 0
            and self.duplicate_result_artifacts == 0
            and self.unreconciled_cases == 0
            and self.real_side_effect_count == 0
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "milestone": "M5-CAM-001A",
            "mode": "LOCAL_SYNTHETIC_SHADOW_PREFLIGHT",
            "passed": self.passed,
            "deploymentCompleted": self.deployment_completed,
            "caseCount": len(self.cases),
            "autoContinueCount": self.auto_continue_count,
            "rawExposureCount": self.raw_exposure_count,
            "duplicateResultArtifacts": self.duplicate_result_artifacts,
            "unreconciledCases": self.unreconciled_cases,
            "realSideEffectCount": self.real_side_effect_count,
            "cases": [asdict(case) for case in self.cases],
        }


def run_shadow_preflight(
    *,
    gateway: Camunda7ShadowPreflightGateway,
    private_root: Path,
    repository_root: Path,
    worker_id: str,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    timeout_seconds: float = 55.0,
) -> ShadowPreflightReport:
    """Execute two synthetic review-first cases against a local Camunda engine."""

    if timeout_seconds <= 0 or timeout_seconds >= 60:
        raise ValueError("timeout_seconds must be greater than 0 and below 60")
    root = private_root.resolve()
    if not root.is_absolute():
        raise ValueError("private_root must be absolute")
    run_root = root / "m5-shadow-preflight" / uuid.uuid4().hex
    run_root.mkdir(parents=True, exist_ok=False)
    bpmn = repository_root / "camunda" / "HR_DOCUMENT_AGENT_MVP_V2.bpmn"
    dmn = repository_root / "camunda" / "HR_DOCUMENT_QUALITY_ROUTING.dmn"
    gateway.deploy(bpmn, dmn)
    worker = _build_worker(gateway, worker_id, run_root)
    before_results = _result_count(run_root)
    completed_cases = tuple(
        _run_case(
            gateway,
            worker,
            run_root,
            case_id=case_id,
            document_type=document_type,
            lines=lines,
            clock=clock,
            sleep=sleep,
            timeout_seconds=timeout_seconds,
        )
        for case_id, document_type, lines in (
            ("M5-LEAVE-SYNTHETIC", "LEAVE_REQUEST", _leave_lines()),
            ("M5-OVERTIME-SYNTHETIC", "OVERTIME_REQUEST", _overtime_lines()),
        )
    )
    cases = tuple(result for result, _ in completed_cases)
    instance_ids = tuple(instance_id for _, instance_id in completed_cases)
    after_results = _result_count(run_root)
    expected_results = before_results + len(cases)
    all_variables = tuple(gateway.history_variables(instance_id) for instance_id in instance_ids)
    raw_exposure_count = sum(_raw_exposure_count(values) for values in all_variables)
    auto_continue_count = sum(
        1
        for values in all_variables
        if values.get("recommendedAction") == "AUTO_CONTINUE"
        or values.get("autoContinueEnabled") is True
    )
    unreconciled_cases = sum(
        1
        for case, instance_id, values in zip(cases, instance_ids, all_variables, strict=True)
        if not case.completed
        or not case.hris_simulated
        or not case.notification_simulated
        or not gateway.process_finished(instance_id)
        or values.get("hrisUpdateStatus") != "SIMULATED"
        or values.get("notificationStatus") != "SIMULATED"
    )
    real_side_effect_count = sum(
        1
        for values in all_variables
        if values.get("hrisUpdateStatus") not in {None, "SIMULATED"}
        or values.get("notificationStatus") not in {None, "SIMULATED"}
    )
    return ShadowPreflightReport(
        deployment_completed=True,
        cases=cases,
        auto_continue_count=auto_continue_count,
        raw_exposure_count=raw_exposure_count,
        duplicate_result_artifacts=max(0, after_results - expected_results),
        unreconciled_cases=unreconciled_cases,
        real_side_effect_count=real_side_effect_count,
    )


def build_local_shadow_gateway(
    *,
    base_url: str,
    worker_id: str,
) -> Camunda7ShadowPreflightGateway:
    """Build a localhost-only gateway; production endpoints are intentionally rejected."""

    if not base_url.startswith(("http://127.0.0.1", "http://localhost")):
        raise ValueError("Shadow preflight only supports a localhost Camunda REST URL")
    return Camunda7ShadowPreflightGateway(
        Camunda7RestConfig(base_url=base_url, worker_id=worker_id, timeout_seconds=45)
    )


def _build_worker(
    gateway: Camunda7ShadowPreflightGateway,
    worker_id: str,
    root: Path,
) -> Camunda7ExternalTaskWorker:
    config = Camunda7RestConfig(
        base_url=gateway._config.base_url,  # noqa: SLF001 - same adapter boundary
        worker_id=worker_id,
        timeout_seconds=45,
    )
    client = Camunda7ExternalTaskClient(
        UrllibCamundaRestTransport(config.base_url, timeout_seconds=config.timeout_seconds),
        worker_id=worker_id,
    )
    return build_m4_worker(
        client=client,
        pipeline=build_default_template_processing_service(),
        source_store=LocalSessionDocumentSourceStore(root),
        result_store=JsonFileTemplateResultStore(root / "camunda_m4"),
    )


def _run_case(
    gateway: Camunda7ShadowPreflightGateway,
    worker: Camunda7ExternalTaskWorker,
    root: Path,
    *,
    case_id: str,
    document_type: str,
    lines: list[str],
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    timeout_seconds: float,
) -> tuple[ShadowPreflightCaseReport, str]:
    source_reference = f"{case_id}-{uuid.uuid4().hex[:12]}"
    _write_source(root, source_reference, _docx_bytes(lines))
    start = clock()
    instance_id = gateway.start_process({"applicationId": case_id})
    submit_task = _wait_for_task(
        gateway, instance_id, _SUBMIT_TASK_KEY, worker, clock, sleep, timeout_seconds
    )
    gateway.claim_task(submit_task, "synthetic-submit-reviewer")
    gateway.complete_task(
        submit_task,
        {
            "applicationId": case_id,
            "documentReference": source_reference,
            "declaredDocumentType": document_type,
        },
    )
    user_task = _wait_for_task(
        gateway, instance_id, _USER_REVIEW_TASK_KEY, worker, clock, sleep, timeout_seconds
    )
    gateway.claim_task(user_task, "synthetic-user-reviewer")
    gateway.complete_task(user_task, {"userReviewDecision": "CONFIRMED"})
    _wait_for_finished(gateway, instance_id, worker, clock, sleep, timeout_seconds)
    values = gateway.history_variables(instance_id)
    duration = clock() - start
    report = ShadowPreflightCaseReport(
        case_id=case_id,
        document_type=document_type,
        reached_user_review=True,
        completed=gateway.process_finished(instance_id),
        duration_seconds=round(duration, 3),
        auto_continue_observed=(
            values.get("recommendedAction") == "AUTO_CONTINUE"
            or values.get("autoContinueEnabled") is True
        ),
        hris_simulated=values.get("hrisUpdateStatus") == "SIMULATED",
        notification_simulated=values.get("notificationStatus") == "SIMULATED",
    )
    return report, instance_id


def _wait_for_task(
    gateway: Camunda7ShadowPreflightGateway,
    instance_id: str,
    definition_key: str,
    worker: Camunda7ExternalTaskWorker,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    timeout_seconds: float,
) -> str:
    deadline = clock() + timeout_seconds
    while clock() < deadline:
        task_id = gateway.find_task(instance_id, definition_key)
        if task_id is not None:
            return task_id
        worker.run_once(max_tasks=1)
        sleep(0.05)
    raise TimeoutError(f"Timed out waiting for {definition_key}")


def _wait_for_finished(
    gateway: Camunda7ShadowPreflightGateway,
    instance_id: str,
    worker: Camunda7ExternalTaskWorker,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    timeout_seconds: float,
) -> None:
    deadline = clock() + timeout_seconds
    while clock() < deadline:
        if gateway.process_finished(instance_id):
            return
        worker.run_once(max_tasks=1)
        sleep(0.05)
    raise TimeoutError("Timed out waiting for process completion")


def _raw_exposure_count(values: Mapping[str, ProcessValue]) -> int:
    return sum(
        1
        for name, value in values.items()
        if name not in PROCESS_VARIABLE_WHITELIST or not isinstance(value, _SCALAR_TYPES)
    )


def _result_count(root: Path) -> int:
    directory = root / "camunda_m4" / "results"
    return len(tuple(directory.glob("*.json"))) if directory.is_dir() else 0


def _write_source(root: Path, reference: str, content: bytes) -> None:
    directory = root / "user_uploads" / "sessions" / reference / "input"
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "document.docx").write_bytes(content)


def _docx_bytes(lines: list[str]) -> bytes:
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


def _leave_lines() -> list[str]:
    return [
        "ĐƠN XIN NGHỈ PHÉP",
        "Kính gửi: - Ban Giám đốc CÔNG TY SYNTHETIC",
        "Tôi tên là: NHÂN VIÊN SYNTHETIC",
        "Chức vụ: Chuyên viên kiểm thử",
        "Bộ phận: Kiểm thử",
        "Địa chỉ: Địa chỉ synthetic",
        "Điện thoại: 0000000000",
        (
            "Nay tôi làm đơn này xin nghỉ trong thời gian 2 ngày, kể từ ngày "
            "01/06/2026 đến hết ngày 02/06/2026."
        ),
        "Lý do xin nghỉ phép: Lý do synthetic. Tôi dự kiến trở lại làm việc vào ngày 03/06/2026.",
        "Tôi đã bàn giao công việc cho: ĐỒNG NGHIỆP SYNTHETIC - Bộ phận: Kiểm thử.",
        "Các công việc được bàn giao: Công việc synthetic.",
        "Hà Nội, ngày 30 tháng 05 năm 2026",
    ]


def _overtime_lines() -> list[str]:
    return [
        "Hà Nội, ngày 31 tháng 05 năm 2026",
        "ĐƠN XIN TĂNG CA",
        "Căn cứ Hợp đồng lao động số HD-SYNTHETIC ký ngày 01/01/2026;",
        "Kính gửi: Ban Giám đốc CÔNG TY SYNTHETIC.",
        "Tôi là: NHÂN VIÊN SYNTHETIC - Chức vụ: Chuyên viên kiểm thử",
        (
            "Hiện nay, tôi đang thực hiện công việc tại vị trí Chuyên viên kiểm thử, "
            "thời gian làm việc 08:00-17:00. Do hoàn thiện kiểm thử synthetic, tôi "
            "đề nghị được làm thêm."
        ),
        (
            "Thời gian đề nghị: Từ ngày 01/06/2026 đến hết ngày 03/06/2026, tăng "
            "thêm 2 giờ mỗi ngày, từ 18 giờ 00 phút đến 20 giờ 00 phút; tổng thời "
            "gian dự kiến là 6 giờ."
        ),
        "Nội dung công việc: Hoàn thiện kiểm thử synthetic.",
    ]


def _encode_variables(
    variables: Mapping[str, ProcessValue],
) -> dict[str, object]:
    return {
        name: {"value": value, "type": _camunda_type(value)}
        for name, value in variables.items()
    }


def _camunda_type(value: ProcessValue) -> str:
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Long"
    if isinstance(value, float):
        return "Double"
    if value is None:
        return "Null"
    return "String"


def _opaque_id(value: str) -> str:
    if not value or "/" in value or "\\" in value:
        raise ValueError("Camunda identifier is invalid")
    return value
