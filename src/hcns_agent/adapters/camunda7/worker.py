"""Single-poll Camunda 7 worker runtime; Camunda retains all process state."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from hcns_agent.adapters.camunda7.client import (
    CamundaExternalTaskClient,
    CamundaRestError,
    ExternalTask,
    TopicSubscription,
)
from hcns_agent.adapters.camunda7.contract import (
    ProcessValue,
    ProcessVariables,
    validate_process_variables,
)


class CamundaBusinessError(RuntimeError):
    def __init__(
        self,
        error_code: str,
        public_message: str,
        *,
        variables: ProcessVariables | None = None,
    ) -> None:
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message
        self.variables = variables or {}


class CamundaTechnicalError(RuntimeError):
    def __init__(
        self,
        public_message: str,
        *,
        retry_timeout_ms: int = 5_000,
    ) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.retry_timeout_ms = retry_timeout_ms


class ExternalTaskHandler(Protocol):
    @property
    def topic_name(self) -> str:
        """Camunda external-task topic handled by this adapter."""

    def handle(self, variables: Mapping[str, ProcessValue]) -> ProcessVariables:
        """Execute one bounded task and return sanitized variables."""


@dataclass(frozen=True, slots=True)
class LockExtensionPolicy:
    topic_names: frozenset[str]
    new_duration_ms: int

    def __post_init__(self) -> None:
        if not self.topic_names:
            raise ValueError("Lock-extension topics must not be empty")
        if any(not topic.strip() for topic in self.topic_names):
            raise ValueError("Lock-extension topic names must not be empty")
        if self.new_duration_ms <= 0:
            raise ValueError("Lock-extension duration must be positive")

    def applies_to(self, topic_name: str) -> bool:
        return topic_name in self.topic_names


@dataclass(frozen=True, slots=True)
class ReconnectBackoffPolicy:
    """Bound retry delays for a local worker when Camunda is temporarily offline."""

    initial_delay_seconds: float = 1.0
    maximum_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.initial_delay_seconds <= 0:
            raise ValueError("initial_delay_seconds must be positive")
        if self.maximum_delay_seconds < self.initial_delay_seconds:
            raise ValueError(
                "maximum_delay_seconds must be at least initial_delay_seconds"
            )


class Camunda7ExternalTaskWorker:
    def __init__(
        self,
        client: CamundaExternalTaskClient,
        handlers: tuple[ExternalTaskHandler, ...],
        *,
        default_retries: int = 3,
        retry_timeout_ms: int = 5_000,
        lock_extension_policy: LockExtensionPolicy | None = None,
    ) -> None:
        if default_retries <= 0:
            raise ValueError("default_retries must be positive")
        if retry_timeout_ms < 0:
            raise ValueError("retry_timeout_ms must not be negative")
        self._client = client
        self._handlers = _handler_registry(handlers)
        self._default_retries = default_retries
        self._retry_timeout_ms = retry_timeout_ms
        self._lock_extension_policy = lock_extension_policy

    def run_once(self, *, max_tasks: int = 1) -> int:
        subscriptions = tuple(
            TopicSubscription(topic_name) for topic_name in sorted(self._handlers)
        )
        tasks = self._client.fetch_and_lock(subscriptions, max_tasks=max_tasks)
        for task in tasks:
            self._handle_task(task)
        return len(tasks)

    def run_forever(
        self,
        *,
        max_polls: int | None = None,
        backoff_policy: ReconnectBackoffPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> int:
        """Poll indefinitely, recovering from unavailable Camunda REST endpoints.

        ``max_polls`` exists for deterministic local preflight and unit tests.  The
        CLI omits it and therefore keeps polling until interrupted.
        """

        if max_polls is not None and max_polls <= 0:
            raise ValueError("max_polls must be positive when provided")
        policy = backoff_policy or ReconnectBackoffPolicy()
        completed = 0
        poll_count = 0
        delay = policy.initial_delay_seconds
        while max_polls is None or poll_count < max_polls:
            poll_count += 1
            try:
                completed += self.run_once(max_tasks=1)
            except CamundaRestError:
                sleep(delay)
                delay = min(delay * 2, policy.maximum_delay_seconds)
            else:
                delay = policy.initial_delay_seconds
        return completed

    def _handle_task(self, task: ExternalTask) -> None:
        handler = self._handlers.get(task.topic_name)
        if handler is None:
            self._report_failure(task, "No handler is registered for this topic")
            return
        try:
            if (
                self._lock_extension_policy is not None
                and self._lock_extension_policy.applies_to(task.topic_name)
            ):
                self._client.extend_lock(
                    task.task_id,
                    self._lock_extension_policy.new_duration_ms,
                )
            result = handler.handle(task.variables)
            validate_process_variables(result)
            self._client.complete(task.task_id, result)
        except CamundaBusinessError as error:
            validate_process_variables(error.variables)
            self._client.handle_bpmn_error(
                task.task_id,
                error_code=error.error_code,
                error_message=error.public_message,
                variables=error.variables,
            )
        except CamundaTechnicalError as error:
            self._report_failure(
                task,
                error.public_message,
                retry_timeout_ms=error.retry_timeout_ms,
            )
        except Exception as error:
            self._report_failure(
                task,
                "Unexpected external-task worker failure",
                error_details=type(error).__name__,
            )

    def _report_failure(
        self,
        task: ExternalTask,
        public_message: str,
        *,
        retry_timeout_ms: int | None = None,
        error_details: str | None = None,
    ) -> None:
        current_retries = task.retries
        if current_retries is None:
            current_retries = self._default_retries
        self._client.handle_failure(
            task.task_id,
            error_message=public_message,
            retries=max(0, current_retries - 1),
            retry_timeout_ms=(
                self._retry_timeout_ms
                if retry_timeout_ms is None
                else max(0, retry_timeout_ms)
            ),
            error_details=error_details,
        )


def _handler_registry(
    handlers: tuple[ExternalTaskHandler, ...],
) -> dict[str, ExternalTaskHandler]:
    if not handlers:
        raise ValueError("At least one external-task handler is required")
    registry: dict[str, ExternalTaskHandler] = {}
    for handler in handlers:
        if not handler.topic_name.strip():
            raise ValueError("External-task handler topic must not be empty")
        if handler.topic_name in registry:
            raise ValueError(f"Duplicate external-task handler: {handler.topic_name}")
        registry[handler.topic_name] = handler
    return registry
