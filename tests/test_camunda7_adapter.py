from collections.abc import Mapping
from dataclasses import dataclass
from unittest import TestCase

from hcns_agent.adapters.camunda7.client import (
    Camunda7ExternalTaskClient,
    Camunda7RestConfig,
    CamundaRestError,
    ExternalTask,
    TopicSubscription,
)
from hcns_agent.adapters.camunda7.contract import ProcessValue, ProcessVariables
from hcns_agent.adapters.camunda7.handlers import (
    ALL_EXTERNAL_TASK_TOPICS,
    DOCUMENT_STAGE_TOPICS,
    MockSideEffectHandler,
    ReferenceStageHandler,
    ReuploadControlHandler,
    build_m4_shadow_handlers,
)
from hcns_agent.adapters.camunda7.worker import (
    Camunda7ExternalTaskWorker,
    CamundaBusinessError,
    CamundaTechnicalError,
)


class _RecordingTransport:
    def __init__(self, response: object = None) -> None:
        self.response = [] if response is None else response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, path: str, payload: dict[str, object]) -> object:
        self.calls.append((path, payload))
        return self.response


class Camunda7ClientTests(TestCase):
    def test_rest_config_reads_endpoint_worker_and_bearer_from_environment(self) -> None:
        config = Camunda7RestConfig.from_environment(
            {
                "CAMUNDA_REST_URL": "http://127.0.0.1:8080/engine-rest",
                "CAMUNDA_WORKER_ID": "worker-synthetic",
                "CAMUNDA_BEARER_TOKEN": "synthetic-token",
            }
        )

        self.assertEqual("http://127.0.0.1:8080/engine-rest", config.base_url)
        self.assertEqual("worker-synthetic", config.worker_id)
        self.assertEqual("Bearer synthetic-token", config.authorization_header)

        with self.assertRaises(ValueError):
            Camunda7RestConfig.from_environment({})

    def test_fetch_complete_failure_bpmn_error_and_extend_lock_payloads(self) -> None:
        transport = _RecordingTransport(
            [
                {
                    "id": "TASK-1",
                    "topicName": "document_validate_file",
                    "retries": 3,
                    "variables": {
                        "documentReference": {
                            "value": "object://synthetic/document",
                            "type": "String",
                        }
                    },
                }
            ]
        )
        client = Camunda7ExternalTaskClient(transport, worker_id="worker-synthetic")

        tasks = client.fetch_and_lock(
            (TopicSubscription("document_validate_file", 12_000),)
        )
        client.complete(
            "TASK-1",
            {"fileValidationStatus": "VALID", "reviewRequired": False},
        )
        client.handle_failure(
            "TASK-1",
            error_message="Synthetic technical failure",
            retries=2,
            retry_timeout_ms=5000,
            error_details="SyntheticError",
        )
        client.handle_bpmn_error(
            "TASK-1",
            error_code="DOCUMENT_INPUT_INVALID",
            error_message="Synthetic input invalid",
            variables={"errorCode": "DOCUMENT_INPUT_INVALID"},
        )
        client.extend_lock("TASK-1", 30_000)

        self.assertEqual("TASK-1", tasks[0].task_id)
        self.assertEqual("object://synthetic/document", tasks[0].variables["documentReference"])
        self.assertEqual("/external-task/fetchAndLock", transport.calls[0][0])
        fetch_payload = transport.calls[0][1]
        self.assertEqual("worker-synthetic", fetch_payload["workerId"])
        self.assertEqual("/external-task/TASK-1/complete", transport.calls[1][0])
        complete_variables = transport.calls[1][1]["variables"]
        self.assertEqual(
            {"value": False, "type": "Boolean"},
            complete_variables["reviewRequired"],  # type: ignore[index]
        )
        self.assertEqual("/external-task/TASK-1/failure", transport.calls[2][0])
        self.assertEqual("/external-task/TASK-1/bpmnError", transport.calls[3][0])
        self.assertEqual("/external-task/TASK-1/extendLock", transport.calls[4][0])

    def test_fetch_rejects_non_list_response_and_structured_variables(self) -> None:
        client = Camunda7ExternalTaskClient(_RecordingTransport({}), worker_id="worker")
        with self.assertRaises(CamundaRestError):
            client.fetch_and_lock((TopicSubscription("document_validate_file"),))

        client = Camunda7ExternalTaskClient(
            _RecordingTransport(
                [
                    {
                        "id": "TASK",
                        "topicName": "document_validate_file",
                        "variables": {"documentReference": {"value": {"raw": "forbidden"}}},
                    }
                ]
            ),
            worker_id="worker",
        )
        with self.assertRaises(CamundaRestError):
            client.fetch_and_lock((TopicSubscription("document_validate_file"),))


