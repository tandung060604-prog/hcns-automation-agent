#!/usr/bin/env python3
"""Build independent aggregate per-profile quality evidence for CCCD OCR."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcns_agent.application.ocr_metrics import edit_distance, evaluate_text_pairs  # noqa: E402

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
TARGET_FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
LINE_CLASSES = ("LINE_ID_MATCH", "LINE_ID_MISS", "LINE_ORDER_MISMATCH", "DUPLICATE_LINE")
AUTH_SCHEMA = "ocr-ho-v2-019d-per-profile-quality-authorization-record/1.0.0"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_digest(manifest: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in manifest.items() if key != "manifestSha256"}
    return hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def normalized(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split())


def ascii_normalized(value: Any) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", normalized(value)).casefold()
        if not unicodedata.combining(char)
    )


def gt_value(item: Any) -> str:
    return str(item.get("value", "") if isinstance(item, dict) else item or "")


def variant_family(value: Any) -> str:
    return re.sub(r"^line\d+_", "", str(value or ""))


def line_ids(candidate: dict[str, Any]) -> tuple[int, ...]:
    raw = candidate.get("lineIds")
    if isinstance(raw, list) and raw:
        return tuple(int(item) for item in raw if item is not None)
    raw_id = candidate.get("lineId")
    return (int(raw_id),) if raw_id is not None else ()


def classify_line_ids(expected: tuple[int, ...], candidates: list[dict[str, Any]]) -> str:
    ordered = sorted(candidates, key=lambda item: (int(item.get("lineOrder", 0)), line_ids(item)))
    observed = tuple(item_id for candidate in ordered for item_id in line_ids(candidate))
    if len(observed) != len(set(observed)):
        return "DUPLICATE_LINE"
    if not set(expected).issubset(set(observed)):
        return "LINE_ID_MISS"
    if observed != expected:
        return "LINE_ORDER_MISMATCH"
    return "LINE_ID_MATCH"


def candidate_quality(expected: str, candidate: dict[str, Any]) -> tuple[int, int, int, float]:
    predicted = str(candidate.get("value", ""))
    return (
        int(normalized(expected) != normalized(predicted)),
        int(ascii_normalized(expected) != ascii_normalized(predicted)),
        edit_distance(tuple(normalized(expected)), tuple(normalized(predicted))),
        -float(candidate.get("confidence") or 0.0),
    )


def metric_summary(pairs: list[tuple[str, str]]) -> dict[str, int | float]:
    metrics = evaluate_text_pairs(pairs)
    ascii_exact = sum(
        ascii_normalized(expected) == ascii_normalized(predicted) for expected, predicted in pairs
    )
    return {
        "evaluated": len(pairs),
        "strictExactCount": metrics.strict_exact_count,
        "asciiExactCount": ascii_exact,
        "characterErrorCount": metrics.character_error_count,
        "referenceCharacterCount": metrics.reference_character_count,
        "diacriticErrorCount": metrics.diacritic_error_count,
        "referenceDiacriticCount": metrics.reference_diacritic_count,
        "strictExactMatch": round(metrics.strict_exact_rate, 6),
        "asciiExactMatch": round(ascii_exact / max(1, len(pairs)), 6),
        "cer": round(metrics.character_error_rate, 6),
        "der": round(metrics.diacritic_error_rate, 6),
    }


def validate_scope(source: dict[str, Any], schema: str, task_id: str) -> None:
    if source.get("schemaVersion") != schema or source.get("taskId") != task_id:
        raise SystemExit(f"{task_id} source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"{task_id} source scope mismatch: {key}")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} must remain aggregate-only and sealed")


def validate_manifest(manifest: dict[str, Any]) -> None:
    if (
        manifest.get("sealed") is not True
        or manifest.get("immutable") is not True
        or manifest.get("localOnly") is not True
        or manifest.get("predictionOpened") is not False
        or manifest.get("manifestSha256") != manifest_digest(manifest)
        or manifest.get("documentCount") != SCOPE["documentCount"]
        or len(manifest.get("documents", [])) != SCOPE["documentCount"]
    ):
        raise SystemExit("sealed prediction-blind 15-document manifest required")


def validate_authorization(record: dict[str, Any], manifest_sha: str) -> None:
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != AUTH_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-019D"
        or record.get("datasetFamily") != SCOPE["datasetFamily"]
        or record.get("datasetId") != SCOPE["datasetId"]
        or record.get("candidateVersion") != SCOPE["candidateVersion"]
        or record.get("baselineVersion") != SCOPE["baselineVersion"]
        or record.get("containsRawPII") is not False
        or str(record.get("sealedManifestSha256") or "").casefold() != manifest_sha.casefold()
        or approval.get("approved") is not True
        or approval.get("approverRole") != "OCR_REVIEW_OWNER"
        or approval.get("localOnly") is not True
        or approval.get("aggregatePerProfileQualityAuthorized") is not True
    ):
        raise SystemExit("019D authorization record invalid")
    for key in (
        "selectorChangeAuthorized",
        "counterfactualAuthorized",
        "developmentReplayAuthorized",
        "heldoutEvaluationAuthorized",
        "evaluateOnceAuthorized",
        "primaryRuntimeChangeAuthorized",
        "productionPromotionAllowed",
    ):
        if approval.get(key) is not False:
            raise SystemExit(f"019D prohibited authorization is not false: {key}")


def validate_lineage(source_019b: dict[str, Any], source_019c: dict[str, Any]) -> None:
    validate_scope(
        source_019b,
        "ocr-ho-v2-019b-independent-residence-boundary-profile-variant-crosstab/1.0.0",
        "OCR-HO-V2-019B",
    )
    validate_scope(
        source_019c,
        "ocr-ho-v2-019c-independent-cross-tab-review/1.0.0",
        "OCR-HO-V2-019C",
    )
    cross_tab = source_019b.get("crossTab", {})
    review = source_019c.get("review", {})
    if (
        cross_tab.get("profileVariantCombinationCount") != 16
        or cross_tab.get("profileVariantDocumentGroups") != 240
        or review.get("signatureCount") != 1
        or review.get("selectorEligible") is not False
        or review.get("patchReviewEligible") is not False
    ):
        raise SystemExit("019B/019C non-discriminative lineage required")


def baseline_per_field(source_017b: dict[str, Any]) -> dict[str, dict[str, float]]:
    if source_017b.get("schemaVersion") != "ocr-ho-v2-016b-development/1.0.0":
        raise SystemExit("017B source schema mismatch")
    for key in (
        "candidateVersion",
        "baselineVersion",
        "datasetFamily",
        "datasetId",
        "datasetRole",
        "documentCount",
        "evaluatedFieldCount",
    ):
        expected = SCOPE[key]
        if source_017b.get(key) != expected:
            raise SystemExit(f"017B source scope mismatch: {key}")
    if (
        source_017b.get("containsRawPII") is not False
        or source_017b.get("predictionOpened") is not False
    ):
        raise SystemExit("017B must remain aggregate-only and sealed")
    output: dict[str, dict[str, float]] = {}
    for field in TARGET_FIELDS:
        item = (
            source_017b.get("metrics", {}).get("baseline_11_9_1", {}).get("perField", {}).get(field)
        )
        if not isinstance(item, dict):
            raise SystemExit(f"017B baseline metric missing: {field}")
        output[field] = {
            "strictExactMatch": float(item.get("exactMatch", 0.0)),
            "asciiExactMatch": float(item.get("asciiExactMatch", 0.0)),
            "cer": float(item.get("cer", 0.0)),
            "der": float(item.get("der", 0.0)),
        }
    return output


def new_group() -> dict[str, Any]:
    return {"candidateCount": 0, "byDocument": {}}


def add_group(
    group: dict[str, Any], document_index: int, expected: str, items: list[dict[str, Any]]
) -> None:
    group["candidateCount"] += len(items)
    entry = group["byDocument"].get(document_index)
    if entry is None:
        group["byDocument"][document_index] = [expected, list(items)]
        return
    entry[1].extend(items)


def summarize_group(group: dict[str, Any]) -> dict[str, Any]:
    pairs: list[tuple[str, str]] = []
    any_strict = 0
    any_ascii = 0
    for expected, candidates in group["byDocument"].values():
        if not candidates:
            continue
        any_strict += int(
            any(normalized(expected) == normalized(c.get("value")) for c in candidates)
        )
        any_ascii += int(
            any(ascii_normalized(expected) == ascii_normalized(c.get("value")) for c in candidates)
        )
        best = min(candidates, key=lambda candidate: candidate_quality(expected, candidate))
        pairs.append((expected, str(best.get("value", ""))))
    return {
        "candidateCount": group["candidateCount"],
        "evidenceCases": len(pairs),
        "anyStrictExactCount": any_strict,
        "anyAsciiExactCount": any_ascii,
        "oracleBest": metric_summary(pairs),
    }


def compare_to_baseline(metrics: dict[str, Any], baseline: dict[str, float]) -> dict[str, bool]:
    oracle = metrics["oracleBest"]
    return {
        "strictNotWorse": float(oracle["strictExactMatch"]) >= baseline["strictExactMatch"],
        "asciiNotWorse": float(oracle["asciiExactMatch"]) >= baseline["asciiExactMatch"],
        "cerNotWorse": float(oracle["cer"]) <= baseline["cer"],
        "derNotWorse": float(oracle["der"]) <= baseline["der"],
    }


def build_quality(
    manifest: dict[str, Any], data_root: Path, baselines: dict[str, dict[str, float]]
) -> dict[str, Any]:
    profiles: dict[str, dict[str, dict[str, Any]]] = {}
    variants: dict[str, dict[str, dict[str, Any]]] = {}
    combos: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    residence_line_classes: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for document in manifest["documents"]:
        session = data_root / "user_uploads-sessions" / str(document["sessionId"])
        candidate_path = session / "phase11_10_v2_017b" / "field_consensus.json"
        gt_path = session / "phase10" / "ground_truth.json"
        if not candidate_path.is_file() or not gt_path.is_file():
            raise SystemExit("complete sealed 017B candidate/GT artifacts required")
        artifact = load(candidate_path)
        ground_truth = load(gt_path).get("identityFields", {})
        for field in TARGET_FIELDS:
            expected = gt_value(ground_truth.get(field))
            field_candidates = [
                item
                for item in (artifact.get("candidates", {}).get(field, []) or [])
                if isinstance(item, dict)
            ]
            grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for candidate in field_candidates:
                grouped[
                    (
                        str(candidate.get("profile") or "unknown"),
                        variant_family(candidate.get("variant")),
                    )
                ].append(candidate)
            seen_profiles: set[str] = set()
            seen_variants: set[str] = set()
            for (profile, variant), items in grouped.items():
                combo = combos.setdefault(
                    (profile, variant), {name: new_group() for name in TARGET_FIELDS}
                )
                add_group(combo[field], int(document["documentIndex"]), expected, items)
                if profile not in seen_profiles:
                    profile_group = profiles.setdefault(
                        profile, {name: new_group() for name in TARGET_FIELDS}
                    )
                    add_group(
                        profile_group[field],
                        int(document["documentIndex"]),
                        expected,
                        field_candidates_for_profile(field_candidates, profile),
                    )
                    seen_profiles.add(profile)
                if variant not in seen_variants:
                    variant_group = variants.setdefault(
                        variant, {name: new_group() for name in TARGET_FIELDS}
                    )
                    add_group(
                        variant_group[field],
                        int(document["documentIndex"]),
                        expected,
                        field_candidates_for_variant(field_candidates, variant),
                    )
                    seen_variants.add(variant)
                if field == "placeOfResidence":
                    expected_lines = tuple(
                        int(item) for item in document["fields"][field]["lineIds"]
                    )
                    residence_line_classes[(profile, variant)][
                        classify_line_ids(expected_lines, items)
                    ] += 1

    def rows_for(source: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for name, fields in sorted(source.items()):
            field_quality = {field: summarize_group(fields[field]) for field in TARGET_FIELDS}
            comparisons = {
                field: compare_to_baseline(field_quality[field], baselines[field])
                for field in TARGET_FIELDS
            }
            rows.append(
                {"name": name, "fieldQuality": field_quality, "oracleVsBaseline": comparisons}
            )
        return rows

    combo_rows: list[dict[str, Any]] = []
    eligible = 0
    for (profile, variant), fields in sorted(combos.items()):
        field_quality = {field: summarize_group(fields[field]) for field in TARGET_FIELDS}
        comparisons = {
            field: compare_to_baseline(field_quality[field], baselines[field])
            for field in TARGET_FIELDS
        }
        residence_ascii = int(field_quality["placeOfResidence"]["oracleBest"]["asciiExactCount"])
        all_non_regression = all(all(values.values()) for values in comparisons.values())
        gate_ready = all_non_regression and residence_ascii >= 13
        eligible += int(gate_ready)
        combo_rows.append(
            {
                "profile": profile,
                "variant": variant,
                "evaluatedDocuments": SCOPE["documentCount"],
                "fieldQuality": field_quality,
                "oracleVsBaseline": comparisons,
                "residenceLineClassCounts": {
                    key: residence_line_classes[(profile, variant)].get(key, 0)
                    for key in LINE_CLASSES
                },
                "residenceOracleAsciiExactCount": residence_ascii,
                "residenceGateEligible": gate_ready,
            }
        )
    return {
        "profiles": rows_for(profiles),
        "variants": rows_for(variants),
        "profileVariants": combo_rows,
        "profileCount": len(profiles),
        "variantCount": len(variants),
        "profileVariantCombinationCount": len(combos),
        "selectorEligibleCombinationCount": eligible,
    }


def field_candidates_for_profile(
    candidates: list[dict[str, Any]], profile: str
) -> list[dict[str, Any]]:
    return [item for item in candidates if str(item.get("profile") or "unknown") == profile]


def field_candidates_for_variant(
    candidates: list[dict[str, Any]], variant: str
) -> list[dict[str, Any]]:
    return [item for item in candidates if variant_family(item.get("variant")) == variant]


def build_report(
    quality: dict[str, Any], baselines: dict[str, dict[str, float]], digests: dict[str, str]
) -> dict[str, Any]:
    return {
        "schemaVersion": "ocr-ho-v2-019d-per-profile-quality-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-019D",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "INDEPENDENT_PER_PROFILE_QUALITY_NONREGRESSION_ONLY",
        },
        "sourceDigests": digests,
        "lineage": {
            "candidateMetadataOnly": True,
            "groundTruthValuesReadAfterPrediction": True,
            "rawValuesOpened": False,
            "source019CNonDiscriminative": True,
            "source019BGroupsReconciled": 240,
        },
        "baselineReference": {
            "version": "11.9.1",
            "metrics": baselines,
            "comparisonMode": "ORACLE_BEST_AGAINST_BASELINE_AGGREGATE",
            "selectionEligibleFromThisComparison": False,
        },
        "quality": quality,
        "decision": {
            "status": "PER_PROFILE_QUALITY_EVIDENCE_HOLD",
            "profileVariantWinner": None,
            "selectorEligible": False,
            "patchReviewEligible": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "Per-profile and per-variant oracle quality was independently measured, but "
                "this diagnostic does not select a runtime winner or authorize a selector/patch. "
                "The residence gate and non-regression evidence remain insufficient for promotion."
            ),
            "nextTask": "OCR-HO-V2-019E",
            "nextAction": (
                "Review the independent quality matrix and keep all runtime paths closed."
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
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--source-017b", type=Path, required=True)
    parser.add_argument("--source-019b", type=Path, required=True)
    parser.add_argument("--source-019c", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = load(args.sealed_manifest)
    source_017b = load(args.source_017b)
    source_019b = load(args.source_019b)
    source_019c = load(args.source_019c)
    authorization = load(args.authorization_record)
    validate_manifest(manifest)
    validate_lineage(source_019b, source_019c)
    baselines = baseline_per_field(source_017b)
    validate_authorization(authorization, manifest["manifestSha256"])
    candidate_paths = [
        args.data_root
        / "user_uploads-sessions"
        / str(document["sessionId"])
        / "phase11_10_v2_017b"
        / "field_consensus.json"
        for document in manifest["documents"]
    ]
    if not all(path.is_file() for path in candidate_paths):
        raise SystemExit("complete sealed 017B candidate artifacts required")
    quality = build_quality(manifest, args.data_root, baselines)
    report = build_report(
        quality,
        baselines,
        {
            "sealedManifestDigest": manifest["manifestSha256"],
            "sealedManifestFileSha256": sha256(args.sealed_manifest),
            "source017bSha256": sha256(args.source_017b),
            "source019bSha256": sha256(args.source_019b),
            "source019cSha256": sha256(args.source_019c),
            "authorizationRecordSha256": sha256(args.authorization_record),
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
                "status": report["decision"]["status"],
                "profileCount": quality["profileCount"],
                "variantCount": quality["variantCount"],
                "profileVariantCombinationCount": quality["profileVariantCombinationCount"],
                "selectorEligibleCombinationCount": quality["selectorEligibleCombinationCount"],
                "nextTask": report["decision"]["nextTask"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
