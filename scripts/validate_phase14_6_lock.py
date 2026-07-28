#!/usr/bin/env python3
"""Verify the frozen Phase 14.6 policy and local model artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from hcns_agent.application.ocr_metrics import METRIC_SPEC_VERSION
from hcns_agent.application.recognition_policy import PHASE14_6_SHADOW_POLICY


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load_and_validate_lock(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != "phase14.6-benchmark-lock/1.0.0":
        raise ValueError("Unsupported Phase 14.6 lock schema")
    if payload.get("containsRealPII") is not False:
        raise ValueError("The checked-in lock must not contain real PII")
    if payload.get("metricSpecVersion") != METRIC_SPEC_VERSION:
        raise ValueError("Metric spec does not match the running code")
    if payload.get("policy") != PHASE14_6_SHADOW_POLICY.manifest():
        raise ValueError("Recognition policy does not match the running code")
    protocol = payload.get("heldOutProtocol", {})
    required_guards = (
        "authorizedLocalDocumentsOnly",
        "predictionsMustBeHiddenBeforeGroundTruth",
        "groundTruthMustBeHumanConfirmed",
        "singleFinalEvaluation",
        "promotionRequiresZeroBaselineCorrectLosses",
    )
    if any(protocol.get(key) is not True for key in required_guards):
        raise ValueError("Held-out protocol safety guards are incomplete")
    if protocol.get("thresholdRetuningAllowed") is not False:
        raise ValueError("Held-out threshold retuning must remain disabled")
    if int(protocol.get("minimumDocumentCount", 0)) < 15:
        raise ValueError("Phase 14.6 requires at least 15 held-out documents")
    return payload


def verify_local_models(
    payload: dict[str, Any],
    roots: dict[str, Path],
) -> None:
    for model in payload.get("models", []):
        root_name = str(model["root"])
        if root_name not in roots:
            raise ValueError(f"Missing model root: {root_name}")
        relative = Path(str(model["relativePath"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe model path in lock")
        path = roots[root_name] / relative
        if not path.is_file():
            raise FileNotFoundError(f"Locked model is missing: {model['profile']}")
        if path.stat().st_size != int(model["bytes"]):
            raise ValueError(f"Locked model size changed: {model['profile']}")
        if sha256_file(path) != model["sha256"]:
            raise ValueError(f"Locked model hash changed: {model['profile']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path("config/phase14_6_benchmark_lock.json"),
    )
    parser.add_argument("--private-runtime", type=Path, required=True)
    parser.add_argument("--paddle-model", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = load_and_validate_lock(args.lock)
    verify_local_models(
        payload,
        {
            "privateRuntime": args.private_runtime,
            "paddleModel": args.paddle_model,
        },
    )
    lock_digest = sha256_file(args.lock)
    print(
        "Phase 14.6 lock verified: "
        f"{len(payload['models'])} models, "
        f"{payload['policy']['policyId']}@{payload['policy']['version']}, "
        f"sha256:{lock_digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
