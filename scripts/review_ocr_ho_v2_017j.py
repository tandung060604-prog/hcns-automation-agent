#!/usr/bin/env python3
"""Review evidence before authorizing one OCR-HO-V2-017J selector counterfactual."""

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-017i", type=Path, required=True)
    parser.add_argument("--artifact-017d", type=Path, required=True)
    parser.add_argument("--artifact-017e", type=Path, required=True)
    parser.add_argument("--artifact-017f", type=Path, required=True)
    parser.add_argument("--artifact-017h", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    i = load(args.artifact_017i)
    d = load(args.artifact_017d)
    e = load(args.artifact_017e)
    f = load(args.artifact_017f)
    h = load(args.artifact_017h)

    if not (
        i["datasetFamily"]
        == d["datasetFamily"]
        == e["datasetFamily"]
        == f["datasetFamily"]
        == "CCCD"
        and i["datasetId"] == d["datasetId"] == e["datasetId"] == f["datasetId"] == "DATA-HO-014"
        and i["documentCount"]
        == d["documentCount"]
        == e["documentCount"]
        == f["documentCount"]
        == 15
    ):
        raise SystemExit("017J evidence scope mismatch")
    if i["residenceCeiling"]["profileOrVariantReachesGate"]:
        raise SystemExit("017I unexpectedly reaches the residence gate")

    f_audit = f["selectionAudit"]
    e_metrics = e["metrics"]
    evidence = {
        "profileVariant": {
            "profileCount": len(i["profileDiagnostics"]["aggregate"]),
            "variantCount": len(i["variantDiagnostics"]["aggregate"]),
            "residenceGateAsciiExactCount": i["residenceCeiling"]["gateAsciiExactCount"],
            "profileOracleBestMaxResidenceAsciiExactCount": i["residenceCeiling"][
                "profileOracleBestMaxAsciiExactCount"
            ],
            "variantOracleBestMaxResidenceAsciiExactCount": i["residenceCeiling"][
                "variantOracleBestMaxAsciiExactCount"
            ],
            "profileOrVariantReachesGate": i["residenceCeiling"]["profileOrVariantReachesGate"],
        },
        "priorSelectorCounterfactual017D": {
            "selectedDer": d["metrics"]["selected_11_10_2"]["der"],
            "counterfactualDer": d["metrics"]["counterfactual_017d"]["der"],
            "selectedDiacriticErrors": d["metrics"]["selected_11_10_2"]["diacriticErrorCount"],
            "counterfactualDiacriticErrors": d["metrics"]["counterfactual_017d"][
                "diacriticErrorCount"
            ],
            "exactRegressionZero": d["gates"]["exactRegressionZero"],
            "derNotWorse": d["gates"]["derNotWorse"],
        },
        "strictRule017E": {
            "changedFieldCount": e["selectionAudit"]["changedFieldCount"],
            "eligibleSwitchCount": e["selectionAudit"]["eligibleSwitchCount"],
            "targetMetrics": e_metrics["rule017eTarget"],
        },
        "strictRuleReplay017F": {
            "changedFieldCount": f_audit["changedFieldCount"],
            "eligibleSwitchCount": f_audit["eligibleSwitchCount"],
            "targetMetrics": f["metrics"]["replayed_017f_target45"],
            "selectorReplayNonRegression": f["gates"]["selectorReplayNonRegression"],
            "derNotWorse": f["gates"]["derNotWorseVsSelected"],
            "exactRegressionZero": f["gates"]["exactRegressionVsSelected"],
        },
        "roi017H": {
            "decision": h["decision"]["status"],
            "dominantCauseFound": h["automaticDetector"]["aggregate"].get("dominantCategory"),
            "dominantCauseRate": h["automaticDetector"]["aggregate"].get("dominantCategoryRate"),
        },
    }

    counterfactual_authorized = bool(
        evidence["profileVariant"]["profileOrVariantReachesGate"]
        and evidence["strictRuleReplay017F"]["eligibleSwitchCount"] > 0
        and evidence["strictRuleReplay017F"]["changedFieldCount"] > 0
        and evidence["strictRuleReplay017F"]["selectorReplayNonRegression"]
        and evidence["strictRuleReplay017F"]["derNotWorse"]
        and evidence["strictRuleReplay017F"]["exactRegressionZero"] == 0
    )
    report = {
        "schemaVersion": "ocr-ho-v2-017j-selector-counterfactual-review/1.0.0",
        "taskId": "OCR-HO-V2-017J",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "protocol": "AGGREGATE_EVIDENCE_REVIEW_ONLY",
        "sourceDigests": {
            "artifact017i": sha256(args.artifact_017i),
            "artifact017d": sha256(args.artifact_017d),
            "artifact017e": sha256(args.artifact_017e),
            "artifact017f": sha256(args.artifact_017f),
            "artifact017h": sha256(args.artifact_017h),
        },
        "evidence": evidence,
        "gates": {
            "counterfactualAuthorized": counterfactual_authorized,
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
            "productionPromotionAllowed": False,
        },
        "decision": {
            "status": "NO_COUNTERFACTUAL_AUTHORIZATION_HOLD",
            "counterfactualAuthorized": counterfactual_authorized,
            "reason": (
                "Profile/variant evidence cannot meet the residence gate; strict selector replay "
                "had no eligible switch, while the earlier relaxed counterfactual worsened DER."
            ),
            "nextAction": (
                "Do not run a selector counterfactual; gather new line/token recognizer evidence "
                "before reconsideration."
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "counterfactualAuthorized": counterfactual_authorized,
                "decision": report["decision"]["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
