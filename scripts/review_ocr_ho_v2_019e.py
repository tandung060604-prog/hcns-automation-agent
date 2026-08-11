#!/usr/bin/env python3
"""Review sealed 019D quality evidence without opening prediction or runtime paths."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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
TARGET_FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
FORBIDDEN_KEYS = {"value", "rawValue", "text"}
AUTH_SCHEMA = "ocr-ho-v2-019e-quality-matrix-review-authorization-record/1.0.0"


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
        source.get("schemaVersion") != "ocr-ho-v2-019d-per-profile-quality-diagnostic/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-019D"
    ):
        raise SystemExit("019D source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"019D source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
        or has_forbidden_key(source)
    ):
        raise SystemExit("019D must remain aggregate-only and sealed")
    quality = source.get("quality", {})
    if (
        quality.get("profileCount") != 4
        or quality.get("variantCount") != 4
        or quality.get("profileVariantCombinationCount") != 16
        or len(quality.get("profileVariants", [])) != 16
    ):
        raise SystemExit("019D quality matrix scope mismatch")
    for row in quality["profileVariants"]:
        if row.get("evaluatedDocuments") != SCOPE["documentCount"]:
            raise SystemExit("019D row document scope mismatch")
        if set(row.get("fieldQuality", {})) != set(TARGET_FIELDS):
            raise SystemExit("019D target field matrix mismatch")
        if set(row.get("residenceLineClassCounts", {})) != {
            "LINE_ID_MATCH",
            "LINE_ID_MISS",
            "LINE_ORDER_MISMATCH",
            "DUPLICATE_LINE",
        }:
            raise SystemExit("019D residence line matrix mismatch")


def validate_authorization(record: dict[str, Any], source_sha: str, manifest_sha: str) -> None:
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != AUTH_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-019E"
        or record.get("datasetFamily") != SCOPE["datasetFamily"]
        or record.get("datasetId") != SCOPE["datasetId"]
        or record.get("candidateVersion") != SCOPE["candidateVersion"]
        or record.get("baselineVersion") != SCOPE["baselineVersion"]
        or record.get("containsRawPII") is not False
        or str(record.get("sealedManifestSha256") or "").casefold() != manifest_sha.casefold()
        or str(record.get("source019dSha256") or "").casefold() != source_sha.casefold()
        or approval.get("approved") is not True
        or approval.get("approverRole") != "OCR_REVIEW_OWNER"
        or approval.get("localOnly") is not True
        or approval.get("aggregateQualityMatrixReviewAuthorized") is not True
    ):
        raise SystemExit("019E authorization record invalid")
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
            raise SystemExit(f"019E prohibited authorization is not false: {key}")


def quality_review(source: dict[str, Any]) -> dict[str, Any]:
    rows = source["quality"]["profileVariants"]
    field_non_regression: Counter[str] = Counter()
    residence_ascii_values: list[int] = []
    line_totals: Counter[str] = Counter()
    signatures: Counter[tuple[Any, ...]] = Counter()
    for row in rows:
        for field in TARGET_FIELDS:
            comparison = row["oracleVsBaseline"][field]
            if all(
                bool(comparison.get(key))
                for key in ("strictNotWorse", "asciiNotWorse", "cerNotWorse", "derNotWorse")
            ):
                field_non_regression[field] += 1
        residence_ascii_values.append(int(row["residenceOracleAsciiExactCount"]))
        line_totals.update(row["residenceLineClassCounts"])
        signatures[
            (
                tuple(sorted(row["residenceLineClassCounts"].items())),
                row["residenceOracleAsciiExactCount"],
                tuple(
                    sorted(
                        field
                        for field in TARGET_FIELDS
                        if all(row["oracleVsBaseline"][field].values())
                    )
                ),
            )
        ] += 1
    return {
        "profileVariantRows": len(rows),
        "fieldQualityRows": len(rows) * len(TARGET_FIELDS),
        "fieldNonRegressionPassCounts": {
            field: field_non_regression[field] for field in TARGET_FIELDS
        },
        "allFieldNonRegressionPassRows": sum(
            all(all(row["oracleVsBaseline"][field].values()) for field in TARGET_FIELDS)
            for row in rows
        ),
        "residence": {
            "gateAsciiExactCount": 13,
            "gateAsciiMatch": 0.85,
            "oracleAsciiExactMin": min(residence_ascii_values),
            "oracleAsciiExactMax": max(residence_ascii_values),
            "gateQualifiedCombinationCount": sum(value >= 13 for value in residence_ascii_values),
        },
        "residenceLineClassTotals": dict(sorted(line_totals.items())),
        "matrixSignatureCount": len(signatures),
        "matrixSignatureDistribution": [
            {"signature": list(signature), "combinationCount": count}
            for signature, count in sorted(signatures.items(), key=lambda item: repr(item[0]))
        ],
    }


def build_report(
    source: dict[str, Any], review: dict[str, Any], digests: dict[str, str]
) -> dict[str, Any]:
    return {
        "schemaVersion": "ocr-ho-v2-019e-quality-matrix-review/1.0.0",
        "taskId": "OCR-HO-V2-019E",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": False,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "INDEPENDENT_QUALITY_MATRIX_REVIEW_ONLY",
        },
        "sourceDigests": digests,
        "review": review,
        "decision": {
            "status": "PER_PROFILE_QUALITY_MATRIX_NONDISCRIMINATIVE_HOLD",
            "profileVariantWinner": None,
            "selectorEligible": False,
            "patchReviewEligible": False,
            "candidateRule": None,
            "selectorChanged": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "No profile/variant combination passes all field non-regression checks and "
                "the residence oracle ceiling is only 2/15 versus the 13/15 gate. The matrix "
                "does not justify a selector or bounded runtime patch."
            ),
            "nextTask": "OCR-HO-V2-019F",
            "nextAction": (
                "Close the profile/variant selection path and define the next independent "
                "evidence requirement without changing runtime."
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
    parser.add_argument("--source-019d", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--sealed-manifest-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.source_019d)
    authorization = load(args.authorization_record)
    validate_source(source)
    source_sha = sha256(args.source_019d)
    validate_authorization(authorization, source_sha, args.sealed_manifest_digest)
    report = build_report(
        source,
        quality_review(source),
        {
            "source019dSha256": source_sha,
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
                "profileVariantRows": report["review"]["profileVariantRows"],
                "allFieldNonRegressionPassRows": report["review"]["allFieldNonRegressionPassRows"],
                "residenceOracleAsciiMax": report["review"]["residence"]["oracleAsciiExactMax"],
                "nextTask": report["decision"]["nextTask"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
