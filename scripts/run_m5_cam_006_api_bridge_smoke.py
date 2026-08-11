"""Run a read-only localhost API to Phase15 Camunda bridge smoke test."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import sys
import tempfile
import threading
from collections.abc import Mapping
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from serve_dashboard_api import DashboardHandler, UserOCRService  # noqa: E402

from hcns_agent.adapters.camunda7.contract import (  # noqa: E402
    PROCESS_VARIABLE_WHITELIST,
    validate_process_variables,
)
from hcns_agent.adapters.camunda7.phase15_bridge import (  # noqa: E402
    project_phase15_business_json,
)
from hcns_agent.adapters.camunda7.shadow_preflight import (  # noqa: E402
    _synthetic_phase15_business_json,
)

_FIXTURES = (
    ("00000000-0000-4000-8000-000000000006", "LEAVE_REQUEST"),
    ("00000000-0000-4000-8000-000000000007", "OVERTIME_REQUEST"),
)
_SCALAR_TYPES = (str, int, float, bool, type(None))


def _seed_phase15_session(data_root: Path, case_id: str, document_type: str) -> Path:
    session_dir = data_root / "user_uploads" / "sessions" / case_id
    phase15_dir = session_dir / "phase15"
    phase15_dir.mkdir(parents=True, exist_ok=True)
    business = _synthetic_phase15_business_json(
        f"m5-cam-006-{case_id}-document",
        document_type,
    )
    (session_dir / "result.json").write_text(
        json.dumps({"sessionId": case_id, "status": "NEEDS_REVIEW"}),
        encoding="utf-8",
    )
    business_path = phase15_dir / "business.json"
    business_path.write_text(
        json.dumps(business, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return business_path


def _configure_handler(data_root: Path) -> None:
    DashboardHandler.data_root = data_root
    for name in (
        "benchmark_report",
        "benchmark_manifest",
        "cccd_heldout_root",
        "ocr_ho_shadow_root",
        "external_dataset_root",
        "external_dataset_inventory",
        "external_dataset_ground_truth",
        "external_dataset_data23_manifest",
        "external_dataset_data23_prediction_lock",
        "external_dataset_data23_ground_truth_lock",
        "external_dataset_typed_projection",
        "external_dataset_typed_approval",
        "external_dataset_typed_report",
        "external_dataset_predictions",
        "external_dataset_prediction_report",
        "external_dataset_prediction_marker",
        "external_dataset_predictions_data13",
        "external_dataset_prediction_report_data13",
        "external_dataset_prediction_marker_data13",
        "external_dataset_policy_v2_report",
        "external_dataset_policy_v2_marker",
        "m5_local_shadow_report",
    ):
        setattr(DashboardHandler, name, None)
    DashboardHandler.native_indexes = {}
    DashboardHandler.user_ocr = UserOCRService(data_root)
    DashboardHandler.template_processor = None  # type: ignore[assignment]


def _get_business_json(
    connection: http.client.HTTPConnection,
    case_id: str,
) -> tuple[int, dict[str, object]]:
    connection.request("GET", f"/user/phase15-business?id={case_id}")
    response = connection.getresponse()
    body = response.read()
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise AssertionError("localhost Phase15 response must be an object")
    return response.status, payload


def _bridge_projection(payload: Mapping[str, object], case_id: str, document_type: str) -> None:
    projection = project_phase15_business_json(
        payload,
        application_id=f"m5-cam-006-{case_id}-application",
        document_reference=f"m5-cam-006-{case_id}-document",
        declared_document_type=document_type,
        result_reference=f"m5-cam-006-{case_id}-result",
    )
    variables = projection.variables
    validate_process_variables(variables)
    if set(variables) - PROCESS_VARIABLE_WHITELIST:
        raise AssertionError("Phase15 bridge projection escaped the whitelist")
    if any(not isinstance(value, _SCALAR_TYPES) for value in variables.values()):
        raise AssertionError("Phase15 bridge projection contains a non-scalar")
    if variables.get("reviewRequired") is not True:
        raise AssertionError("localhost smoke fixture must remain manual review")
    if variables.get("autoContinueEnabled") is not False:
        raise AssertionError("localhost smoke fixture enabled auto-continue")


def run_smoke() -> dict[str, object]:
    """Read two synthetic Phase15 files over loopback and project them safely."""

    with tempfile.TemporaryDirectory(prefix="m5-cam-006-") as temporary_root:
        data_root = Path(temporary_root)
        source_paths = {
            case_id: _seed_phase15_session(data_root, case_id, document_type)
            for case_id, document_type in _FIXTURES
        }
        _configure_handler(data_root)
        server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        statuses: list[int] = []
        source_mutations = 0
        try:
            connection = http.client.HTTPConnection(
                "127.0.0.1",
                server.server_port,
                timeout=10,
            )
            for case_id, document_type in _FIXTURES:
                source_path = source_paths[case_id]
                before = hashlib.sha256(source_path.read_bytes()).digest()
                status, payload = _get_business_json(connection, case_id)
                statuses.append(status)
                _bridge_projection(payload, case_id, document_type)
                after = hashlib.sha256(source_path.read_bytes()).digest()
                source_mutations += before != after
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    passed = (
        statuses == [200, 200]
        and source_mutations == 0
    )
    return {
        "milestone": "M5-CAM-006",
        "evaluationKind": "localhost-api-phase15-bridge-read-only-smoke",
        "mode": "LOCAL_SYNTHETIC_READ_ONLY",
        "passed": passed,
        "fixtureCount": len(_FIXTURES),
        "getRequestCount": len(_FIXTURES),
        "postRequestCount": 0,
        "httpMethodPolicy": "GET_ONLY",
        "phase15BridgeProjectionCount": len(_FIXTURES),
        "manualReviewCount": len(_FIXTURES),
        "autoContinueCount": 0,
        "scalarOnly": True,
        "opaqueReferenceOnly": True,
        "schemaWhitelistErrorCount": 0,
        "nonScalarValueCount": 0,
        "sourceMutationCount": source_mutations,
        "camundaProcessStartAttempts": 0,
        "hrisSideEffectCount": 0,
        "notificationSideEffectCount": 0,
        "groundTruthUsed": False,
        "evaluateOnceArtifactTouched": False,
        "realCohortOpened": False,
        "containsRawFieldValues": False,
        "promotionAllowed": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the M5-CAM-006 localhost API/Phase15 bridge smoke test."
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("--output already exists; reports are create-only")
    if ROOT in output.parents:
        raise ValueError("aggregate report must stay outside the repository")
    report = run_smoke()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
