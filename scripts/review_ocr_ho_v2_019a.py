#!/usr/bin/env python3
"""Aggregate-only decision on whether a residence patch review may open."""

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
AUTH_SCHEMA = "ocr-ho-v2-019a-residence-patch-review-authorization-record/1.0.0"
PROHIBITED_AUTH_KEYS = (
    "selectorChangeAuthorized",
    "counterfactualAuthorized",
    "developmentReplayAuthorized",
    "heldoutEvaluationAuthorized",
    "evaluateOnceAuthorized",
    "primaryRuntimeChangeAuthorized",
    "productionPromotionAllowed",
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_scope(source: dict[str, Any], schema: str, task_id: str) -> None:
    if source.get("schemaVersion") != schema or source.get("taskId") != task_id:
        raise SystemExit(f"{task_id} source schema mismatch")
    for key, expected in SCOPE.items():
        actual = source.get(key)
        if key == "diagnosticFieldCount" and task_id == "OCR-HO-V2-018C" and actual is None:
            continue
        if actual != expected:
            raise SystemExit(f"{task_id} source scope mismatch: {key}")
    if source.get("containsRawPII") is not False:
        raise SystemExit(f"{task_id} must be aggregate-only")
    if source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} prediction must remain sealed")


def validate_sources(
    source_018z: dict[str, Any],
    source_018a: dict[str, Any],
    source_018c: dict[str, Any],
) -> None:
    validate_scope(
        source_018z,
        "ocr-ho-v2-018z-residence-line-id-boundary-attribution/1.0.0",
        "OCR-HO-V2-018Z",
    )
    validate_scope(
        source_018a,
        "ocr-ho-v2-018a-shadow-patch-review/1.0.0",
        "OCR-HO-V2-018A",
    )
    validate_scope(
        source_018c,
        "ocr-ho-v2-018c-development-replay/1.0.0",
        "OCR-HO-V2-018C",
    )
    if source_018z["decision"]["patchAuthorized"] is not False:
        raise SystemExit("018Z patch boundary must remain closed")
    if source_018z["geometryCorroboration"]["globalPatchThresholdReached"] is not False:
        raise SystemExit("018Z global patch threshold drift")
    if source_018z["attribution"]["crossTabAvailable"] is not False:
        raise SystemExit("018Z cross-tab status drift")
    review_018a = source_018a.get("review", {})
    if review_018a.get("primaryRuntimeChanged") is not False:
        raise SystemExit("018A primary runtime must remain unchanged")
    if review_018a.get("qualityImprovementProven") is not False:
        raise SystemExit("018A quality must remain unproven")
    replay_gate = source_018c.get("gates", {}).get("developmentRegressionGate", {})
    if replay_gate.get("status") != "HOLD":
        raise SystemExit("018C development gate must remain HOLD")
    if replay_gate.get("checks", {}).get("derNotWorse") is not False:
        raise SystemExit("018C DER non-regression evidence drift")


def validate_authorization(record: dict[str, Any] | None, manifest_digest: str) -> None:
    if record is None:
        raise SystemExit("019A explicit sealed-manifest authorization required")
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != AUTH_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-019A"
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
        or approval.get("aggregateResidencePatchReviewAuthorized") is not True
    ):
        raise SystemExit("019A authorization record invalid")
    for key in PROHIBITED_AUTH_KEYS:
        if approval.get(key) is not False:
            raise SystemExit(f"019A prohibited authorization is not false: {key}")


def review(
    source_018z: dict[str, Any],
    source_018a: dict[str, Any],
    source_018c: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    residence = source_018z["attribution"]["residenceBoundary"]
    geometry = source_018z["geometryCorroboration"]
    replay_checks = source_018c["gates"]["developmentRegressionGate"]["checks"]
    return {
        "schemaVersion": "ocr-ho-v2-019a-residence-patch-review-decision/1.0.0",
        "taskId": "OCR-HO-V2-019A",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "RESIDENCE_PATCH_REVIEW_DECISION_ONLY",
        },
        "sourceDigests": digests,
        "evidence": {
            "residenceBoundary": residence,
            "globalBoundaryRate": geometry["globalDominantBoundaryRate"],
            "globalPatchThresholdReached": geometry["globalPatchThresholdReached"],
            "profileVariantBoundaryCrossTabAvailable": source_018z["attribution"][
                "crossTabAvailable"
            ],
            "shadowPatchQualityImprovementProven": source_018a["review"][
                "qualityImprovementProven"
            ],
            "developmentReplayGate": source_018c["gates"]["developmentRegressionGate"][
                "status"
            ],
            "developmentReplayDerNotWorse": replay_checks["derNotWorse"],
            "developmentReplayResidenceAsciiExactMatch": replay_checks[
                "residenceAsciiExactMatch"
            ],
            "developmentReplayResidenceRoi": source_018c["roiDiagnostics"][
                "automaticDetector"
            ]["placeOfResidence"]["accuracy"],
        },
        "decision": {
            "status": "PATCH_REVIEW_NOT_WARRANTED_HOLD",
            "patchReviewEligible": False,
            "patchAuthorizationIssued": False,
            "profileVariantWinner": None,
            "selectorChanged": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "The field-specific bottom-boundary rate is 3/5, but the global rate is "
                "8/18, the boundary cross-tab is unavailable, and the prior shadow patch "
                "has no proven quality gain while 018C remains HOLD with DER regression."
            ),
            "recommendedNextTask": "OCR-HO-V2-019B",
            "recommendedNextDiagnostic": "INDEPENDENT_RESIDENCE_BOUNDARY_CROSSTAB_REVIEW",
            "nextAction": (
                "Obtain independent boundary/profile cross-tab evidence before any separately "
                "authorized patch review; keep runtime and replay closed."
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
    parser.add_argument("--artifact-018z", type=Path, required=True)
    parser.add_argument("--artifact-018a", type=Path, required=True)
    parser.add_argument("--artifact-018c", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--sealed-manifest-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018z = load(args.artifact_018z)
    source_018a = load(args.artifact_018a)
    source_018c = load(args.artifact_018c)
    authorization = load(args.authorization_record)
    validate_sources(source_018z, source_018a, source_018c)
    validate_authorization(authorization, args.sealed_manifest_digest)
    paths = {
        "artifact018zSha256": args.artifact_018z,
        "artifact018aSha256": args.artifact_018a,
        "artifact018cSha256": args.artifact_018c,
        "authorizationRecordSha256": args.authorization_record,
    }
    report = review(
        source_018z,
        source_018a,
        source_018c,
        {
            **{name: sha256(path) for name, path in paths.items()},
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
                "decision": report["decision"]["status"],
                "patchReviewEligible": report["decision"]["patchReviewEligible"],
                "nextTask": report["decision"]["recommendedNextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
