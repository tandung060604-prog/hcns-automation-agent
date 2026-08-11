#!/usr/bin/env python3
"""Run the authorized aggregate-only profile/variant error-class review."""

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
CLASS_KEYS = (
    "LINE_ID_MISS",
    "LINE_ORDER_MISMATCH",
    "TOKEN_OMISSION",
    "TOKEN_EXTRA",
    "TOKEN_SWAP",
    "DUPLICATE_LINE",
    "RECOGNIZER_DISAGREEMENT",
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_scope(source: dict[str, Any], label: str) -> None:
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{label} scope mismatch: {key}")


def validate_018u(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018u-residence-error-class-attribution/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018U"
    ):
        raise SystemExit("018U source schema mismatch")
    validate_scope(source, "018U")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018U must remain sealed and attribution-only")
    if source.get("protocol", {}).get("gate") != "AUTO_DETECTOR":
        raise SystemExit("018U gate protocol mismatch")
    cohort = source.get("evidence", {}).get("residenceAutoRegionHitCohort", {})
    if (
        cohort.get("field") != "placeOfResidence"
        or cohort.get("cohort") != "AUTO_REGION_HIT"
        or cohort.get("classCounts", {}).get("RECOGNIZER_DISAGREEMENT") != 116
        or cohort.get("errorGroupCount") != 160
    ):
        raise SystemExit("018U residence cohort mismatch")
    if source.get("decision", {}).get("selectedDiagnostic") != (
        "RESIDENCE_RECOGNIZER_ERROR_CLASS_ATTRIBUTION"
    ):
        raise SystemExit("018U selected diagnostic mismatch")


def validate_018s(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018s-residence-profile-variant-crosstab-validation/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018S"
    ):
        raise SystemExit("018S source schema mismatch")
    validate_scope(source, "018S")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018S must remain sealed and attribution-only")
    cross_tab = source.get("crossTab", {})
    ceiling = source.get("residenceCeiling", {})
    if (
        cross_tab.get("available") is not True
        or cross_tab.get("residenceSpecific") is not True
        or cross_tab.get("combinationCount") != 16
        or cross_tab.get("evaluatedPerCombination") != 15
        or cross_tab.get("oracleAttributionOnly") is not True
        or ceiling.get("gateAsciiExactCount") != 13
        or ceiling.get("profileOracleBestMaxAsciiExactCount") != 2
        or ceiling.get("variantOracleBestMaxAsciiExactCount") != 2
        or ceiling.get("profileOrVariantReachesGate") is not False
    ):
        raise SystemExit("018S cross-tab ceiling mismatch")
    if len(source.get("profileVariantResidenceRows", [])) != 16:
        raise SystemExit("018S cross-tab row count mismatch")
    decision = source.get("decision", {})
    if (
        decision.get("profileVariantWinner") is not None
        or decision.get("profileSelectorAuthorized") is not False
        or decision.get("variantSelectorAuthorized") is not False
        or decision.get("counterfactualAuthorized") is not False
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
    ):
        raise SystemExit("018S selector boundary mismatch")


def validate_018p(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018p-recognizer-token-attribution/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018P"
    ):
        raise SystemExit("018P source schema mismatch")
    validate_scope(source, "018P")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018P must remain sealed and attribution-only")
    if source.get("protocol", {}).get("gate") != "AUTO_DETECTOR":
        raise SystemExit("018P gate protocol mismatch")
    for cohort_name in ("byProfile", "byVariant"):
        cohorts = source.get(cohort_name, {})
        if len(cohorts) != 4:
            raise SystemExit(f"018P {cohort_name} count mismatch")
        for value in cohorts.values():
            if "autoRegionHit" not in value:
                raise SystemExit(f"018P {cohort_name} aggregate missing")
            if any(key not in value["autoRegionHit"].get("classCounts", {}) for key in CLASS_KEYS):
                raise SystemExit(f"018P {cohort_name} class schema mismatch")


def validate_authorization(
    intake: dict[str, Any],
    source_u_digest: str,
    authorization_record: dict[str, Any],
    authorization_digest: str,
) -> None:
    if (
        intake.get("schemaVersion")
        != "ocr-ho-v2-018v-profile-variant-error-class-authorization-intake/1.0.0"
        or intake.get("taskId") != "OCR-HO-V2-018V"
        or intake.get("authorizationIntake", {}).get("status")
        != "VALID_FOR_PROFILE_VARIANT_ERROR_CLASS_REVIEW"
        or intake.get("decision", {}).get("evidenceReviewExecuted") is not False
        or intake.get("sourceDigests", {}).get("artifact018uSha256")
        != source_u_digest
        or intake.get("sourceDigests", {}).get("authorizationRecordSha256")
        != authorization_digest
    ):
        raise SystemExit("018V authorization intake mismatch")
    if authorization_record.get("approval", {}).get(
        "aggregateProfileVariantErrorClassReviewAuthorized"
    ) is not True:
        raise SystemExit("018V review authorization missing")
    for key in (
        "selectorChangeAuthorized",
        "counterfactualAuthorized",
        "developmentReplayAuthorized",
        "heldoutEvaluationAuthorized",
        "evaluateOnceAuthorized",
        "primaryRuntimeChangeAuthorized",
        "productionPromotionAllowed",
    ):
        if authorization_record.get("approval", {}).get(key) is not False:
            raise SystemExit(f"018V prohibited authorization is not false: {key}")


def compact_class_counts(value: dict[str, Any]) -> dict[str, Any]:
    aggregate = value["autoRegionHit"]
    return {
        "groups": aggregate["groups"],
        "eligibleLineTokenGroups": aggregate["eligibleLineTokenGroups"],
        "errorGroupCount": aggregate["errorGroupCount"],
        "classCounts": {key: aggregate["classCounts"][key] for key in CLASS_KEYS},
        "dominantErrorClass": aggregate["dominantErrorClass"],
        "dominantErrorRate": aggregate["dominantErrorRate"],
    }


def review(
    source_018u: dict[str, Any],
    source_018s: dict[str, Any],
    source_018p: dict[str, Any],
    intake: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    residence = source_018u["evidence"]["residenceAutoRegionHitCohort"]
    profile_aggregates = {
        name: compact_class_counts(value)
        for name, value in source_018p["byProfile"].items()
    }
    variant_aggregates = {
        name: compact_class_counts(value)
        for name, value in source_018p["byVariant"].items()
    }
    ceiling = source_018s["residenceCeiling"]
    return {
        "schemaVersion": "ocr-ho-v2-018v-profile-variant-error-class-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-018V",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "AGGREGATE_PROFILE_VARIANT_BY_ERROR_CLASS_DIAGNOSTIC_ONLY",
        },
        "sourceDigests": digests,
        "authorization": {
            "status": intake["authorizationIntake"]["status"],
            "approverRole": "OCR_REVIEW_OWNER",
            "aggregateProfileVariantErrorClassReviewAuthorized": True,
            "selectorChangeAuthorized": False,
            "counterfactualAuthorized": False,
            "developmentReplayAuthorized": False,
            "heldoutEvaluationAuthorized": False,
            "evaluateOnceAuthorized": False,
            "primaryRuntimeChangeAuthorized": False,
            "productionPromotionAllowed": False,
        },
        "evidence": {
            "residenceErrorClassCohort": {
                "field": "placeOfResidence",
                "cohort": "AUTO_REGION_HIT",
                "groups": residence["groups"],
                "eligibleLineTokenGroups": residence["eligibleLineTokenGroups"],
                "errorGroupCount": residence["errorGroupCount"],
                "classCounts": residence["classCounts"],
                "dominantErrorClass": "RECOGNIZER_DISAGREEMENT",
                "dominantErrorRate": residence[
                    "recognizerDisagreementRateAmongErrorGroups"
                ],
            },
            "residenceProfileVariantCrossTab": {
                "combinationCount": 16,
                "evaluatedPerCombination": 15,
                "gateAsciiExactCount": ceiling["gateAsciiExactCount"],
                "profileOracleBestMaxAsciiExactCount": ceiling[
                    "profileOracleBestMaxAsciiExactCount"
                ],
                "variantOracleBestMaxAsciiExactCount": ceiling[
                    "variantOracleBestMaxAsciiExactCount"
                ],
                "profileOrVariantReachesGate": ceiling[
                    "profileOrVariantReachesGate"
                ],
                "profileVariantWinner": None,
            },
            "allTargetFieldProfileAggregates": {
                "scope": "ALL_TARGET_FIELDS_NOT_RESIDENCE_SPECIFIC",
                "byProfile": profile_aggregates,
                "byVariant": variant_aggregates,
            },
            "jointEvidenceBoundary": {
                "profileVariantByResidenceErrorClassAvailable": False,
                "selectionEligible": False,
                "reason": (
                    "018U supplies residence field-level error classes and 018S supplies "
                    "residence profile/variant exact metrics, while 018P profile/variant "
                    "class aggregates cover all target fields. These artifacts do not "
                    "contain a joint residence profile×variant×error-class table; no "
                    "winner or selector inference is made."
                ),
            },
        },
        "decision": {
            "status": "PROFILE_VARIANT_ERROR_CLASS_REVIEW_HOLD",
            "evidenceReviewExecuted": True,
            "profileVariantByResidenceErrorClassAvailable": False,
            "profileVariantWinner": None,
            "profileSelectorAuthorized": False,
            "variantSelectorAuthorized": False,
            "selectorChanged": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "The authorized aggregate review confirms the source coverage boundary "
                "but cannot create the missing joint residence profile×variant×error-class "
                "evidence. Keep the selector closed and do not treat all-target aggregates "
                "as residence-specific evidence."
            ),
            "nextTask": "OCR-HO-V2-018W",
            "nextAction": (
                "Prepare a separately scoped sealed aggregate extractor for joint residence "
                "profile×variant×error-class attribution; no selector or replay."
            ),
        },
        "gates": {
            "profileVariantErrorClassReviewAuthorized": True,
            "evidenceReviewExecuted": True,
            "developmentRegressionGate": "HOLD",
            "heldoutReadinessGate": "HOLD",
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
            "productionPromotionAllowed": False,
        },
        "lineage": {
            "source018uResidenceErrorClasses": True,
            "source018sResidenceProfileVariantMetrics": True,
            "source018pAllTargetProfileVariantClassAggregates": True,
            "rawPredictionOpened": False,
            "groundTruthUsedAtSelection": False,
            "groundTruthUsedForAttribution": True,
            "selectorChanged": False,
            "counterfactualExecuted": False,
            "replayExecuted": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-018u", type=Path, required=True)
    parser.add_argument("--artifact-018s", type=Path, required=True)
    parser.add_argument("--artifact-018p", type=Path, required=True)
    parser.add_argument("--authorization-intake", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_u = load(args.artifact_018u)
    source_s = load(args.artifact_018s)
    source_p = load(args.artifact_018p)
    intake = load(args.authorization_intake)
    authorization_record = load(args.authorization_record)
    validate_018u(source_u)
    validate_018s(source_s)
    validate_018p(source_p)
    source_u_digest = sha256(args.artifact_018u)
    authorization_digest = sha256(args.authorization_record)
    validate_authorization(intake, source_u_digest, authorization_record, authorization_digest)
    report = review(
        source_u,
        source_s,
        source_p,
        intake,
        {
            "artifact018uSha256": source_u_digest,
            "artifact018sSha256": sha256(args.artifact_018s),
            "artifact018pSha256": sha256(args.artifact_018p),
            "authorizationIntakeSha256": sha256(args.authorization_intake),
            "authorizationRecordSha256": authorization_digest,
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
                "evidenceReviewExecuted": report["decision"]["evidenceReviewExecuted"],
                "jointEvidenceAvailable": report["decision"][
                    "profileVariantByResidenceErrorClassAvailable"
                ],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
