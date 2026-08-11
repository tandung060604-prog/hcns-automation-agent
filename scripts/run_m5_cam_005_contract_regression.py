"""Run the M5-CAM-005 scalar/opaque handoff contract regression."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcns_agent.adapters.camunda7.contract import (  # noqa: E402
    PROCESS_VARIABLE_WHITELIST,
    validate_process_variables,
)
from hcns_agent.adapters.camunda7.phase15_bridge import (  # noqa: E402
    Phase15CamundaProjectionError,
    project_phase15_business_json,
)
from hcns_agent.adapters.camunda7.shadow_preflight import (  # noqa: E402
    _synthetic_phase15_business_json,
)

_SCALAR_TYPES = (str, int, float, bool, type(None))
_OPAQUE_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_OPAQUE_REFERENCE_NAMES = (
    "applicationId",
    "documentReference",
    "resultReference",
)
_FORBIDDEN_CAMUNDA_NAMES = (
    "fields",
    "fieldValues",
    "ocrText",
    "ocrPayload",
    "recognizedText",
    "documentSourcePath",
    "rawPayload",
)


def _api_fixture(case_id: str, document_type: str) -> dict[str, object]:
    document_reference = f"m5-cam-005-{case_id}-document"
    return {
        "applicationId": f"m5-cam-005-{case_id}-application",
        "documentReference": document_reference,
        "declaredDocumentType": document_type,
        "resultReference": f"m5-cam-005-{case_id}-result",
        "businessJson": _synthetic_phase15_business_json(
            document_reference,
            document_type,
        ),
    }


def _project_api_fixture(payload: Mapping[str, object]) -> dict[str, object]:
    business_json = payload["businessJson"]
    if not isinstance(business_json, Mapping):
        raise AssertionError("synthetic API fixture must contain Business JSON")
    projection = project_phase15_business_json(
        business_json,
        application_id=_string(payload, "applicationId"),
        document_reference=_string(payload, "documentReference"),
        declared_document_type=_string(payload, "declaredDocumentType"),
        result_reference=_string(payload, "resultReference"),
    )
    variables = projection.variables
    validate_process_variables(variables)
    if set(variables) - PROCESS_VARIABLE_WHITELIST:
        raise AssertionError("projection escaped the Camunda variable whitelist")
    if any(not isinstance(value, _SCALAR_TYPES) for value in variables.values()):
        raise AssertionError("projection contains a non-scalar value")
    if variables.get("reviewRequired") is not True:
        raise AssertionError("synthetic handoff must remain manual review")
    if variables.get("qualityStatus") != "REVIEW_REQUIRED":
        raise AssertionError("synthetic handoff must retain review-required quality")
    if variables.get("autoContinueEnabled") is not False:
        raise AssertionError("auto-continue must remain disabled")
    references = {
        name: variables.get(name)
        for name in _OPAQUE_REFERENCE_NAMES
    }
    references["businessKey"] = projection.business_key
    if any(
        not isinstance(value, str) or _OPAQUE_REFERENCE.fullmatch(value) is None
        for value in references.values()
    ):
        raise AssertionError("projection contains a non-opaque reference")
    return {
        "businessKey": projection.business_key,
        "variables": variables,
    }


def _string(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
        raise AssertionError(f"synthetic API fixture {name} must be a string")
    return value


def _forbidden_payload_rejections() -> int:
    rejected = 0
    for name in _FORBIDDEN_CAMUNDA_NAMES:
        payload = _api_fixture("negative", "LEAVE_REQUEST")
        business_json = payload["businessJson"]
        assert isinstance(business_json, dict)
        variables = business_json["camunda"]["variables"]
        assert isinstance(variables, dict)
        variables[name] = (
            r"C:\private\synthetic.docx"
            if "Path" in name or "File" in name
            else "synthetic-raw-payload"
        )
        try:
            _project_api_fixture(payload)
        except Phase15CamundaProjectionError:
            rejected += 1
    return rejected


def run_regression() -> dict[str, object]:
    """Run two synthetic API-to-bridge checks without starting Camunda."""

    fixtures = (
        _api_fixture("leave", "LEAVE_REQUEST"),
        _api_fixture("overtime", "OVERTIME_REQUEST"),
    )
    first_pass = [_project_api_fixture(fixture) for fixture in fixtures]
    replay_pass = [_project_api_fixture(deepcopy(fixture)) for fixture in fixtures]
    idempotency_mismatches = sum(
        first != replay
        for first, replay in zip(first_pass, replay_pass, strict=True)
    )
    rejected_count = _forbidden_payload_rejections()
    fixture_types = [
        _string(fixture, "declaredDocumentType")
        for fixture in fixtures
    ]
    passed = (
        len(first_pass) == 2
        and idempotency_mismatches == 0
        and rejected_count == len(_FORBIDDEN_CAMUNDA_NAMES)
        and all(
            projection["variables"].get("reviewRequired") is True
            and projection["variables"].get("autoContinueEnabled") is False
            for projection in first_pass
        )
    )
    return {
        "milestone": "M5-CAM-005",
        "evaluationKind": "scalar-opaque-handoff-contract-regression",
        "mode": "LOCAL_SYNTHETIC_CONTRACT_ONLY",
        "passed": passed,
        "fixtureCount": len(first_pass),
        "fixtureTypes": fixture_types,
        "scalarOnly": True,
        "opaqueReferenceOnly": True,
        "manualReviewCount": len(first_pass),
        "autoContinueCount": 0,
        "schemaWhitelistErrorCount": 0,
        "nonScalarValueCount": 0,
        "forbiddenPayloadCaseCount": len(_FORBIDDEN_CAMUNDA_NAMES),
        "forbiddenPayloadRejectedCount": rejected_count,
        "idempotencyMismatchCount": idempotency_mismatches,
        "camundaProcessStartAttempts": 0,
        "hrisSideEffectCount": 0,
        "notificationSideEffectCount": 0,
        "groundTruthUsed": False,
        "evaluateOnceArtifactTouched": False,
        "containsRawFieldValues": False,
        "promotionAllowed": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the M5-CAM-005 local scalar/opaque contract regression."
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    output = args.output.resolve()
    if not output.is_absolute():
        raise ValueError("--output must be an absolute private path")
    if ROOT in output.parents:
        raise ValueError("aggregate report must stay outside the repository")
    if output.exists():
        raise FileExistsError("--output already exists; reports are create-only")
    report = run_regression()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
