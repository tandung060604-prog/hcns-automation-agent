"""Run the M5-CAM-004 synthetic Camunda manual-review rehearsal."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcns_agent.adapters.camunda7.m5_authorization import (  # noqa: E402
    M5SyntheticAuthorization,
)
from hcns_agent.adapters.camunda7.shadow_preflight import (  # noqa: E402
    build_local_shadow_gateway,
    run_shadow_preflight,
)


def build_synthetic_authorization(now: datetime) -> M5SyntheticAuthorization:
    """Create an in-memory, short-lived synthetic-only authorization."""

    current = now.astimezone(timezone.utc)
    payload = {
        "status": "AUTHORIZED_SYNTHETIC_ONLY",
        "authorizationId": "m5-cam-004-auth",
        "ownerId": "m5-cam-004-owner",
        "reviewerIds": ["m5-cam-004-reviewer"],
        "scope": {
            "kind": "SYNTHETIC_ONLY",
            "realCohortAllowed": False,
            "families": ["LEAVE_REQUEST", "OVERTIME_REQUEST"],
            "caseCount": 2,
        },
        "timeWindow": {
            "start": (current - timedelta(minutes=1)).isoformat(),
            "end": (current + timedelta(minutes=5)).isoformat(),
        },
        "retention": {
            "retainUntil": (current + timedelta(days=7)).isoformat(),
            "deletionOwnerId": "m5-cam-004-owner",
        },
        "rollback": {
            "authorityId": "m5-cam-004-owner",
            "triggers": [
                "autoContinueCount > 0",
                "rawExposureCount > 0",
                "duplicateResultArtifacts > 0",
                "unreconciledCases > 0",
                "realSideEffectCount > 0",
                "any_case_not_MANUAL_REVIEW",
                "case_duration_seconds > 60",
            ],
        },
        "policy": {
            "reviewAction": "MANUAL_REVIEW",
            "autoContinueEnabled": False,
            "realSideEffectsEnabled": False,
            "data24": "IMMUTABLE_NOT_OPENED",
        },
    }
    return M5SyntheticAuthorization.from_mapping(payload)


def build_rehearsal_report(
    preflight: Mapping[str, object],
    *,
    process_start_count: int,
    authorization: M5SyntheticAuthorization,
) -> dict[str, object]:
    """Add M5-CAM-004 handoff, idempotency and rollback evidence."""

    cases = preflight.get("cases")
    case_ids = [
        case.get("case_id")
        for case in cases
        if isinstance(case, Mapping)
    ] if isinstance(cases, list) else []
    idempotency_passed = (
        len(case_ids) == 2
        and all(isinstance(case_id, str) and case_id for case_id in case_ids)
        and len(set(case_ids)) == len(case_ids)
        and preflight.get("duplicateResultArtifacts") == 0
    )
    rollback_probe = deepcopy(dict(preflight))
    rollback_probe["autoContinueCount"] = 1
    rollback_decision = authorization.evaluate_report(rollback_probe)
    preflight_passed = preflight.get("passed") is True
    report = {
        "milestone": "M5-CAM-004",
        "mode": "LOCAL_SYNTHETIC_CAMUNDA_MANUAL_REVIEW",
        "passed": (
            preflight_passed
            and process_start_count == 2
            and idempotency_passed
            and rollback_decision.rollback_required
            and not rollback_decision.allowed_to_complete
        ),
        "caseCount": preflight.get("caseCount"),
        "documentTypes": [
            case.get("document_type")
            for case in cases
            if isinstance(case, Mapping)
        ] if isinstance(cases, list) else [],
        "processStartCount": process_start_count,
        "manualReviewCount": sum(
            1
            for case in cases
            if isinstance(case, Mapping) and case.get("reached_user_review") is True
        ) if isinstance(cases, list) else 0,
        "autoContinueCount": preflight.get("autoContinueCount"),
        "rawExposureCount": preflight.get("rawExposureCount"),
        "duplicateResultArtifacts": preflight.get("duplicateResultArtifacts"),
        "unreconciledCases": preflight.get("unreconciledCases"),
        "realSideEffectCount": preflight.get("realSideEffectCount"),
        "idempotency": {
            "passed": idempotency_passed,
            "duplicateCaseIdCount": len(case_ids) - len(set(case_ids)),
            "duplicateResultArtifacts": preflight.get("duplicateResultArtifacts"),
        },
        "rollbackCheck": {
            "simulatedViolation": "autoContinueCount > 0",
            "rollbackRequired": rollback_decision.rollback_required,
            "allowedToComplete": rollback_decision.allowed_to_complete,
            "action": rollback_decision.action,
            "triggerCodes": list(rollback_decision.trigger_codes),
        },
        "handoff": {
            "boundary": "phase15-scalar-reference",
            "scalarOnly": True,
            "opaqueReferenceOnly": True,
            "reviewAction": "MANUAL_REVIEW",
            "autoContinueEnabled": False,
            "realSideEffectsEnabled": False,
        },
        "authorization": {
            "syntheticOnly": True,
            "realCohortAllowed": False,
            "groundTruthUsed": False,
            "evaluateOnceArtifactTouched": False,
        },
        "promotionAllowed": False,
        "containsRawFieldValues": False,
    }
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run two synthetic leave/overtime cases through local Camunda 7.13."
    )
    parser.add_argument("--camunda-url", required=True)
    parser.add_argument("--worker-id", default="m5-cam-004-rehearsal")
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.output.is_absolute() or not args.private_root.is_absolute():
        raise ValueError("--private-root and --output must be absolute private paths")
    output = args.output.resolve()
    private_root = args.private_root.resolve()
    if ROOT in output.parents or ROOT in private_root.parents:
        raise ValueError("private artifacts must stay outside the repository")
    if output.exists():
        raise FileExistsError("--output already exists; rehearsal reports are create-only")
    authorization = build_synthetic_authorization(datetime.now(timezone.utc))
    gateway = build_local_shadow_gateway(
        base_url=args.camunda_url,
        worker_id=args.worker_id,
    )
    preflight = run_shadow_preflight(
        gateway=gateway,
        private_root=private_root,
        repository_root=ROOT,
        worker_id=args.worker_id,
        authorization=authorization,
    )
    report = build_rehearsal_report(
        preflight.as_dict(),
        process_start_count=gateway.process_start_attempts,
        authorization=authorization,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
