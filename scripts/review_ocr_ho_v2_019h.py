#!/usr/bin/env python3
"""Review independent CCCD prediction/GroundTruth package locks without evaluation."""

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
SOURCE_SCHEMA = "ocr-ho-v2-019g-independent-package-intake/1.0.0"
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
    if source.get("schemaVersion") != SOURCE_SCHEMA or source.get("taskId") != "OCR-HO-V2-019G":
        raise SystemExit("019G source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"019G source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not False
    ):
        raise SystemExit("019G source is not sealed aggregate-only")
    decision = source.get("decision", {})
    for key in (
        "developmentReplayAuthorized",
        "heldoutOpened",
        "evaluateOnceAuthorized",
        "runtimeChanged",
        "promotionAllowed",
    ):
        if decision.get(key) is not False:
            raise SystemExit(f"019G source execution flag is not false: {key}")


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
        digest = str(section.get("sha256") or "")
        if (
            section.get("sealed") is not True
            or section.get("immutable") is not True
            or section.get("localOnly") is not True
            or not HEX64.fullmatch(digest)
            or not str(section.get("lockedAt") or "")
        ):
            failures.append(name)
    prediction_digest = locks.get("predictionLock", {}).get("sha256")
    ground_truth_digest = locks.get("groundTruthLock", {}).get("sha256")
    if prediction_digest and prediction_digest == ground_truth_digest:
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
    digests: dict[str, str | None],
) -> dict[str, Any]:
    available = package is not None
    locked = available and not failures
    return {
        "schemaVersion": "ocr-ho-v2-019h-independent-package-lock-review/1.0.0",
        "taskId": "OCR-HO-V2-019H",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": False,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "INDEPENDENT_PREDICTION_GROUNDTRUTH_LOCK_REVIEW_ONLY",
        },
        "sourceDigests": digests,
        "packageReview": {
            "packageAvailable": available,
            "packageLockReady": locked,
            "validationFailures": failures,
            "packageMetadataOnly": True,
            "predictionOrGroundTruthOpened": False,
            "requiredLocks": [
                "predictionLock sealed/immutable/localOnly with 64-hex SHA-256",
                "groundTruthLock sealed/immutable/localOnly with distinct 64-hex SHA-256",
                "predictionGroundTruthIndependent=true",
                "exact scope 15 documents / 120 fields / 45 diagnostic fields",
                "prediction-derived GroundTruth and evaluate-once explicitly disabled",
            ],
        },
        "decision": {
            "status": "PACKAGE_LOCKED_READY_HOLD" if locked else "PACKAGE_LOCK_NOT_READY_HOLD",
            "packageLockReady": locked,
            "developmentReplayAuthorized": False,
            "heldoutOpened": False,
            "evaluateOnceAuthorized": False,
            "selectorEligible": False,
            "runtimeChanged": False,
            "promotionAllowed": False,
            "reason": (
                "Independent prediction and GroundTruth locks satisfy metadata checks; "
                "replay remains separately gated."
                if locked
                else (
                    "Independent prediction/GroundTruth package is missing or fails lock checks; "
                    "no GroundTruth was created or opened."
                )
            ),
            "nextTask": "OCR-HO-V2-019I",
            "nextAction": (
                "Keep replay closed until the package lock review is complete and "
                "separately scheduled."
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
    parser.add_argument("--source-019g", type=Path, required=True)
    parser.add_argument("--package-manifest", type=Path)
    parser.add_argument("--sealed-manifest-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.source_019g)
    validate_source(source)
    source_digest = sha256(args.source_019g)
    package = load(args.package_manifest) if args.package_manifest else None
    failures = validate_package(package) if package is not None else ["packageManifestMissing"]
    report = build_report(
        source,
        package,
        failures,
        {
            "source019gSha256": source_digest,
            "packageManifestSha256": sha256(args.package_manifest)
            if args.package_manifest
            else None,
            "sealedManifestDigest": args.sealed_manifest_digest,
        },
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
                "packageAvailable": report["packageReview"]["packageAvailable"],
                "packageLockReady": report["packageReview"]["packageLockReady"],
                "nextTask": report["decision"]["nextTask"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
