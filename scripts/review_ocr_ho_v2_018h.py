#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-018H selector safety-evidence review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.review_ocr_ho_v2_018g import load, sha256, validate_source
except ModuleNotFoundError:
    from review_ocr_ho_v2_018g import load, sha256, validate_source


def review(source: dict[str, Any], source_digest: str) -> dict[str, Any]:
    criteria = source["openingCriteria"]
    gates = source["gates"]
    safety = {
        "sealedAggregateLineage": {
            "status": "PASS",
            "sourceArtifact": "OCR-HO-V2-018G",
            "predictionOpened": source["predictionOpened"],
            "gtUsedAtSelection": source["gtUsedAtSelection"],
        },
        "recognizerDominantEvidence": {
            "status": criteria["recognizerDominantEvidence"]["status"],
            "observedRate": criteria["recognizerDominantEvidence"]["observedRate"],
        },
        "nonRegressionEvidence": {
            "status": criteria["priorCounterfactualNonRegression"]["status"],
            "derDelta": criteria["priorCounterfactualNonRegression"]["derDelta"],
            "diacriticErrorDelta": criteria["priorCounterfactualNonRegression"][
                "diacriticErrorDelta"
            ],
        },
        "eligibleSwitchEvidence": {
            "status": criteria["strictRuleEligibleSwitch"]["status"],
            "eligibleSwitchCount": criteria["strictRuleEligibleSwitch"][
                "eligibleSwitchCount"
            ],
        },
        "replayChangeEvidence": {
            "status": criteria["replayChangedFieldEvidence"]["status"],
            "changedFieldCount": criteria["replayChangedFieldEvidence"]["changedFieldCount"],
        },
        "ownerAuthorization": {
            "status": "HOLD",
            "present": False,
            "required": "Explicit selector safety-evidence authorization record",
        },
        "safetyInvariants": {
            "status": "PASS",
            "schemaErrors": gates["schemaErrors"],
            "sensitiveFalseAcceptance": gates["sensitiveFalseAcceptance"],
            "acceptedCoverage": gates["acceptedCoverage"],
            "manualReviewOnly": gates["manualReviewOnly"],
        },
    }
    ready = all(item["status"] == "PASS" for item in safety.values())
    return {
        "schemaVersion": "ocr-ho-v2-018h-selector-safety-evidence-review/1.0.0",
        "taskId": "OCR-HO-V2-018H",
        "candidateVersion": source["candidateVersion"],
        "baselineVersion": source["baselineVersion"],
        "datasetFamily": source["datasetFamily"],
        "datasetId": source["datasetId"],
        "datasetRole": source["datasetRole"],
        "documentCount": source["documentCount"],
        "evaluatedFieldCount": source["evaluatedFieldCount"],
        "diagnosticFieldCount": source["diagnosticFieldCount"],
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_SELECTOR_SAFETY_EVIDENCE_REVIEW_ONLY",
        },
        "sourceDigests": {"artifact018gSha256": source_digest},
        "safetyEvidence": safety,
        "readiness": {
            "independentSafetyEvidenceReady": ready,
            "counterfactualOpeningAllowed": False,
            "counterfactualAuthorized": False,
            "runtimeChangeAuthorized": False,
            "replayAuthorized": False,
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
            "status": "SELECTOR_SAFETY_EVIDENCE_HOLD",
            "reason": (
                "018G confirms recognizer dominance but does not provide non-regression, "
                "eligible-switch or changed-field evidence. A separate authorization record "
                "is also absent; keep the selector counterfactual closed."
            ),
            "nextTask": "OCR-HO-V2-018I",
            "nextAction": (
                "Obtain an explicit selector safety-evidence authorization record before any "
                "new diagnostic or counterfactual; do not run one in 018H."
            ),
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-018g", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = load(args.artifact_018g)
    validate_source(
        source,
        "ocr-ho-v2-018g-selector-counterfactual-review/1.0.0",
        "OCR-HO-V2-018G",
        diagnostic_fields=45,
    )
    if source.get("selectorOpening", {}).get("allowed") is not False:
        raise SystemExit("018G must deny selector opening")
    if source.get("decision", {}).get("counterfactualAuthorized") is not False:
        raise SystemExit("018G counterfactual must remain unauthorized")
    report = review(source, sha256(args.artifact_018g))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "independentSafetyEvidenceReady": report["readiness"][
                    "independentSafetyEvidenceReady"
                ],
                "counterfactualAuthorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
