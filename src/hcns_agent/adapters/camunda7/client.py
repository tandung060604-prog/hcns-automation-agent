"""Small Camunda 7 External Task REST client with an injectable transport."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from hcns_agent.adapters.camunda7.contract import (
    PROCESS_VARIABLE_WHITELIST,
    ProcessValue,
    ProcessVariables,
    validate_process_variables,
)


class CamundaRestError(RuntimeError):
    """Camunda REST communication or response contract failure."""


@dataclass(frozen=True, slots=True)
class Camunda7RestConfig:
    base_url: str
    worker_id: str
    authorization_header: str | None = None
    timeout_seconds: float = 30.0

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> Camunda7RestConfig:
        values = os.environ if environment is None else environment
        base_url = values.get("CAMUNDA_REST_URL", "").strip()
        worker_id = values.get("CAMUNDA_WORKER_ID", "").strip()
        if not base_url or not worker_id:
            raise ValueError("CAMUNDA_REST_URL and CAMUNDA_WORKER_ID are required")
        bearer_token = values.get("CAMUNDA_BEARER_TOKEN", "").strip()
        authorization = f"Bearer {bearer_token}" if bearer_token else None
        return cls(
            base_url=base_url,
            worker_id=worker_id,
            authorization_header=authorization,
        )


class CamundaRestTransport(Protocol):
    def post(self, path: str, payload: dict[str, object]) -> object:
        """POST JSON to the configured Camunda REST base URL."""


class UrllibCamundaRestTransport:
    def __init__(
        self,
        base_url: str,
        *,
        authorization_header: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("Camunda REST base URL must use HTTP or HTTPS")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._base_url = base_url.rstrip("/") + "/"
        self._authorization_header = authorization_header
        self._timeout_seconds = timeout_seconds

    def post(self, path: str, payload: dict[str, object]) -> object:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._authorization_header:
            headers["Authorization"] = self._authorization_header
        request = Request(
            urljoin(self._base_url, path.lstrip("/")),
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
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
            return cast(object, json.loads(content.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CamundaRestError("Camunda REST returned invalid JSON") from error


@dataclass(frozen=True, slots=True)
class TopicSubscription:
    topic_name: str
    lock_duration_ms: int = 60_000

    def __post_init__(self) -> None:
        if not self.topic_name.strip():
            raise ValueError("topic_name must not be empty")
        if self.lock_duration_ms <= 0:
            raise ValueError("lock_duration_ms must be positive")


@dataclass(frozen=True, slots=True)
class ExternalTask:
    task_id: str
    topic_name: str
    retries: int | None
    variables: ProcessVariables


class CamundaExternalTaskClient(Protocol):
    def fetch_and_lock(
        self,
        subscriptions: tuple[TopicSubscription, ...],
        *,
        max_tasks: int = 1,
        async_response_timeout_ms: int = 10_000,
    ) -> tuple[ExternalTask, ...]:
        """Fetch and lock external tasks."""

    def complete(self, task_id: str, variables: ProcessVariables) -> None:
        """Complete a task with sanitized scalar variables."""

    def handle_failure(
        self,
        task_id: str,
        *,
        error_message: str,
        retries: int,
        retry_timeout_ms: int,
        error_details: str | None = None,
    ) -> None:
        """Report a technical failure."""

    def handle_bpmn_error(
        self,
        task_id: str,
        *,
        error_code: str,
        error_message: str,
        variables: ProcessVariables | None = None,
    ) -> None:
        """Report a business BPMN error."""

    def extend_lock(self, task_id: str, new_duration_ms: int) -> None:
        """Extend an active external-task lock."""


class Camunda7ExternalTaskClient:
    def __init__(self, transport: CamundaRestTransport, *, worker_id: str) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        self._transport = transport
        self._worker_id = worker_id

    @classmethod
    def from_config(cls, config: Camunda7RestConfig) -> Camunda7ExternalTaskClient:
        return cls(
            UrllibCamundaRestTransport(
                config.base_url,
                authorization_header=config.authorization_header,
                timeout_seconds=config.timeout_seconds,
            ),
            worker_id=config.worker_id,
        )

    def fetch_and_lock(
        self,
        subscriptions: tuple[TopicSubscription, ...],
        *,
        max_tasks: int = 1,
        async_response_timeout_ms: int = 10_000,
    ) -> tuple[ExternalTask, ...]:
        if not subscriptions:
            raise ValueError("At least one topic subscription is required")
        if max_tasks <= 0:
            raise ValueError("max_tasks must be positive")
        payload: dict[str, object] = {
            "workerId": self._worker_id,
            "maxTasks": max_tasks,
            "usePriority": True,
            "asyncResponseTimeout": async_response_timeout_ms,
            "topics": [
                {
                    "topicName": item.topic_name,
                    "lockDuration": item.lock_duration_ms,
                    "variables": sorted(PROCESS_VARIABLE_WHITELIST),
                }
                for item in subscriptions
            ],
        }
        response = self._transport.post("/external-task/fetchAndLock", payload)
        if not isinstance(response, list):
            raise CamundaRestError("fetchAndLock response must be a list")
        return tuple(_decode_external_task(item) for item in response)

    def complete(self, task_id: str, variables: ProcessVariables) -> None:
        validate_process_variables(variables)
        self._transport.post(
            f"/external-task/{_task_id(task_id)}/complete",
            {
                "workerId": self._worker_id,
                "variables": _encode_variables(variables),
            },
        )

    def handle_failure(
        self,
        task_id: str,
        *,
        error_message: str,
        retries: int,
        retry_timeout_ms: int,
        error_details: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "workerId": self._worker_id,
            "errorMessage": error_message[:1000],
            "retries": max(0, retries),
            "retryTimeout": max(0, retry_timeout_ms),
        }
        if error_details:
            payload["errorDetails"] = error_details[:4000]
        self._transport.post(f"/external-task/{_task_id(task_id)}/failure", payload)

    def handle_bpmn_error(
        self,
        task_id: str,
        *,
        error_code: str,
        error_message: str,
        variables: ProcessVariables | None = None,
    ) -> None:
        safe_variables = variables or {}
        validate_process_variables(safe_variables)
        self._transport.post(
            f"/external-task/{_task_id(task_id)}/bpmnError",
            {
                "workerId": self._worker_id,
                "errorCode": error_code,
                "errorMessage": error_message[:1000],
                "variables": _encode_variables(safe_variables),
            },
        )

    def extend_lock(self, task_id: str, new_duration_ms: int) -> None:
        if new_duration_ms <= 0:
            raise ValueError("new_duration_ms must be positive")
        self._transport.post(
            f"/external-task/{_task_id(task_id)}/extendLock",
            {
                "workerId": self._worker_id,
                "newDuration": new_duration_ms,
            },
        )


def _decode_external_task(raw: object) -> ExternalTask:
    if not isinstance(raw, dict):
        raise CamundaRestError("External task entry must be an object")
    task_id = raw.get("id")
    topic_name = raw.get("topicName")
    retries = raw.get("retries")
    encoded_variables = raw.get("variables", {})
    if not isinstance(task_id, str) or not task_id:
        raise CamundaRestError("External task id is missing")
    if not isinstance(topic_name, str) or not topic_name:
        raise CamundaRestError("External task topicName is missing")
    if retries is not None and not isinstance(retries, int):
        raise CamundaRestError("External task retries must be an integer")
    if not isinstance(encoded_variables, dict):
        raise CamundaRestError("External task variables must be an object")
    variables: ProcessVariables = {}
    for raw_name, encoded in encoded_variables.items():
        if not isinstance(raw_name, str) or not isinstance(encoded, dict):
            raise CamundaRestError("External task variable encoding is invalid")
        value = encoded.get("value")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise CamundaRestError("External task variables must be scalar")
        variables[raw_name] = value
    validate_process_variables(variables)
    return ExternalTask(
        task_id=task_id,
        topic_name=topic_name,
        retries=retries,
        variables=variables,
    )


def _encode_variables(variables: ProcessVariables) -> dict[str, object]:
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


def _task_id(task_id: str) -> str:
    if not task_id or "/" in task_id or "\\" in task_id:
        raise ValueError("External task id is invalid")
    return task_id
