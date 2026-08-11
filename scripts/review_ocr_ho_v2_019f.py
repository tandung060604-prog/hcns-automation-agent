#!/usr/bin/env python3
"""Close the CCCD profile/variant selector path from sealed aggregate evidence."""

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
AUTH_SCHEMA = "ocr-ho-v2-019f-profile-variant-closure-authorization-record/1.0.0"
FORBIDDEN_KEYS = {"value", "rawValue", "text"}


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
        source.get("schemaVersion") != "ocr-ho-v2-019e-quality-matrix-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-019E"
    ):
        raise SystemExit("019E source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"019E source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not False
        or has_forbidden_key(source)
    ):
        raise SystemExit("019E must remain aggregate-only and sealed")
    decision = source.get("decision", {})
    gates = source.get("gates", {})
    review = source.get("review", {})
    if (
        decision.get("selectorEligible") is not False
        or decision.get("patchReviewEligible") is not False
        or decision.get("counterfactualAuthorized") is not False
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
        or decision.get("promotionAllowed") is not False
        or gates.get("developmentRegressionGate") != "HOLD"
        or gates.get("heldoutReadinessGate") != "HOLD"
        or gates.get("acceptedCoverage") != 0
        or gates.get("manualReviewOnly") is not True
        or review.get("allFieldNonRegressionPassRows") != 0
        or review.get("residence", {}).get("oracleAsciiExactMax") != 2
        or review.get("residence", {}).get("gateQualifiedCombinationCount") != 0
    ):
        raise SystemExit("019E closure evidence mismatch")


def validate_authorization(record: dict[str, Any], source_sha: str, manifest_sha: str) -> None:
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != AUTH_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-019F"
        or record.get("datasetFamily") != SCOPE["datasetFamily"]
        or record.get("datasetId") != SCOPE["datasetId"]
        or record.get("candidateVersion") != SCOPE["candidateVersion"]
        or record.get("baselineVersion") != SCOPE["baselineVersion"]
        or record.get("containsRawPII") is not False
        or str(record.get("sealedManifestSha256") or "").casefold() != manifest_sha.casefold()
        or str(record.get("source019eSha256") or "").casefold() != source_sha.casefold()
        or approval.get("approved") is not True
        or approval.get("approverRole") != "OCR_REVIEW_OWNER"
        or approval.get("localOnly") is not True
        or approval.get("aggregateProfileVariantClosureAuthorized") is not True
    ):
        raise SystemExit("019F authorization record invalid")
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
            raise SystemExit(f"019F prohibited authorization is not false: {key}")


def close_path(source: dict[str, Any]) -> dict[str, Any]:
    review = source["review"]
    return {
        "closureBasis": {
            "profileVariantRows": review["profileVariantRows"],
            "fieldQualityRows": review["fieldQualityRows"],
            "fullNonRegressionPassRows": review["allFieldNonRegressionPassRows"],
            "residenceOracleAsciiMax": review["residence"]["oracleAsciiExactMax"],
            "residenceGateQualifiedCombinationCount": review["residence"][
                "gateQualifiedCombinationCount"
            ],
            "matrixSignatureCount": review["matrixSignatureCount"],
        },
        "selectionPath": {
            "status": "CLOSED",
            "profileVariantWinner": None,
            "selectorEligible": False,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
        },
        "reopenRequirements": [
            (
                "A new independent evidence package with prediction and GroundTruth digests "
                "locked separately."
            ),
            (
                "Pinned CCCD scope and baseline version, with no oracle line/profile IDs used "
                "at selection."
            ),
            "At least one candidate must meet residence ASCII >= 13/15 and automatic ROI >= 95%.",
            (
                "Exact regression count = 0, DER non-regression PASS, schema errors = 0 and "
                "sensitive false acceptance = 0."
            ),
            "Explicit review-owner authorization before any selector, patch or development replay.",
        ],
        "notSufficientEvidence": [
            "Oracle-best profile/variant quality is attribution-only and cannot select runtime.",
            "The 019D residence ceiling is 2/15, far below the 13/15 gate.",
            "No combination passes all field non-regression comparisons.",
        ],
    }


def build_report(
    source: dict[str, Any], closure: dict[str, Any], digests: dict[str, str]
) -> dict[str, Any]:
    return {
        "schemaVersion": "ocr-ho-v2-019f-profile-variant-closure/1.0.0",
        "taskId": "OCR-HO-V2-019F",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": False,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "PROFILE_VARIANT_SELECTION_CLOSURE_ONLY",
        },
        "sourceDigests": digests,
        "closure": closure,
        "decision": {
            "status": "PROFILE_VARIANT_SELECTION_PATH_CLOSED_HOLD",
            "profileVariantWinner": None,
            "selectorEligible": False,
            "patchReviewEligible": False,
            "selectorChanged": False,
            "patchAuthorized": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "019E provides no full non-regression pass and no residence gate-qualified "
                "combination; the profile/variant selection path is closed until a new "
                "independent evidence package satisfies the documented reopen requirements."
            ),
            "nextTask": "OCR-HO-V2-019G",
            "nextAction": (
                "Prepare or review a new independent evidence package; do not reopen selector, "
                "patch, replay or promotion paths in the current development artifact."
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
    parser.add_argument("--source-019e", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--sealed-manifest-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.source_019e)
    authorization = load(args.authorization_record)
    validate_source(source)
    source_sha = sha256(args.source_019e)
    validate_authorization(authorization, source_sha, args.sealed_manifest_digest)
    report = build_report(
        source,
        close_path(source),
        {
            "source019eSha256": source_sha,
            "authorizationRecordSha256": sha256(args.authorization_record),
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
                "selectionPath": report["closure"]["selectionPath"]["status"],
                "reopenRequirementCount": len(report["closure"]["reopenRequirements"]),
                "nextTask": report["decision"]["nextTask"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
