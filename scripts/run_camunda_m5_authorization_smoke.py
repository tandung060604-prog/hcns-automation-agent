"""Run M5-CAM-001C authorization expiry and rollback checks locally."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcns_agent.adapters.camunda7.m5_authorization import (  # noqa: E402
    M5AuthorizationError,
    M5SyntheticAuthorization,
)
from hcns_agent.adapters.camunda7.shadow_preflight import (  # noqa: E402
    build_local_shadow_gateway,
    run_shadow_preflight,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run synthetic-only M5 authorization expiry and rollback smoke checks."
    )
    parser.add_argument("--camunda-url", required=True)
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _read_authorization(path: Path) -> tuple[dict[str, object], M5SyntheticAuthorization]:
    if not path.is_absolute():
        raise ValueError("--authorization must be an absolute private path")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("authorization record must be a JSON object")
    return payload, M5SyntheticAuthorization.from_mapping(payload)


def _aggregate(report: dict[str, object]) -> dict[str, object]:
    return {
        "passed": report.get("passed") is True,
        "caseCount": report.get("caseCount"),
        "autoContinueCount": report.get("autoContinueCount"),
        "rawExposureCount": report.get("rawExposureCount"),
        "duplicateResultArtifacts": report.get("duplicateResultArtifacts"),
        "unreconciledCases": report.get("unreconciledCases"),
        "realSideEffectCount": report.get("realSideEffectCount"),
    }


def main() -> int:
    args = _parser().parse_args()
    for path, name in ((args.output, "--output"), (args.private_root, "--private-root")):
        if not path.is_absolute():
            raise ValueError(f"{name} must be an absolute private path")
    output = args.output.resolve()
    if ROOT in output.parents:
        raise ValueError("--output must be outside the repository")
    if output.exists():
        raise FileExistsError("--output already exists; smoke reports are create-only")

    payload, authorization = _read_authorization(args.authorization.resolve())
    now = datetime.now(timezone.utc)
    active_gateway = build_local_shadow_gateway(
        base_url=args.camunda_url,
        worker_id="m5-cam-001c-active",
    )
    active_report = run_shadow_preflight(
        gateway=active_gateway,
        private_root=args.private_root.resolve() / "active",
        repository_root=ROOT,
        worker_id="m5-cam-001c-active",
        authorization=authorization,
        authorization_now=lambda: now,
    )
    active_aggregate = active_report.as_dict()
    active_decision = authorization.evaluate_report(active_aggregate)

    expired_payload = deepcopy(payload)
    expired_window = expired_payload["timeWindow"]
    if not isinstance(expired_window, dict):
        raise ValueError("authorization timeWindow must be an object")
    expired_window["start"] = "2026-08-09T15:55:00+07:00"
    expired_window["end"] = "2026-08-09T18:00:00+07:00"
    expired_authorization = M5SyntheticAuthorization.from_mapping(expired_payload)
    expiry_gateway = build_local_shadow_gateway(
        base_url=args.camunda_url,
        worker_id="m5-cam-001c-expiry",
    )
    expired_refused = False
    expiry_error = ""
    try:
        run_shadow_preflight(
            gateway=expiry_gateway,
            private_root=args.private_root.resolve() / "expired",
            repository_root=ROOT,
            worker_id="m5-cam-001c-expiry",
            authorization=expired_authorization,
            authorization_now=lambda: now,
        )
    except M5AuthorizationError as error:
        expired_refused = True
        expiry_error = str(error)

    violation_report = deepcopy(active_aggregate)
    violation_report["autoContinueCount"] = 1
    rollback_decision = authorization.evaluate_report(violation_report)
    result = {
        "milestone": "M5-CAM-001C",
        "mode": "LOCAL_SYNTHETIC_AUTHORIZATION_SMOKE",
        "passed": (
            active_decision.allowed_to_complete
            and not active_decision.rollback_required
            and expired_refused
            and expiry_gateway.process_start_attempts == 0
            and rollback_decision.rollback_required
            and not rollback_decision.allowed_to_complete
        ),
        "authorization": {
            "status": "AUTHORIZED_SYNTHETIC_ONLY",
            "realCohortAllowed": False,
            "reviewAction": "MANUAL_REVIEW",
            "realSideEffectsEnabled": False,
            "data24": "IMMUTABLE_NOT_OPENED",
        },
        "activeRun": {
            "aggregate": _aggregate(active_aggregate),
            "decision": {
                "allowedToComplete": active_decision.allowed_to_complete,
                "rollbackRequired": active_decision.rollback_required,
            },
        },
        "expiryCheck": {
            "expiredAuthorizationRefused": expired_refused,
            "processStartAttempts": expiry_gateway.process_start_attempts,
            "error": expiry_error,
        },
        "rollbackCheck": {
            "simulatedViolation": "autoContinueCount > 0",
            "rollbackRequired": rollback_decision.rollback_required,
            "allowedToComplete": rollback_decision.allowed_to_complete,
            "action": rollback_decision.action,
            "triggerCodes": list(rollback_decision.trigger_codes),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
