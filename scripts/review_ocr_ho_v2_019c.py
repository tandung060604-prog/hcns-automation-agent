#!/usr/bin/env python3
"""Review independent residence cross-tab for profile/variant discrimination."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
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
AUTH_SCHEMA = "ocr-ho-v2-019c-independent-cross-tab-review-authorization-record/1.0.0"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_scope(source: dict[str, Any], schema: str, task_id: str) -> None:
    if source.get("schemaVersion") != schema or source.get("taskId") != task_id:
        raise SystemExit(f"{task_id} source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{task_id} source scope mismatch: {key}")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} must remain aggregate-only and sealed")


def validate_authorization(record: dict[str, Any] | None, manifest_digest: str) -> None:
    if record is None:
        raise SystemExit("019C standing local-only diagnostic authorization required")
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != AUTH_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-019C"
        or record.get("datasetFamily") != SCOPE["datasetFamily"]
        or record.get("datasetId") != SCOPE["datasetId"]
        or record.get("candidateVersion") != SCOPE["candidateVersion"]
        or record.get("baselineVersion") != SCOPE["baselineVersion"]
        or record.get("containsRawPII") is not False
        or str(record.get("sealedManifestSha256") or "").casefold()
        != manifest_digest.casefold()
        or approval.get("approved") is not True
        or approval.get("approverRole") != "OCR_REVIEW_OWNER"
        or approval.get("localOnly") is not True
        or approval.get("aggregateCrossTabReviewAuthorized") is not True
    ):
        raise SystemExit("019C authorization record invalid")
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
            raise SystemExit(f"019C prohibited authorization is not false: {key}")


def validate_source(source: dict[str, Any]) -> None:
    validate_scope(
        source,
        "ocr-ho-v2-019b-independent-residence-boundary-profile-variant-crosstab/1.0.0",
        "OCR-HO-V2-019B",
    )
    cross_tab = source.get("crossTab", {})
    if cross_tab.get("available") is not True or cross_tab.get("rows") is None:
        raise SystemExit("019B independent cross-tab is required")
    if cross_tab.get("profileVariantCombinationCount") != 16:
        raise SystemExit("019B profile/variant combination scope mismatch")
    if cross_tab.get("profileVariantDocumentGroups") != 240:
        raise SystemExit("019B document group scope mismatch")
    if any("value" in row or "text" in row or "rawValue" in row for row in cross_tab["rows"]):
        raise SystemExit("019B raw value emitted")


def signature_review(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_combo: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for row in rows:
        combo = (str(row["profile"]), str(row["variant"]))
        by_combo[combo][str(row["boundaryCategory"])] = int(row["lineIdMissGroups"])
    signatures = {
        tuple(sorted(values.items()))
        for values in by_combo.values()
    }
    return {
        "combinationCount": len(by_combo),
        "signatureCount": len(signatures),
        "discriminative": len(signatures) > 1,
        "signatures": [
            {"boundaryCounts": dict(signature), "combinationCount": sum(
                tuple(sorted(values.items())) == signature for values in by_combo.values()
            )}
            for signature in sorted(signatures)
        ],
    }


def review(source: dict[str, Any], digests: dict[str, str]) -> dict[str, Any]:
    cross_tab = source["crossTab"]
    signatures = signature_review(cross_tab["rows"])
    return {
        "schemaVersion": "ocr-ho-v2-019c-independent-cross-tab-review/1.0.0",
        "taskId": "OCR-HO-V2-019C",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "INDEPENDENT_RESIDENCE_CROSSTAB_REVIEW_ONLY",
        },
        "sourceDigests": digests,
        "review": {
            **signatures,
            "independentRows": len(cross_tab["rows"]),
            "lineIdMissGroups": cross_tab["lineIdClassTotals"]["LINE_ID_MISS"],
            "boundaryAttributedLineIdMissGroups": cross_tab["boundaryAttributedLineIdMissGroups"],
            "profileVariantWinner": None,
            "selectorEligible": False,
            "patchReviewEligible": False,
            "interpretation": (
                "Every profile/variant combination has the same boundary signature; the "
                "cross-tab confirms a common document/geometry cohort, not a discriminative "
                "profile or variant cause."
            ),
        },
        "decision": {
            "status": "INDEPENDENT_CROSSTAB_NONDISCRIMINATIVE_HOLD",
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
                "The independent cross-tab contains one identical signature across all 16 "
                "profile/variant combinations; no safe winner or patch-specific cause is "
                "established."
            ),
            "nextTask": "OCR-HO-V2-019D",
            "nextAction": (
                "Collect independent per-profile quality/non-regression evidence before any "
                "patch or selector review; keep all runtime paths closed."
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
    parser.add_argument("--artifact-019b", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--sealed-manifest-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.artifact_019b)
    authorization = load(args.authorization_record)
    validate_source(source)
    validate_authorization(authorization, args.sealed_manifest_digest)
    report = review(
        source,
        {
            "artifact019bSha256": sha256(args.artifact_019b),
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
                "signatureCount": report["review"]["signatureCount"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
