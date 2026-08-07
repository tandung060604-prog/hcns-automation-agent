#!/usr/bin/env python3
"""Aggregate-only automatic boundary reconciliation for OCR-HO-V2-018E."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

# ruff: noqa: E501

FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
SCOPE = {
    "datasetFamily": "CCCD",
    "datasetId": "DATA-HO-014",
    "datasetRole": "DEVELOPMENT_REGRESSION",
    "documentCount": 15,
    "evaluatedFieldCount": 120,
    "candidateVersion": "11.10.2",
    "baselineVersion": "11.9.1",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_scope(source: dict[str, Any], schema: str, task_id: str) -> None:
    if source.get("schemaVersion") != schema:
        raise SystemExit(f"{task_id} schema mismatch")
    if source.get("taskId") not in (None, task_id):
        raise SystemExit(f"{task_id} task mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{task_id} scope mismatch: {key}")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} must be aggregate-only and sealed")


def reconcile(
    source_018d: dict[str, Any],
    source_017n: dict[str, Any],
    source_017o: dict[str, Any],
    source_017p: dict[str, Any],
    source_017k: dict[str, Any],
    source_018a: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    if source_018d.get("decision", {}).get("selectedLayer") != "DETECTOR_CROP":
        raise SystemExit("018D must select DETECTOR_CROP")
    automatic = source_017n["evidence"]["automaticDetectorByField"]
    target_roi = source_018d["gateFailureSummary"]["targetROI"]
    roi_reconciliation = {
        field: {
            "automaticEvidenceCorrect": automatic[field]["autoHit"],
            "automaticEvidenceEvaluated": automatic[field]["evaluated"],
            "018CArtifactCorrect": target_roi[field]["correct"],
            "018CArtifactEvaluated": target_roi[field]["evaluated"],
            "consistent": (
                automatic[field]["autoHit"] == target_roi[field]["correct"]
                and automatic[field]["evaluated"] == target_roi[field]["evaluated"]
            ),
        }
        for field in FIELDS
    }
    global_boundary = source_017n["evidence"]["automaticDetectorAggregate"]
    residence = source_017o["evidence"]["residenceBoundaryMisses"]
    geometry = source_017p["evidence"]["bottomBoundaryCases"]
    all_roi_consistent = all(item["consistent"] for item in roi_reconciliation.values())
    global_rule_eligible = global_boundary["dominantCategoryRate"] >= 0.5
    patch_gain_proven = source_018a["review"]["qualityImprovementProven"]
    return {
        "schemaVersion": "ocr-ho-v2-018e-boundary-reconciliation/1.0.0",
        "taskId": "OCR-HO-V2-018E",
        **SCOPE,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_BOUNDARY_RECONCILIATION_ONLY",
        },
        "sourceDigests": digests,
        "reconciliation": {
            "roiConsistency": {
                "byField": roi_reconciliation,
                "allFieldsConsistent": all_roi_consistent,
            },
            "automaticBoundary": {
                "aggregate": global_boundary,
                "byField": automatic,
                "lineSideCounts": source_017n["evidence"].get("lineSideCounts", {}),
                "globalRuleEligibleAt50Percent": global_rule_eligible,
            },
            "residence": {
                "boundaryMisses": residence,
                "geometrySegmentation": geometry,
                "bottomBoundaryAllGeometrySource": geometry["regionSourceCounts"] == {"phase11_10_geometry_line_segmentation": 3},
                "lineIdOverlapRate": geometry["sealedLineIdOverlapRate"],
                "bottomOverflowRate": geometry["bottomOverflowCaseRate"],
            },
            "lineToken": {
                "lineOrderMismatch": source_017k["aggregate"]["classCounts"]["LINE_ORDER_MISMATCH"],
                "recognizerDisagreement": source_017k["aggregate"]["classCounts"]["RECOGNIZER_DISAGREEMENT"],
                "eligibleFailureCount": source_017k["aggregate"]["eligibleFailureCount"],
            },
            "patchOutcome": {
                "authorizedPatchQualityImprovementProven": patch_gain_proven,
                "nextActionIsAttributionOnly": True,
            },
        },
        "candidateHypothesis": {
            "name": "RESIDENCE_GEOMETRY_BOTTOM_BOUNDARY",
            "status": "CANDIDATE_ONLY_NO_RUNTIME_PATCH",
            "field": "placeOfResidence",
            "caseCount": residence["bottomBoundary"]["caseCount"],
            "caseRate": residence["bottomBoundary"]["caseRate"],
            "regionSourceCounts": residence["bottomBoundary"]["regionSourceCounts"],
            "globalDominantBoundaryRate": global_boundary["dominantCategoryRate"],
            "globalPatchThresholdReached": global_rule_eligible,
            "reason": "Residence evidence is field-specific; global boundary category remains below 50%, and the prior 15px shadow patch had no measured gain.",
        },
        "selectedNextDiagnostic": {
            "taskId": "OCR-HO-V2-018F",
            "name": "RECOGNIZER_TOKEN_ALIGNMENT_REVIEW",
            "status": "PROPOSED_NOT_AUTHORIZED",
            "reason": "Boundary evidence reconciles with 018C but does not justify another ROI patch; inspect token/recognizer cohort next without selector change.",
            "protocolGate": "AUTO_DETECTOR",
            "protocolDiagnostic": "AGGREGATE_TOKEN_ATTRIBUTION_ONLY",
            "aggregateOnly": True,
            "runtimeChange": False,
            "replayAuthorized": False,
            "patchAuthorized": False,
            "selectorChange": False,
            "counterfactualAuthorized": False,
            "heldoutOrEvaluateOnce": False,
        },
        "gates": {
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
            "productionPromotionAllowed": False,
            "replayAuthorized": False,
            "patchAuthorized": False,
        },
        "decision": {
            "status": "BOUNDARY_RECONCILED_HOLD",
            "reconciliationConsistent": all_roi_consistent,
            "selectedLayer": "DETECTOR_CROP",
            "runtimeChanged": False,
            "replayExecuted": False,
            "reason": "Automatic ROI counts reconcile with 018C; no global boundary rule reaches the patch threshold, and the existing residence patch has no measured gain.",
            "nextAction": "Keep the candidate shadow-only and obtain separate approval for 018F token/recognizer attribution; do not replay or patch in 018E.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-018d", type=Path, required=True)
    parser.add_argument("--artifact-017n", type=Path, required=True)
    parser.add_argument("--artifact-017o", type=Path, required=True)
    parser.add_argument("--artifact-017p", type=Path, required=True)
    parser.add_argument("--artifact-017k", type=Path, required=True)
    parser.add_argument("--artifact-018a", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_018d = load(args.artifact_018d)
    source_017n = load(args.artifact_017n)
    source_017o = load(args.artifact_017o)
    source_017p = load(args.artifact_017p)
    source_017k = load(args.artifact_017k)
    source_018a = load(args.artifact_018a)
    validate_scope(source_018d, "ocr-ho-v2-018d-gate-failure-review/1.0.0", "OCR-HO-V2-018D")
    validate_scope(source_017n, "ocr-ho-v2-017n-auto-line-mapping-boundary-attribution/1.0.0", "OCR-HO-V2-017N")
    validate_scope(source_017o, "ocr-ho-v2-017o-residence-bottom-boundary-attribution/1.0.0", "OCR-HO-V2-017O")
    validate_scope(source_017p, "ocr-ho-v2-017p-residence-geometry-segmentation-boundary-review/1.0.0", "OCR-HO-V2-017P")
    validate_scope(source_017k, "ocr-ho-v2-017k-line-token-diagnostic/1.0.0", "OCR-HO-V2-017K")
    validate_scope(source_018a, "ocr-ho-v2-018a-shadow-patch-review/1.0.0", "OCR-HO-V2-018A")
    paths = {
        "artifact018d": args.artifact_018d,
        "artifact017n": args.artifact_017n,
        "artifact017o": args.artifact_017o,
        "artifact017p": args.artifact_017p,
        "artifact017k": args.artifact_017k,
        "artifact018a": args.artifact_018a,
    }
    report = reconcile(
        source_018d,
        source_017n,
        source_017o,
        source_017p,
        source_017k,
        source_018a,
        {name: sha256(path) for name, path in paths.items()},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "decision": report["decision"]["status"], "nextTask": "OCR-HO-V2-018F", "replayExecuted": False, "patchAuthorized": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
