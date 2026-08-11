#!/usr/bin/env python3
"""Intake an independent CCCD prediction/GroundTruth package without evaluating it."""

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
AUTH_SCHEMA = "ocr-ho-v2-019g-independent-package-intake-authorization-record/1.0.0"
PACKAGE_SCHEMA = "ocr-ho-v2-019g-independent-evidence-package-manifest/1.0.0"
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
    if (
        source.get("schemaVersion") != "ocr-ho-v2-019f-profile-variant-closure/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-019F"
    ):
        raise SystemExit("019F source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"019F source scope mismatch: {key}")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit("019F must remain aggregate-only and sealed")
    decision = source.get("decision", {})
    if (
        decision.get("status") != "PROFILE_VARIANT_SELECTION_PATH_CLOSED_HOLD"
        or decision.get("selectorEligible") is not False
        or decision.get("patchReviewEligible") is not False
        or decision.get("promotionAllowed") is not False
    ):
        raise SystemExit("019F closure status mismatch")


def validate_authorization(record: dict[str, Any], source_sha: str, manifest_sha: str) -> None:
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != AUTH_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-019G"
        or record.get("datasetFamily") != SCOPE["datasetFamily"]
        or record.get("datasetId") != SCOPE["datasetId"]
        or record.get("candidateVersion") != SCOPE["candidateVersion"]
        or record.get("baselineVersion") != SCOPE["baselineVersion"]
        or record.get("containsRawPII") is not False
        or str(record.get("sealedManifestSha256") or "").casefold() != manifest_sha.casefold()
        or str(record.get("source019fSha256") or "").casefold() != source_sha.casefold()
        or approval.get("approved") is not True
        or approval.get("approverRole") != "OCR_REVIEW_OWNER"
        or approval.get("localOnly") is not True
        or approval.get("independentEvidencePackageIntakeAuthorized") is not True
    ):
        raise SystemExit("019G authorization record invalid")
    for key in (
        "selectorChangeAuthorized",
        "counterfactualAuthorized",
        "developmentReplayAuthorized",
        "heldoutEvaluationAuthorized",
        "evaluateOnceAuthorized",
        "primaryRuntimeChangeAuthorized",
        "productionPromotionAllowed",
    ):
        if approval.get(key) is not False:
            raise SystemExit(f"019G prohibited authorization is not false: {key}")


def validate_package(package: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if package.get("schemaVersion") != PACKAGE_SCHEMA:
        failures.append("schemaVersion")
    for key, expected in SCOPE.items():
        if package.get(key) != expected:
            failures.append(key)
    if package.get("containsRawPII") is not False or has_forbidden_key(package):
        failures.append("aggregateOnly")
    if package.get("predictionGroundTruthIndependent") is not True:
        failures.append("predictionGroundTruthIndependent")
    for section_name in ("predictionLock", "groundTruthLock"):
        section = package.get(section_name, {})
        if (
            section.get("sealed") is not True
            or section.get("immutable") is not True
            or section.get("localOnly") is not True
            or not str(section.get("sha256") or "")
            or not str(section.get("lockedAt") or "")
        ):
            failures.append(section_name)
    for key in (
        "predictionOpened",
        "groundTruthCreatedFromPrediction",
        "evaluateOnceAuthorized",
        "heldoutOpened",
        "primaryRuntimeChanged",
    ):
        if package.get(key) is not False:
            failures.append(key)
    prediction_sha = package.get("predictionLock", {}).get("sha256")
    ground_truth_sha = package.get("groundTruthLock", {}).get("sha256")
    if prediction_sha and prediction_sha == ground_truth_sha:
        failures.append("distinctPredictionGroundTruthDigests")
    return failures


def build_report(
    source: dict[str, Any],
    package: dict[str, Any] | None,
    failures: list[str],
    digests: dict[str, str],
) -> dict[str, Any]:
    available = package is not None
    ready = available and not failures
    missing = [
        "prediction lock with independent SHA-256 and immutable/local-only metadata",
        "GroundTruth lock with independent SHA-256 and reviewer confirmation",
        "distinct prediction and GroundTruth digests",
        "sealed scope for 15 documents / 120 fields / 45 diagnostic fields",
        "explicit prohibition of prediction-derived GroundTruth and evaluate-once execution",
    ]
    return {
        "schemaVersion": "ocr-ho-v2-019g-independent-package-intake/1.0.0",
        "taskId": "OCR-HO-V2-019G",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": False,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "INDEPENDENT_PREDICTION_GROUNDTRUTH_PACKAGE_INTAKE_ONLY",
        },
        "sourceDigests": digests,
        "packageReview": {
            "packageAvailable": available,
            "packageReady": ready,
            "validationFailures": failures,
            "requiredEvidence": missing,
            "packageMetadataOnly": True,
            "predictionOrGroundTruthOpened": False,
        },
        "decision": {
            "status": "INDEPENDENT_PACKAGE_READY_HOLD" if ready else "PACKAGE_NOT_READY_HOLD",
            "packageReady": ready,
            "selectorEligible": False,
            "patchReviewEligible": False,
            "developmentReplayAuthorized": False,
            "heldoutOpened": False,
            "evaluateOnceAuthorized": False,
            "runtimeChanged": False,
            "promotionAllowed": False,
            "reason": (
                "A complete independent package is available for a future gate review."
                if ready
                else (
                    "No complete independent prediction/GroundTruth package is available; "
                    "no GroundTruth was created or opened."
                )
            ),
            "nextTask": "OCR-HO-V2-019H",
            "nextAction": (
                "Review or lock a complete independent package before any replay or evaluation."
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
    parser.add_argument("--source-019f", type=Path, required=True)
    parser.add_argument("--package-manifest", type=Path)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--sealed-manifest-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.source_019f)
    authorization = load(args.authorization_record)
    validate_source(source)
    source_sha = sha256(args.source_019f)
    validate_authorization(authorization, source_sha, args.sealed_manifest_digest)
    package = load(args.package_manifest) if args.package_manifest else None
    failures = validate_package(package) if package is not None else ["packageManifestMissing"]
    report = build_report(
        source,
        package,
        failures,
        {
            "source019fSha256": source_sha,
            "authorizationRecordSha256": sha256(args.authorization_record),
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
                "packageReady": report["packageReview"]["packageReady"],
                "nextTask": report["decision"]["nextTask"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
