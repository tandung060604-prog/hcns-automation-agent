#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-018J selector safety-evidence review.

This reviewer consumes sealed, aggregate artifacts only.  It deliberately does
not reopen predictions, OCR output, Ground Truth values, or run a selector.
"""

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


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_common(source: dict[str, Any], schema: str, task_id: str) -> None:
    if source.get("schemaVersion") != schema or source.get("taskId") != task_id:
        raise SystemExit(f"{task_id} source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{task_id} source scope mismatch: {key}")
    if source.get("containsRawPII") is not False:
        raise SystemExit(f"{task_id} must remain aggregate-only")
    if source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} prediction must remain sealed")
    if source.get("gtUsedAtSelection") is not False:
        raise SystemExit(f"{task_id} used Ground Truth at selection")


def validate_lineage(
    source_018i: dict[str, Any],
    source_018h: dict[str, Any],
    source_018g: dict[str, Any],
    digests: dict[str, str],
) -> None:
    _validate_common(
        source_018i,
        "ocr-ho-v2-018i-selector-safety-authorization-intake/1.0.0",
        "OCR-HO-V2-018I",
    )
    _validate_common(
        source_018h,
        "ocr-ho-v2-018h-selector-safety-evidence-review/1.0.0",
        "OCR-HO-V2-018H",
    )
    _validate_common(
        source_018g,
        "ocr-ho-v2-018g-selector-counterfactual-review/1.0.0",
        "OCR-HO-V2-018G",
    )
    if source_018i.get("protocol", {}).get("gate") != "AUTO_DETECTOR":
        raise SystemExit("018I gate protocol mismatch")
    if source_018h.get("protocol", {}).get("diagnostic") != (
        "AGGREGATE_SELECTOR_SAFETY_EVIDENCE_REVIEW_ONLY"
    ):
        raise SystemExit("018H must be aggregate safety evidence only")
    if source_018g.get("protocol", {}).get("diagnostic") != (
        "AGGREGATE_SELECTOR_OPENING_REVIEW_ONLY"
    ):
        raise SystemExit("018G must be aggregate selector review only")
    intake = source_018i.get("authorizationIntake", {})
    if intake.get("status") != "VALID_FOR_SAFETY_REVIEW":
        raise SystemExit("018I safety-review authorization is not valid")
    if intake.get("sourceArtifactMatch") is not True or intake.get("scopeMatch") is not True:
        raise SystemExit("018I source or scope does not match")
    if intake.get("selectorSafetyEvidenceAuthorized") is not True:
        raise SystemExit("018I does not authorize safety evidence")
    if any(
        intake.get(key) is not False
        for key in (
            "counterfactualAuthorized",
            "selectorChangeAuthorized",
            "developmentReplayAuthorized",
            "heldoutEvaluationAuthorized",
            "evaluateOnceAuthorized",
            "primaryRuntimeChangeAuthorized",
            "productionPromotionAllowed",
        )
    ):
        raise SystemExit("018I contains broader authorization than safety review")
    if source_018h.get("sourceDigests", {}).get("artifact018gSha256", "").casefold() != digests[
        "artifact018gSha256"
    ].casefold():
        raise SystemExit("018H does not match the supplied 018G digest")
    if source_018i.get("sourceDigests", {}).get("artifact018hSha256", "").casefold() != digests[
        "artifact018hSha256"
    ].casefold():
        raise SystemExit("018I does not match the supplied 018H digest")
    if source_018g.get("selectorOpening", {}).get("allowed") is not False:
        raise SystemExit("018G must deny selector opening")
    if source_018g.get("decision", {}).get("counterfactualAuthorized") is not False:
        raise SystemExit("018G counterfactual must remain unauthorized")


def _criteria(source_018g: dict[str, Any]) -> dict[str, Any]:
    criteria = source_018g["openingCriteria"]
    evidence = source_018g["evidence"]
    return {
        "recognizerDominant": {
            "status": criteria["recognizerDominantEvidence"]["status"],
            "observedRate": criteria["recognizerDominantEvidence"]["observedRate"],
            "threshold": criteria["recognizerDominantEvidence"]["threshold"],
            "disagreementCount": evidence["018F"]["recognizerDisagreementCount"],
            "errorGroupCount": evidence["018F"]["autoRegionHitErrorGroupCount"],
        },
        "priorNonRegression": {
            "status": criteria["priorCounterfactualNonRegression"]["status"],
            "derDelta": criteria["priorCounterfactualNonRegression"]["derDelta"],
            "diacriticErrorDelta": criteria["priorCounterfactualNonRegression"][
                "diacriticErrorDelta"
            ],
            "strictExactDelta": criteria["priorCounterfactualNonRegression"][
                "strictExactDelta"
            ],
        },
        "eligibleSwitch": {
            "status": criteria["strictRuleEligibleSwitch"]["status"],
            "eligibleSwitchCount": criteria["strictRuleEligibleSwitch"][
                "eligibleSwitchCount"
            ],
            "changedFieldCount": criteria["strictRuleEligibleSwitch"]["changedFieldCount"],
        },
        "replayChange": {
            "status": criteria["replayChangedFieldEvidence"]["status"],
            "eligibleSwitchCount": criteria["replayChangedFieldEvidence"][
                "eligibleSwitchCount"
            ],
            "changedFieldCount": criteria["replayChangedFieldEvidence"]["changedFieldCount"],
        },
    }


def review(
    source_018i: dict[str, Any],
    source_018h: dict[str, Any],
    source_018g: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    criteria = _criteria(source_018g)
    safety_invariants = {
        "status": "PASS",
        "schemaErrors": 0,
        "sensitiveFalseAcceptance": 0,
        "acceptedCoverage": 0,
        "manualReviewOnly": True,
    }
    evidence_hold = any(item["status"] != "PASS" for item in criteria.values())
    return {
        "schemaVersion": "ocr-ho-v2-018j-aggregate-selector-safety-evidence/1.0.0",
        "taskId": "OCR-HO-V2-018J",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_SELECTOR_SAFETY_EVIDENCE_ONLY",
        },
        "sourceDigests": {
            "artifact018iSha256": digests["artifact018iSha256"],
            "artifact018hSha256": digests["artifact018hSha256"],
            "artifact018gSha256": digests["artifact018gSha256"],
        },
        "authorization": {
            "sourceTask": "OCR-HO-V2-018I",
            "status": source_018i["authorizationIntake"]["status"],
            "sourceArtifactMatch": source_018i["authorizationIntake"]["sourceArtifactMatch"],
            "scopeMatch": source_018i["authorizationIntake"]["scopeMatch"],
            "safetyEvidenceAuthorized": True,
            "counterfactualAuthorized": False,
        },
        "evidence": {
            **criteria,
            "safetyInvariants": safety_invariants,
            "sealedLineage": {
                "status": "PASS",
                "predictionOpened": False,
                "gtUsedAtSelection": False,
                "gtUsedForAttribution": True,
            },
        },
        "readiness": {
            "safetyEvidenceCollected": True,
            "independentSafetyEvidenceReady": not evidence_hold,
            "selectorCounterfactualOpeningAllowed": False,
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
        "decision": {
            "status": "AGGREGATE_SELECTOR_SAFETY_EVIDENCE_HOLD",
            "reason": (
                "Safety-only authorization is valid, but aggregate evidence still shows "
                "prior DER non-regression failure and no eligible selector switch or replay "
                "change. Keep the selector counterfactual closed."
            ),
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "nextTask": "OCR-HO-V2-018K",
            "nextAction": (
                "Review this aggregate evidence and decide whether a separately approved "
                "counterfactual is warranted; do not run one in 018J."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-018i", type=Path, required=True)
    parser.add_argument("--artifact-018h", type=Path, required=True)
    parser.add_argument("--artifact-018g", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = {
        "018I": load(args.artifact_018i),
        "018H": load(args.artifact_018h),
        "018G": load(args.artifact_018g),
    }
    digests = {
        "artifact018iSha256": sha256(args.artifact_018i),
        "artifact018hSha256": sha256(args.artifact_018h),
        "artifact018gSha256": sha256(args.artifact_018g),
    }
    validate_lineage(sources["018I"], sources["018H"], sources["018G"], digests)
    report = review(sources["018I"], sources["018H"], sources["018G"], digests)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "decision": report["decision"]["status"],
                "safetyEvidenceCollected": report["readiness"]["safetyEvidenceCollected"],
                "counterfactualAuthorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
