#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017T patch-gate reconciliation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(
    source: dict[str, Any],
    *,
    schema: str,
    task_id: str,
) -> None:
    if (
        source.get("schemaVersion") != schema
        or source.get("taskId") != task_id
        or source.get("datasetFamily") != "CCCD"
        or source.get("datasetId") != "DATA-HO-014"
        or source.get("datasetRole") != "DEVELOPMENT_REGRESSION"
        or source.get("candidateVersion") != "11.10.2"
        or source.get("baselineVersion") != "11.9.1"
        or source.get("documentCount") != 15
        or source.get("evaluatedFieldCount") != 120
        or source.get("diagnosticFieldCount") != 45
    ):
        raise SystemExit(f"{task_id} source scope/schema mismatch")
    if source.get("containsRawPII") is not False:
        raise SystemExit(f"{task_id} must be aggregate-only")
    if source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} prediction must remain sealed")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit(f"{task_id} must not use GroundTruth at selection")


def reconcile_gate(source_017r: dict[str, Any], source_017s: dict[str, Any]) -> dict[str, Any]:
    rule = source_017r["candidateRule"]
    review = source_017r["gateReview"]
    evidence = source_017s["evidenceAssessment"]
    source_inventory = source_017s["sourceInventory"]
    bounded_rule = (
        review.get("boundedRuleGate") == "PASS"
        and 0 < int(rule.get("maxBottomExtensionPixels", 0)) <= 15
        and int(rule.get("preserveMaxValueLines", 0)) == 2
        and rule.get("lineIdRemapping") is False
    )
    independent_evidence = (
        review.get("independentLineIdEvidenceGate") == "HOLD"
        and evidence.get("lineIdEvidenceGate") == "PASS"
        and evidence.get("independentSourceAvailable") is True
        and int(evidence.get("independentDocumentCoverage", 0)) == 15
        and int(evidence.get("independentLineIdOverlapCount", 0)) > 0
        and float(evidence.get("independentLineIdOverlapRate", 0.0)) > 0
        and source_inventory.get("independentFromCandidate") is True
        and source_inventory.get("rawTextConsumed") is False
    )
    reconciled = bounded_rule and independent_evidence
    return {
        "boundedRuleGate": "PASS" if bounded_rule else "HOLD",
        "independentLineIdEvidenceGate": "PASS" if independent_evidence else "HOLD",
        "reconciliationGate": "PASS" if reconciled else "HOLD",
        "boundedRuleSatisfied": bounded_rule,
        "independentEvidenceSatisfied": independent_evidence,
        "qualityImprovementProven": False,
        "explicitPatchApproval": "REQUIRED",
        "patchAuthorized": False,
        "replayAuthorized": False,
        "counterfactualAuthorized": False,
    }


def build_report(
    source_017r: dict[str, Any],
    source_017s: dict[str, Any],
    digest_017r: str,
    digest_017s: str,
) -> dict[str, Any]:
    gate = reconcile_gate(source_017r, source_017s)
    rule = source_017r["candidateRule"]
    evidence = source_017s["evidenceAssessment"]
    report = {
        "schemaVersion": "ocr-ho-v2-017t-patch-gate-reconciliation/1.0.0",
        "taskId": "OCR-HO-V2-017T",
        "candidateVersion": source_017r["candidateVersion"],
        "baselineVersion": source_017r["baselineVersion"],
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "RESIDENCE_GEOMETRY_PATCH_GATE_RECONCILIATION_ONLY",
        },
        "sourceDigests": {
            "artifact017rSha256": digest_017r,
            "artifact017sSha256": digest_017s,
        },
        "candidateRule": {
            "name": rule.get("name"),
            "field": rule.get("field"),
            "maxBottomExtensionPixels": int(rule.get("maxBottomExtensionPixels", 0)),
            "preserveMaxValueLines": int(rule.get("preserveMaxValueLines", 0)),
            "lineIdRemapping": rule.get("lineIdRemapping"),
        },
        "independentEvidence": {
            "source": source_017s["sourceInventory"]["independentSource"],
            "documentCoverage": int(evidence["independentDocumentCoverage"]),
            "lineIdOverlapCount": int(evidence["independentLineIdOverlapCount"]),
            "lineIdOverlapRate": float(evidence["independentLineIdOverlapRate"]),
            "regionAttributionRate": float(
                source_017s["aggregate"]["expectedRegionMappedRate"]
            ),
        },
        "gateReview": gate,
        "decision": {
            "status": (
                "RECONCILED_READY_FOR_EXPLICIT_PATCH_APPROVAL"
                if gate["reconciliationGate"] == "PASS"
                else "PATCH_GATE_RECONCILIATION_HOLD"
            ),
            "recommendedNextTask": (
                "OCR-HO-V2-017U" if gate["reconciliationGate"] == "PASS" else "OCR-HO-V2-017T"
            ),
            "recommendedNextDiagnostic": "EXPLICIT_PATCH_AUTHORIZATION_REVIEW",
            "reason": (
                "The bounded 15-pixel rule and independent line-ID evidence reconcile, "
                "but this diagnostic proves neither quality improvement nor authorization. "
                "Require explicit approval before a minimal runtime patch or replay."
                if gate["reconciliationGate"] == "PASS"
                else (
                    "Rule and independent line-ID evidence did not reconcile; keep patch "
                    "and replay closed."
                )
            ),
            "runtimeChanged": False,
            "patchAuthorized": False,
            "replayAuthorized": False,
            "counterfactualAuthorized": False,
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
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-017r", type=Path, required=True)
    parser.add_argument("--artifact-017s", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_017r = load(args.artifact_017r)
    source_017s = load(args.artifact_017s)
    validate_source(
        source_017r,
        schema="ocr-ho-v2-017r-residence-geometry-patch-gated-review/1.0.0",
        task_id="OCR-HO-V2-017R",
    )
    validate_source(
        source_017s,
        schema="ocr-ho-v2-017s-independent-line-id-mapping-evidence/1.0.0",
        task_id="OCR-HO-V2-017S",
    )
    if source_017s.get("protocol", {}).get("diagnostic") != (
        "INDEPENDENT_LINE_ID_MAPPING_EVIDENCE_ONLY"
    ):
        raise SystemExit("017S diagnostic protocol mismatch")
    if source_017r.get("decision", {}).get("patchAuthorized") is not False:
        raise SystemExit("017R patch authorization must remain denied")
    if source_017r.get("decision", {}).get("replayAuthorized") is not False:
        raise SystemExit("017R replay authorization must remain denied")
    report = build_report(
        source_017r,
        source_017s,
        sha256(args.artifact_017r),
        sha256(args.artifact_017s),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "reconciliationGate": report["gateReview"]["reconciliationGate"],
                "patchAuthorized": False,
                "replayAuthorized": False,
                "nextTask": report["decision"]["recommendedNextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