class _FakeClient:
    def __init__(self, task: ExternalTask) -> None:
        self.task = task
        self.completed: list[ProcessVariables] = []
        self.failures: list[dict[str, object]] = []
        self.business_errors: list[dict[str, object]] = []

    def fetch_and_lock(
        self,
        subscriptions: tuple[TopicSubscription, ...],
        *,
        max_tasks: int = 1,
        async_response_timeout_ms: int = 10_000,
    ) -> tuple[ExternalTask, ...]:
        return (self.task,)

    def complete(self, task_id: str, variables: ProcessVariables) -> None:
        self.completed.append(variables)

    def handle_failure(
        self,
        task_id: str,
        *,
        error_message: str,
        retries: int,
        retry_timeout_ms: int,
        error_details: str | None = None,
    ) -> None:
        self.failures.append(
            {
                "message": error_message,
                "retries": retries,
                "timeout": retry_timeout_ms,
                "details": error_details,
            }
        )

    def handle_bpmn_error(
        self,
        task_id: str,
        *,
        error_code: str,
        error_message: str,
        variables: ProcessVariables | None = None,
    ) -> None:
        self.business_errors.append(
            {
                "code": error_code,
                "message": error_message,
                "variables": variables or {},
            }
        )

    def extend_lock(self, task_id: str, new_duration_ms: int) -> None:
        pass


