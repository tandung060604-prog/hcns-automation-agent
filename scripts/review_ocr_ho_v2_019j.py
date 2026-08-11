#!/usr/bin/env python3
"""Recheck for a new independent CCCD package/lock without opening or evaluating it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
SOURCE_SCHEMA = "ocr-ho-v2-019i-replay-closure-review/1.0.0"
PACKAGE_SCHEMAS = {
    "ocr-ho-v2-019g-independent-evidence-package-manifest/1.0.0",
    "ocr-ho-v2-019h-independent-evidence-package-manifest/1.0.0",
}
FORBIDDEN_KEYS = {"value", "rawValue", "text", "ocr", "prediction", "groundTruth"}
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


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
    if source.get("schemaVersion") != SOURCE_SCHEMA or source.get("taskId") != "OCR-HO-V2-019I":
        raise SystemExit("019I source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"019I source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not False
        or has_forbidden_key(source)
    ):
        raise SystemExit("019I source is not aggregate-only")
    decision = source.get("decision", {})
    if source.get("lockReview", {}).get("replayClosure") != "PASS":
        raise SystemExit("019I replay closure is not PASS")
    if decision.get("replayClosed") is not True:
        raise SystemExit("019I replay is not closed")
    for key in (
        "developmentReplayAuthorized",
        "developmentReplayExecuted",
        "heldoutOpened",
        "evaluateOnceAuthorized",
        "selectorEligible",
        "runtimeChanged",
        "promotionAllowed",
    ):
        if decision.get(key) is not False:
            raise SystemExit(f"019I execution flag is not false: {key}")


def validate_package(package: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if package.get("schemaVersion") not in PACKAGE_SCHEMAS:
        failures.append("schemaVersion")
    for key, expected in SCOPE.items():
        if package.get(key) != expected:
            failures.append(key)
    if package.get("containsRawPII") is not False or has_forbidden_key(package):
        failures.append("aggregateOnly")
    if package.get("predictionGroundTruthIndependent") is not True:
        failures.append("predictionGroundTruthIndependent")
    locks: dict[str, dict[str, Any]] = {}
    for name in ("predictionLock", "groundTruthLock"):
        section = package.get(name)
        if not isinstance(section, dict):
            failures.append(name)
            continue
        locks[name] = section
        if (
            section.get("sealed") is not True
            or section.get("immutable") is not True
            or section.get("localOnly") is not True
            or not HEX64.fullmatch(str(section.get("sha256") or ""))
            or not str(section.get("lockedAt") or "")
        ):
            failures.append(name)
    prediction = locks.get("predictionLock", {}).get("sha256")
    ground_truth = locks.get("groundTruthLock", {}).get("sha256")
    if prediction and prediction == ground_truth:
        failures.append("distinctPredictionGroundTruthDigests")
    for key in (
        "predictionOpened",
        "gtUsedAtSelection",
        "groundTruthCreatedFromPrediction",
        "evaluateOnceAuthorized",
        "heldoutOpened",
        "primaryRuntimeChanged",
    ):
        if package.get(key) is not False:
            failures.append(key)
    return failures


def build_report(
    source: dict[str, Any],
    package: dict[str, Any] | None,
    failures: list[str],
    source_digest: str,
    package_digest: str | None,
) -> dict[str, Any]:
    available = package is not None
    valid = available and not failures
    if valid:
        status = "NEW_PACKAGE_LOCKED_REPLAY_CLOSED_HOLD"
    elif available:
        status = "NEW_PACKAGE_LOCK_INVALID_REPLAY_CLOSED_HOLD"
    else:
        status = "NEW_PACKAGE_NOT_FOUND_REPLAY_CLOSED_HOLD"
    return {
        "schemaVersion": "ocr-ho-v2-019j-package-recheck/1.0.0",
        "taskId": "OCR-HO-V2-019J",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": False,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "INDEPENDENT_PACKAGE_LOCK_RECHECK_ONLY",
        },
        "sourceDigests": {
            "source019iSha256": source_digest,
            "packageManifestSha256": package_digest,
            "sealedManifestDigest": source.get("sourceDigests", {}).get("sealedManifestDigest"),
        },
        "packageRecheck": {
            "newPackageAvailable": available,
            "newPackageLockValid": valid,
            "validationFailures": failures,
            "metadataOnly": True,
            "predictionOrGroundTruthOpened": False,
            "inventoryResult": "PACKAGE_FOUND" if available else "NO_NEW_PACKAGE_FOUND",
        },
        "decision": {
            "status": status,
            "replayClosed": True,
            "developmentReplayAuthorized": False,
            "developmentReplayExecuted": False,
            "heldoutOpened": False,
            "evaluateOnceAuthorized": False,
            "selectorEligible": False,
            "runtimeChanged": False,
            "promotionAllowed": False,
            "reason": (
                "A new package lock is valid, but replay remains separately gated and was "
                "not executed."
                if valid
                else (
                    "No valid new package lock exists; replay remains closed and no "
                    "GroundTruth was created or opened."
                )
            ),
            "nextTask": "OCR-HO-V2-019K",
            "nextAction": (
                "Review package availability/lock result again before any separately "
                "authorized replay review."
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
    parser.add_argument("--source-019i", type=Path, required=True)
    parser.add_argument("--package-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.source_019i)
    validate_source(source)
    package = load(args.package_manifest) if args.package_manifest else None
    failures = validate_package(package) if package is not None else ["packageManifestMissing"]
    report = build_report(
        source,
        package,
        failures,
        sha256(args.source_019i),
        sha256(args.package_manifest) if args.package_manifest else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": report["decision"]["status"],
                "newPackageAvailable": report["packageRecheck"]["newPackageAvailable"],
                "nextTask": report["decision"]["nextTask"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
