#!/usr/bin/env python3
"""Validate residence-specific profile/variant cross-tab evidence."""

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
TARGET_FIELDS = ["fullName", "placeOfOrigin", "placeOfResidence"]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_018r(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018r-residence-profile-variant-review/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018R"
    ):
        raise SystemExit("018R source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018R source scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
    ):
        raise SystemExit("018R must remain sealed and aggregate-only")
    if source.get("evidenceScope", {}).get(
        "residenceSpecificProfileVariantCrossTabAvailable"
    ) is not False:
        raise SystemExit("018R must record cross-tab as unavailable")
    decision = source.get("decision", {})
    if (
        decision.get("profileVariantWinner") is not None
        or decision.get("profileSelectorAuthorized") is not False
        or decision.get("variantSelectorAuthorized") is not False
        or decision.get("counterfactualAuthorized") is not False
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
    ):
        raise SystemExit("018R selector boundary mismatch")


def compact_metric(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "evaluated": value["evaluated"],
        "strictExactCount": value["strictExactCount"],
        "asciiExactCount": value["asciiExactCount"],
        "characterErrorCount": value["characterErrorCount"],
        "referenceCharacterCount": value["referenceCharacterCount"],
        "diacriticErrorCount": value["diacriticErrorCount"],
        "referenceDiacriticCount": value["referenceDiacriticCount"],
        "strictExactMatch": value["strictExactMatch"],
        "asciiExactMatch": value["asciiExactMatch"],
        "cer": value["cer"],
        "der": value["der"],
    }


