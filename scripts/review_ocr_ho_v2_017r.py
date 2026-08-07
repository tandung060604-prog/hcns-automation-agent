#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017R patch-gated review."""

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


def validate_source(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-017q-residence-geometry-minimal-boundary-rule-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-017Q"
        or source.get("datasetFamily") != "CCCD"
        or source.get("datasetId") != "DATA-HO-014"
        or source.get("documentCount") != 15
        or source.get("evaluatedFieldCount") != 120
        or source.get("diagnosticFieldCount") != 45
    ):
        raise SystemExit("017Q source scope/schema mismatch")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit("017Q must be aggregate-only with prediction sealed")


def evaluate_patch_gate(source: dict[str, Any]) -> dict[str, Any]:
    rule = source["candidateRule"]
    bounded_rule = (
        0 < int(rule["maxBottomExtensionPixels"]) <= 15
        and int(rule["preserveMaxValueLines"]) == 2
        and rule["lineIdRemapping"] is False
    )
    line_id_evidence = float(rule["lineIdOverlapRateInEvidence"]) > 0
    return {
        "boundedRuleGate": "PASS" if bounded_rule else "HOLD",
        "independentLineIdEvidenceGate": "PASS" if line_id_evidence else "HOLD",
        "boundedRuleSatisfied": bounded_rule,
        "lineIdEvidenceAvailable": line_id_evidence,
        "patchAuthorized": bounded_rule and line_id_evidence,
        "replayAuthorized": False,
    }


def review(source: dict[str, Any], source_digest: str) -> dict[str, Any]:
    gate_review = evaluate_patch_gate(source)
    return {
        "schemaVersion": "ocr-ho-v2-017r-residence-geometry-patch-gated-review/1.0.0",
        "taskId": "OCR-HO-V2-017R",
        "candidateVersion": source["candidateVersion"],
        "baselineVersion": source["baselineVersion"],
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
            "diagnostic": "RESIDENCE_GEOMETRY_PATCH_GATED_REVIEW_ONLY",
        },
        "sourceDigests": {"artifact017q": source_digest},
        "gateReview": gate_review,
        "candidateRule": source["candidateRule"],
        "decision": {
            "status": "PATCH_GATE_DENIED_LINE_ID_EVIDENCE_HOLD",
            "recommendedNextTask": "OCR-HO-V2-017S",
            "recommendedNextDiagnostic": "INDEPENDENT_LINE_ID_MAPPING_EVIDENCE",
            "reason": (
                "The bounded 15-pixel rule is internally well-defined, but sealed evidence has "
                "zero line-ID overlap. Do not infer that a bbox extension fixes line selection; "
                "obtain independent line-ID mapping evidence first."
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-017q", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.artifact_017q)
    validate_source(source)
    report = review(source, sha256(args.artifact_017q))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "patchAuthorized": False,
                "replayAuthorized": False,
                "nextTask": "OCR-HO-V2-017S",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
