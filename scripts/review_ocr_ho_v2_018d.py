#!/usr/bin/env python3
"""Aggregate-only review of the OCR-HO-V2-018C gate failures."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

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


def validate_source(source: dict[str, Any]) -> None:
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018C source scope mismatch: {key}")
    if (
        source.get("schemaVersion") != "ocr-ho-v2-018c-development-replay/1.0.0"
        or source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("acceptedCoverage") != 0
        or source.get("manualReviewOnly") is not True
        or source.get("productionPromotionAllowed") is not False
    ):
        raise SystemExit("018C must be sealed, aggregate-only and manual-review-only")


def validate_evidence(source: dict[str, Any], expected_schema: str, task_id: str) -> None:
    if source.get("schemaVersion") != expected_schema or source.get("taskId") not in (None, task_id):
        raise SystemExit(f"{task_id} evidence schema mismatch")
    if (
        source.get("datasetFamily") != SCOPE["datasetFamily"]
        or source.get("datasetId") != SCOPE["datasetId"]
        or source.get("documentCount") != SCOPE["documentCount"]
        or source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
    ):
        raise SystemExit(f"{task_id} evidence scope/privacy mismatch")


def review(
    source: dict[str, Any],
    source_digest: str,
    evidence: dict[str, dict[str, Any]],
    evidence_digests: dict[str, str],
) -> dict[str, Any]:
    candidate = source["metrics"]["candidate_11_10_2"]
    baseline = source["metrics"]["baseline_11_9_1"]
    classes = source["errorAnalyzer"]["candidate_11_10_2"]["classCountsByField"]
    roi = source["roiDiagnostics"]["automaticDetector"]
    roi_miss = sum(int(item.get("ROI_MISS", 0)) for item in classes.values())
    residence_boundary = evidence["017O"]["evidence"]["residenceBoundaryMisses"]
    global_boundary = evidence["017O"]["evidence"]["globalBoundaryContext"]
    line_tokens = evidence["017K"]["aggregate"]
    residence_ceiling = evidence["017I"]["residenceCeiling"]
    selector_review = evidence["017D"]
    selector_rule = evidence["017E"]
    selector_replay = evidence["017F"]
    selector_metrics = selector_review.get("metrics", {})
    selector_audit = selector_rule.get("selectionAudit", {})
    replay_audit = selector_replay.get("selectionAudit", {})

    return {
        "schemaVersion": "ocr-ho-v2-018d-gate-failure-review/1.0.0",
        "taskId": "OCR-HO-V2-018D",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_GATE_FAILURE_REVIEW_ONLY",
        },
        "sourceDigests": {
            "artifact018c": source_digest,
            **evidence_digests,
        },
        "gateFailureSummary": {
            "snapshotMatched": source["gates"]["developmentRegressionGate"]["checks"]["snapshotMatched"],
            "exactRegressionCount": source["exactRegressionCount"],
            "derBaseline": baseline["der"],
            "derCandidate": candidate["der"],
            "derReferenceDiacriticCount": source["derBreakdown"]["candidate_11_10_2"]["referenceDiacriticCount"],
            "derDiacriticErrorCount": source["derBreakdown"]["candidate_11_10_2"]["diacriticErrorCount"],
            "targetROI": {
                name: {
                    "correct": item["correct"],
                    "evaluated": item["evaluated"],
                    "accuracy": item["accuracy"],
                }
                for name, item in roi.items()
            },
            "targetAscii": {
                name: source["metrics"]["candidate_11_10_2"]["perField"][name]["asciiExactMatch"]
                for name in ("fullName", "placeOfOrigin", "placeOfResidence")
            },
        },
        "layerEvidence": {
            "DETECTOR_CROP": {
                "status": "SELECTED_FIRST",
                "roiMissCount": roi_miss,
                "residenceROI": roi["placeOfResidence"]["accuracy"],
                "originROI": roi["placeOfOrigin"]["accuracy"],
                "residenceBottomBoundaryRate": residence_boundary["bottomBoundary"]["caseRate"],
                "residenceBottomBoundaryRegionSources": residence_boundary["bottomBoundary"]["regionSourceCounts"],
                "globalBoundaryCategories": global_boundary["categoryCounts"],
                "reason": (
                    "ROI misses are the largest target-field error cohort and both address "
                    "ROI gates fail. Residence bottom-boundary evidence is field-specific, "
                    "while the prior 15px patch produced no measurable gain; inspect mapping "
                    "and bbox reconciliation before any new patch."
                ),
            },
            "READING_ORDER_TOKEN_ALIGNMENT": {
                "status": "DEFERRED_WITHIN_SELECTED_LAYER",
                "lineOrderMismatch": line_tokens["classCounts"]["LINE_ORDER_MISMATCH"],
                "reason": "Line-order evidence exists but is not isolated from the automatic ROI boundary cohort yet.",
            },
            "RECOGNIZER": {
                "status": "DEFERRED",
                "residenceOracleBestAsciiExactCount": residence_ceiling["profileOracleBestMaxAsciiExactCount"],
                "residenceGateAsciiExactCount": residence_ceiling["gateAsciiExactCount"],
                "reason": "No profile/variant oracle reaches the residence gate; selector evidence is non-regressive only when unchanged.",
            },
            "PARSER": {
                "status": "DEFERRED",
                "residenceParserContamination": classes["placeOfResidence"].get("PARSER_CONTAMINATION", 0),
                "reason": "Parser contamination is material but smaller than the combined ROI cohort and must follow boundary attribution.",
            },
            "UNICODE_ASCII": {
                "status": "DEFERRED",
                "candidateDiacriticErrorCount": source["derBreakdown"]["candidate_11_10_2"]["diacriticErrorCount"],
                "reason": "DER is a gate failure, but address ROI and parser/recognizer errors precede normalization changes.",
            },
            "SELECTOR": {
                "status": "CLOSED",
                "counterfactualAuthorized": False,
                "priorCounterfactualDER": selector_metrics.get("counterfactual_017d", {}).get("der"),
                "strictEligibleSwitches": selector_audit.get("eligibleSwitchCount", 0),
                "replayChangedFields": replay_audit.get("changedFieldCount", 0),
                "reason": "Prior counterfactual worsened DER; strict rule/replay produced no eligible switch or field change.",
            },
            "REGRESSION_DER": {
                "status": "GATE_BLOCKER_NOT_SELECTED_LAYER",
                "baselineErrors": source["derBreakdown"]["baseline_11_9_1"]["diacriticErrorCount"],
                "candidateErrors": source["derBreakdown"]["candidate_11_10_2"]["diacriticErrorCount"],
                "reason": "DER remains a release gate and will be rechecked after the selected boundary diagnostic; no DER counterfactual is authorized.",
            },
        },
        "selectedNextDiagnostic": {
            "taskId": "OCR-HO-V2-018E",
            "layer": "DETECTOR_CROP",
            "name": "AUTOMATIC_LINE_MAPPING_BOUNDARY_RECONCILIATION",
            "status": "PROPOSED_NOT_AUTHORIZED",
            "purpose": "Reconcile automatic region bbox, selected line IDs, line order and bottom/top boundary attribution for origin/residence without changing runtime.",
            "protocolGate": "AUTO_DETECTOR",
            "protocolDiagnostic": "AGGREGATE_BOUNDARY_ATTRIBUTION_ONLY",
            "aggregateOnly": True,
            "runtimeChange": False,
            "roiPatchAuthorized": False,
            "selectorChange": False,
            "counterfactualAuthorized": False,
            "replayAuthorized": False,
            "heldoutOrEvaluateOnce": False,
            "acceptanceCriteria": [
                "Keep automatic detector mapping separate from oracle attribution",
                "Report origin/residence boundary side, region source, selected line count and line-order cohorts",
                "Do not modify detector, crop, recognizer, parser, normalization or selector",
                "Keep schema errors and sensitive false acceptance at zero",
                "Keep accepted coverage zero and every field MANUAL_REVIEW",
            ],
        },
        "gates": {
            "counterfactualAuthorized": False,
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
            "productionPromotionAllowed": False,
        },
        "decision": {
            "status": "ONE_LAYER_SELECTED_HOLD",
            "selectedLayer": "DETECTOR_CROP",
            "reason": "Automatic ROI/boundary failure is the largest directly gated cohort; previous 15px patch had no measurable gain, so the next action is attribution-only reconciliation rather than another patch or recognizer selector.",
            "nextAction": "Obtain explicit approval for OCR-HO-V2-018E diagnostic-only boundary reconciliation; do not replay or patch in 018D.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-018c", type=Path, required=True)
    parser.add_argument("--artifact-017i", type=Path, required=True)
    parser.add_argument("--artifact-017k", type=Path, required=True)
    parser.add_argument("--artifact-017m", type=Path, required=True)
    parser.add_argument("--artifact-017n", type=Path, required=True)
    parser.add_argument("--artifact-017o", type=Path, required=True)
    parser.add_argument("--artifact-017p", type=Path, required=True)
    parser.add_argument("--artifact-017d", type=Path, required=True)
    parser.add_argument("--artifact-017e", type=Path, required=True)
    parser.add_argument("--artifact-017f", type=Path, required=True)
    parser.add_argument("--artifact-018a", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.artifact_018c)
    validate_source(source)
    specs = {
        "artifact017i": (args.artifact_017i, "ocr-ho-v2-017i-recognizer-profile-variant-diagnostic/1.0.0", "OCR-HO-V2-017I"),
        "artifact017k": (args.artifact_017k, "ocr-ho-v2-017k-line-token-diagnostic/1.0.0", "OCR-HO-V2-017K"),
        "artifact017m": (args.artifact_017m, "ocr-ho-v2-017m-line-token-cohort-separation/1.0.0", "OCR-HO-V2-017M"),
        "artifact017n": (args.artifact_017n, "ocr-ho-v2-017n-auto-line-mapping-boundary-attribution/1.0.0", "OCR-HO-V2-017N"),
        "artifact017o": (args.artifact_017o, "ocr-ho-v2-017o-residence-bottom-boundary-attribution/1.0.0", "OCR-HO-V2-017O"),
        "artifact017p": (args.artifact_017p, "ocr-ho-v2-017p-residence-geometry-segmentation-boundary-review/1.0.0", "OCR-HO-V2-017P"),
        "artifact017d": (args.artifact_017d, "ocr-ho-v2-017d-selector-counterfactual/1.0.0", "OCR-HO-V2-017D"),
        "artifact017e": (args.artifact_017e, "ocr-ho-v2-017e-selector-rule-review/1.0.0", "OCR-HO-V2-017E"),
        "artifact017f": (args.artifact_017f, "ocr-ho-v2-017f-selector-replay/1.0.0", "OCR-HO-V2-017F"),
        "artifact018a": (args.artifact_018a, "ocr-ho-v2-018a-shadow-patch-review/1.0.0", "OCR-HO-V2-018A"),
    }
    evidence: dict[str, dict[str, Any]] = {}
    digests = {"artifact018c": sha256(args.artifact_018c)}
    for key, (path, schema, task_id) in specs.items():
        item = load(path)
        validate_evidence(item, schema, task_id)
        evidence[task_id.split("-")[-1]] = item
        digests[key] = sha256(path)
    report = review(source, digests["artifact018c"], evidence, digests)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "decision": report["decision"]["status"], "selectedLayer": "DETECTOR_CROP", "nextTask": "OCR-HO-V2-018E", "replayAuthorized": False, "patchAuthorized": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