def validate_017i(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-017i-recognizer-profile-variant-diagnostic/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-017I"
    ):
        raise SystemExit("017I source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"017I source scope mismatch: {key}")
    if source.get("diagnosticTargetFields") != TARGET_FIELDS:
        raise SystemExit("017I diagnostic target field scope mismatch")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("017I must remain sealed and attribution-only")
    protocols = source.get("protocols", {})
    if (
        protocols.get("gate") != "AUTO_DETECTOR"
        or protocols.get("diagnostic") != "ORACLE_PROFILE_VARIANT_ATTRIBUTION_ONLY"
    ):
        raise SystemExit("017I protocol mismatch")
    combinations = source.get("profileVariantDiagnostics", {})
    if len(combinations) != 16:
        raise SystemExit("017I cross-tab combination count mismatch")
    for name, value in combinations.items():
        residence = value.get("placeOfResidence", {}).get("oracleBest")
        if residence is None or residence.get("evaluated") != 15:
            raise SystemExit(f"017I residence cross-tab row invalid: {name}")
    ceiling = source.get("residenceCeiling", {})
    if (
        ceiling.get("gateAsciiExactCount") != 13
        or ceiling.get("profileOracleBestMaxAsciiExactCount") != 2
        or ceiling.get("variantOracleBestMaxAsciiExactCount") != 2
        or ceiling.get("profileOrVariantReachesGate") is not False
    ):
        raise SystemExit("017I residence ceiling mismatch")
    gates = source.get("gates", {})
    decision = source.get("decision", {})
    if (
        gates.get("developmentRegressionGate") != "HOLD"
        or gates.get("heldoutReadinessGate") != "HOLD"
        or gates.get("schemaErrors") != 0
        or gates.get("sensitiveFalseAcceptance") != 0
        or gates.get("acceptedCoverage") != 0
        or gates.get("manualReviewOnly") is not True
        or gates.get("productionPromotionAllowed") is not False
        or decision.get("runtimeChanged") is not False
        or decision.get("counterfactualReplayAuthorized") is not False
    ):
        raise SystemExit("017I gate or authorization mismatch")


def review(
    source_018r: dict[str, Any], source_017i: dict[str, Any], digests: dict[str, str]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for name, value in source_017i["profileVariantDiagnostics"].items():
        profile, variant = name.split("::", 1)
        rows.append(
            {
                "profile": profile,
                "variant": variant,
                "residence": compact_metric(value["placeOfResidence"]["oracleBest"]),
            }
        )
    rows.sort(
        key=lambda row: (
            -row["residence"]["asciiExactCount"],
            -row["residence"]["strictExactCount"],
            row["residence"]["cer"],
        )
    )
    profile_rows = {
        name: compact_metric(value["placeOfResidence"]["oracleBest"])
        for name, value in source_017i["profileDiagnostics"]["byField"].items()
    }
    variant_rows = {
        name: compact_metric(value["placeOfResidence"]["oracleBest"])
        for name, value in source_017i["variantDiagnostics"]["byField"].items()
    }
    residence_ceiling = source_017i["residenceCeiling"]
    return {
        "schemaVersion": "ocr-ho-v2-018s-residence-profile-variant-crosstab-validation/1.0.0",
        "taskId": "OCR-HO-V2-018S",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "ORACLE_PROFILE_VARIANT_CROSSTAB_ATTRIBUTION_ONLY",
        },
        "sourceDigests": digests,
        "crossTab": {
            "available": True,
            "residenceSpecific": True,
            "combinationCount": len(rows),
            "evaluatedPerCombination": 15,
            "sourceTask": "OCR-HO-V2-017I",
            "oracleAttributionOnly": True,
        },
        "residenceCeiling": {
            "gateAsciiExactCount": residence_ceiling["gateAsciiExactCount"],
            "profileOracleBestMaxAsciiExactCount": residence_ceiling[
                "profileOracleBestMaxAsciiExactCount"
            ],
            "variantOracleBestMaxAsciiExactCount": residence_ceiling[
                "variantOracleBestMaxAsciiExactCount"
            ],
            "profileOrVariantReachesGate": residence_ceiling[
                "profileOrVariantReachesGate"
            ],
        },
        "profileResidenceEvidence": profile_rows,
        "variantResidenceEvidence": variant_rows,
        "profileVariantResidenceRows": rows,
        "decision": {
            "status": "RESIDENCE_PROFILE_VARIANT_CROSSTAB_VALIDATED_HOLD",
            "crossTabValidated": True,
            "profileVariantWinner": None,
            "bestDiagnosticRow": {
                "profile": rows[0]["profile"],
                "variant": rows[0]["variant"],
                "asciiExactCount": rows[0]["residence"]["asciiExactCount"],
                "strictExactCount": rows[0]["residence"]["strictExactCount"],
            },
            "profileSelectorAuthorized": False,
            "variantSelectorAuthorized": False,
            "counterfactualAuthorized": False,
            "selectorPathOpen": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "Residence-specific cross-tab is valid and sealed, but its best oracle "
                "ASCII exact count is 2/15 versus the 13/15 gate. This is attribution "
                "only; do not select a profile/variant or reopen selector."
            ),
            "nextTask": "OCR-HO-V2-018T",
            "nextAction": (
                "Review the validated residence cross-tab ceiling and choose a bounded "
                "non-selector diagnostic; keep selector/replay/runtime closed."
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
        "lineage": {
            "source018rCrossTabAvailable": False,
            "source017iCrossTabValidated": True,
            "rawPredictionOpened": False,
            "groundTruthUsedAtSelection": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-018r", type=Path, required=True)
    parser.add_argument("--artifact-017i", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018r = load(args.artifact_018r)
    source_017i = load(args.artifact_017i)
    validate_018r(source_018r)
    validate_017i(source_017i)
    report = review(
        source_018r,
        source_017i,
        {
            "artifact018rSha256": sha256(args.artifact_018r),
            "artifact017iSha256": sha256(args.artifact_017i),
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
                "crossTabValidated": report["decision"]["crossTabValidated"],
                "bestAsciiExactCount": report["residenceCeiling"][
                    "profileOracleBestMaxAsciiExactCount"
                ],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