@dataclass
class _Handler:
    topic_name: str
    result: ProcessVariables | Exception

    def handle(self, variables: Mapping[str, ProcessValue]) -> ProcessVariables:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Camunda7WorkerTests(TestCase):
    @staticmethod
    def _task(topic: str = "document_validate_file", retries: int | None = 3) -> ExternalTask:
        return ExternalTask(
            task_id="TASK-SYNTHETIC",
            topic_name=topic,
            retries=retries,
            variables={
                "documentReference": "object://synthetic/document",
                "idempotencyKey": "IDEMPOTENT-SYNTHETIC",
            },
        )

    def test_worker_completes_successful_task(self) -> None:
        client = _FakeClient(self._task())
        worker = Camunda7ExternalTaskWorker(
            client,
            (
                _Handler(
                    "document_validate_file",
                    {"fileValidationStatus": "VALID"},
                ),
            ),
        )

        self.assertEqual(1, worker.run_once())
        self.assertEqual([{"fileValidationStatus": "VALID"}], client.completed)

    def test_worker_reports_business_error_without_retry(self) -> None:
        client = _FakeClient(self._task())
        worker = Camunda7ExternalTaskWorker(
            client,
            (
                _Handler(
                    "document_validate_file",
                    CamundaBusinessError(
                        "DOCUMENT_INPUT_INVALID",
                        "Synthetic input invalid",
                        variables={"errorCode": "DOCUMENT_INPUT_INVALID"},
                    ),
                ),
            ),
        )

        worker.run_once()

        self.assertEqual("DOCUMENT_INPUT_INVALID", client.business_errors[0]["code"])
        self.assertFalse(client.failures)

    def test_worker_decrements_retry_and_redacts_unexpected_error_details(self) -> None:
        client = _FakeClient(self._task(retries=2))
        worker = Camunda7ExternalTaskWorker(
            client,
            (
                _Handler(
                    "document_validate_file",
                    ValueError("raw synthetic value must not leak"),
                ),
            ),
        )

        worker.run_once()

        self.assertEqual(1, client.failures[0]["retries"])
        self.assertEqual("Unexpected external-task worker failure", client.failures[0]["message"])
        self.assertEqual("ValueError", client.failures[0]["details"])

    def test_worker_honors_typed_technical_retry_timeout(self) -> None:
        client = _FakeClient(self._task())
        worker = Camunda7ExternalTaskWorker(
            client,
            (
                _Handler(
                    "document_validate_file",
                    CamundaTechnicalError("Model temporarily unavailable", retry_timeout_ms=9000),
                ),
            ),
        )

        worker.run_once()

        self.assertEqual(9000, client.failures[0]["timeout"])

    def test_reference_reupload_and_mock_side_effect_handlers_are_safe(self) -> None:
        stage = ReferenceStageHandler(
            topic_name="document_validate_file",
            required_variables=frozenset({"documentReference"}),
            operation=lambda _: {"fileValidationStatus": "VALID"},
        )
        self.assertEqual(
            {"fileValidationStatus": "VALID"},
            stage.handle({"documentReference": "object://synthetic/document"}),
        )
        with self.assertRaises(CamundaBusinessError):
            stage.handle({})

        reupload = ReuploadControlHandler()
        first = reupload.handle(
            {"reuploadCount": 1, "maxReuploadAttempts": 3, "caseVersion": 4}
        )
        replay = reupload.handle(
            {"reuploadCount": 1, "maxReuploadAttempts": 3, "caseVersion": 4}
        )
        self.assertEqual(first, replay)
        self.assertEqual(2, first["reuploadCount"])
        self.assertEqual(5, first["caseVersion"])

        side_effect = MockSideEffectHandler(
            "hris_update_employee_record",
            "hrisUpdateStatus",
        )
        self.assertEqual(
            {"hrisUpdateStatus": "SIMULATED"},
            side_effect.handle({"idempotencyKey": "IDEMPOTENT-SYNTHETIC"}),
        )

    def test_shadow_handler_builder_covers_every_bpmn_topic(self) -> None:
        operations = {
            topic: (lambda _: {})
            for topic in DOCUMENT_STAGE_TOPICS
        }

        handlers = build_m4_shadow_handlers(operations, lambda _: {})

        self.assertEqual(
            set(ALL_EXTERNAL_TASK_TOPICS),
            {handler.topic_name for handler in handlers},
        )
        with self.assertRaises(ValueError):
            build_m4_shadow_handlers({}, lambda _: {})

    def test_shadow_extract_handler_enforces_m4_closed_set_before_operation(self) -> None:
        extraction_calls: list[Mapping[str, ProcessValue]] = []

        def extract(variables: Mapping[str, ProcessValue]) -> ProcessVariables:
            extraction_calls.append(variables)
            return {"extractionStatus": "SUCCESS"}

        operations = {topic: (lambda _: {}) for topic in DOCUMENT_STAGE_TOPICS}
        operations["document_extract"] = extract
        extract_handler = next(
            handler
            for handler in build_m4_shadow_handlers(operations, lambda _: {})
            if handler.topic_name == "document_extract"
        )
        base_variables: ProcessVariables = {
            "resultReference": "object://synthetic/result",
            "idempotencyKey": "IDEMPOTENT-SYNTHETIC",
        }

        for document_type in ("LEAVE_REQUEST", "OVERTIME_REQUEST"):
            with self.subTest(document_type=document_type):
                self.assertEqual(
                    {"extractionStatus": "SUCCESS"},
                    extract_handler.handle(
                        {
                            **base_variables,
                            "workflowDocumentType": document_type,
                        }
                    ),
                )

        with self.assertRaises(CamundaBusinessError) as raised:
            extract_handler.handle(
                {
                    **base_variables,
                    "workflowDocumentType": "TIMESHEET",
                }
            )

        self.assertEqual("DOCUMENT_INPUT_INVALID", raised.exception.error_code)
        self.assertEqual(2, len(extraction_calls))
