#!/usr/bin/env python3
"""Close the replay path from the 019H package-lock result without executing it."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCOPE = {
    "candidateVersion": "11.10.2",
    "baselineVersion": "11.9.1",
    "datasetFamily": "CCCD",
    "datasetId": "DATA-HO-014",
    "datasetRole": "DEVELOPMENT_REGRESSION",
    "documentCount": 15,
    "evaluatedFieldCount": 120,
    "diagnosticFieldCount": 45,
}
SOURCE_SCHEMA = "ocr-ho-v2-019h-independent-package-lock-review/1.0.0"
FORBIDDEN_KEYS = {"value", "rawValue", "text", "ocr", "prediction", "groundTruth"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key in FORBIDDEN_KEYS or has_forbidden_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(has_forbidden_key(item) for item in value)
    return False


def validate_source(source: dict[str, Any]) -> None:
    if source.get("schemaVersion") != SOURCE_SCHEMA or source.get("taskId") != "OCR-HO-V2-019H":
        raise SystemExit("019H source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"019H source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not False
        or has_forbidden_key(source)
    ):
        raise SystemExit("019H source is not aggregate-only")
    review = source.get("packageReview", {})
    decision = source.get("decision", {})
    gates = source.get("gates", {})
    if (
        review.get("packageMetadataOnly") is not True
        or review.get("predictionOrGroundTruthOpened") is not False
    ):
        raise SystemExit("019H package review is not metadata-only")
    if decision.get("selectorEligible") is not False or decision.get("runtimeChanged") is not False:
        raise SystemExit("019H selector/runtime flag is not closed")
    if (
        gates.get("developmentRegressionGate") != "HOLD"
        or gates.get("heldoutReadinessGate") != "HOLD"
    ):
        raise SystemExit("019H gate status is not HOLD")
    for key in (
        "developmentReplayAuthorized",
        "heldoutOpened",
        "evaluateOnceAuthorized",
        "promotionAllowed",
    ):
        if decision.get(key) is not False:
            raise SystemExit(f"019H execution flag is not false: {key}")


def build_report(source: dict[str, Any], source_digest: str) -> dict[str, Any]:
    package_review = source["packageReview"]
    package_available = package_review.get("packageAvailable") is True
    lock_ready = package_review.get("packageLockReady") is True
    if package_available and lock_ready:
        status = "INDEPENDENT_PACKAGE_LOCKED_REPLAY_CLOSED_HOLD"
        reason = (
            "Package locks are present, but replay remains separately gated and was not "
            "authorized or executed."
        )
    else:
        status = "INDEPENDENT_PACKAGE_ABSENT_REPLAY_CLOSED_HOLD"
        reason = (
            "No complete independent package lock exists; replay remains closed and no "
            "GroundTruth was created or opened."
        )
    return {
        "schemaVersion": "ocr-ho-v2-019i-replay-closure-review/1.0.0",
        "taskId": "OCR-HO-V2-019I",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": False,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "INDEPENDENT_PACKAGE_LOCK_RESULT_REPLAY_CLOSURE_ONLY",
        },
        "sourceDigests": {
            "source019hSha256": source_digest,
            "sealedManifestDigest": source.get("sourceDigests", {}).get("sealedManifestDigest"),
        },
        "lockReview": {
            "packageAvailable": package_available,
            "packageLockReady": lock_ready,
            "validationFailures": package_review.get("validationFailures", []),
            "replayClosure": "PASS",
            "metadataOnly": True,
        },
        "decision": {
            "status": status,
            "packageLockReady": lock_ready,
            "replayClosed": True,
            "developmentReplayAuthorized": False,
            "developmentReplayExecuted": False,
            "heldoutOpened": False,
            "evaluateOnceAuthorized": False,
            "selectorEligible": False,
            "runtimeChanged": False,
            "promotionAllowed": False,
            "reason": reason,
            "nextTask": "OCR-HO-V2-019J",
            "nextAction": (
                "Keep replay closed until a complete independent package exists and a "
                "separate replay review is recorded."
            ),
        },
        "gates": {
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
            "productionPromotionAllowed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-019h", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.source_019h)
    validate_source(source)
    report = build_report(source, sha256(args.source_019h))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": report["decision"]["status"],
                "replayClosed": report["decision"]["replayClosed"],
                "nextTask": report["decision"]["nextTask"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
