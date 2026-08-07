#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017I recognizer profile/variant diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcns_agent.application.ocr_metrics import edit_distance, evaluate_text_pairs  # noqa: E402

TARGET_FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
PROFILE_NAMES = (
    "easyocr_vi",
    "paddle_ppocrv5",
    "vietocr_vgg_seq2seq",
    "vietocr_vgg_transformer",
)
VARIANT_NAMES = ("color_original", "grayscale_clahe", "lanczos_upscale", "balanced_padding")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_digest(payload: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "manifestSha256"}
    return hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def candidate_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def normalized(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split())


def ascii_normalized(value: Any) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", normalized(value)).casefold()
        if not unicodedata.combining(char)
    )


def variant_family(value: Any) -> str:
    return re.sub(r"^line\d+_", "", str(value or ""))


def gt_value(item: Any) -> str:
    return str(item.get("value", "") if isinstance(item, dict) else item or "")


def candidate_quality(expected: str, candidate: dict[str, Any]) -> tuple[int, int, int, float]:
    predicted = str(candidate.get("value", ""))
    expected_nfc = normalized(expected)
    predicted_nfc = normalized(predicted)
    return (
        int(expected_nfc != predicted_nfc),
        int(ascii_normalized(expected) != ascii_normalized(predicted)),
        edit_distance(tuple(expected_nfc), tuple(predicted_nfc)),
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


def new_group() -> dict[str, Any]:
    return {"candidates": 0, "byDocument": defaultdict(list)}


def summarize_group(group: dict[str, Any]) -> dict[str, Any]:
    by_document = group["byDocument"]
    oracle_pairs: list[tuple[str, str]] = []
    any_strict = 0
    any_ascii = 0
    for expected, candidates in by_document.values():
        if not candidates:
            continue
        any_strict += int(
            any(normalized(expected) == normalized(c.get("value")) for c in candidates)
        )
        any_ascii += int(
            any(ascii_normalized(expected) == ascii_normalized(c.get("value")) for c in candidates)
        )
        best = min(candidates, key=lambda candidate: candidate_quality(expected, candidate))
        oracle_pairs.append((expected, str(best.get("value", ""))))
    return {
        "candidateCount": group["candidates"],
        "evidenceCases": len(oracle_pairs),
        "anyStrictExactCount": any_strict,
        "anyAsciiExactCount": any_ascii,
        "oracleBest": metric_summary(oracle_pairs),
    }


def aggregate_groups(groups: dict[str, dict[str, Any]]) -> dict[str, Any]:
    all_pairs: list[tuple[str, str]] = []
    for group in groups.values():
        by_document = group["byDocument"]
        for expected, candidates in by_document.values():
            if candidates:
                best = min(candidates, key=lambda candidate: candidate_quality(expected, candidate))
                all_pairs.append((expected, str(best.get("value", ""))))
    summary = metric_summary(all_pairs)
    summary["candidateCount"] = sum(group["candidates"] for group in groups.values())
    summary["evidenceCases"] = len(all_pairs)
    return summary


def add_document_candidates(
    group: dict[str, Any], document_index: int, expected: str, candidates: list[dict[str, Any]]
) -> None:
    entry = group["byDocument"].get(document_index)
    if entry is None:
        entry = (expected, [])
        group["byDocument"][document_index] = entry
    entry[1].extend(candidates)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--source-017b", type=Path, required=True)
    parser.add_argument("--source-017c", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_json(args.sealed_manifest)
    if (
        manifest.get("sealed") is not True
        or manifest.get("immutable") is not True
        or manifest.get("predictionOpened") is not False
        or manifest.get("manifestSha256") != manifest_digest(manifest)
    ):
        raise SystemExit("Sealed prediction-blind manifest required")
    if len(manifest.get("documents", [])) != 15:
        raise SystemExit("Expected the canonical 15-document CCCD development scope")

    candidate_paths = [
        args.data_root
        / "user_uploads-sessions"
        / str(record["sessionId"])
        / "phase11_10_v2_017b"
        / "field_consensus.json"
        for record in manifest["documents"]
    ]
    if not all(path.is_file() for path in candidate_paths):
        raise SystemExit("Candidate artifacts are incomplete")

    profile_groups: dict[tuple[str, str], dict[str, Any]] = {}
    variant_groups: dict[tuple[str, str], dict[str, Any]] = {}
    combo_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record, candidate_path in zip(manifest["documents"], candidate_paths, strict=True):
        session = args.data_root / "user_uploads-sessions" / str(record["sessionId"])
        ground_truth = load_json(session / "phase10" / "ground_truth.json")["identityFields"]
        candidate_artifact = load_json(candidate_path)
        candidates_by_field = candidate_artifact.get("candidates", {})
        for field in TARGET_FIELDS:
            expected = gt_value(ground_truth[field])
            candidates = [
                item for item in candidates_by_field.get(field, []) if isinstance(item, dict)
            ]
            grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for candidate in candidates:
                profile = str(candidate.get("profile") or "unknown")
                variant = variant_family(candidate.get("variant"))
                grouped[(profile, variant)].append(candidate)
            for (profile, variant), items in grouped.items():
                profile_group = profile_groups.setdefault((profile, field), new_group())
                variant_group = variant_groups.setdefault((variant, field), new_group())
                combo_group = combo_groups.setdefault((profile, variant, field), new_group())
                for group in (profile_group, variant_group, combo_group):
                    group["candidates"] += len(items)
                add_document_candidates(
                    profile_group,
                    record["documentIndex"],
                    expected,
                    candidates_by_profile(candidates, profile),
                )
                add_document_candidates(
                    variant_group,
                    record["documentIndex"],
                    expected,
                    candidates_by_variant(candidates, variant),
                )
                add_document_candidates(combo_group, record["documentIndex"], expected, items)

    profile_by_field = {
        profile: {
            field: summarize_group(group)
            for (name, field), group in profile_groups.items()
            if name == profile
        }
        for profile in sorted({name for name, _ in profile_groups})
    }
    variant_by_field = {
        variant: {
            field: summarize_group(group)
            for (name, field), group in variant_groups.items()
            if name == variant
        }
        for variant in sorted({name for name, _ in variant_groups})
    }
    combo_by_field: dict[str, dict[str, Any]] = {}
    for (profile, variant, field), group in combo_groups.items():
        combo_by_field.setdefault(f"{profile}::{variant}", {})[field] = summarize_group(group)
    profile_aggregate = {
        profile: aggregate_groups(
            {field: group for (name, field), group in profile_groups.items() if name == profile}
        )
        for profile in sorted({name for name, _ in profile_groups})
    }
    variant_aggregate = {
        variant: aggregate_groups(
            {field: group for (name, field), group in variant_groups.items() if name == variant}
        )
        for variant in sorted({name for name, _ in variant_groups})
    }

    def best_by_field(source: dict[str, dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for field in TARGET_FIELDS:
            options = [(name, values[field]) for name, values in source.items() if field in values]
            if options:
                name, summary = min(
                    options,
                    key=lambda item: (
                        item[1]["oracleBest"]["der"],
                        item[1]["oracleBest"]["cer"],
                        -item[1]["oracleBest"]["strictExactCount"],
                    ),
                )
                result[field] = {
                    "name": name,
                    "oracleBest": summary["oracleBest"],
                    "anyAsciiExactCount": summary["anyAsciiExactCount"],
                }
        return result

    source_017b = load_json(args.source_017b)
    source_017c = load_json(args.source_017c)
    residence_profile_max = max(
        (
            values.get("placeOfResidence", {}).get("oracleBest", {}).get("asciiExactCount", 0)
            for values in profile_by_field.values()
        ),
        default=0,
    )
    residence_variant_max = max(
        (
            values.get("placeOfResidence", {}).get("oracleBest", {}).get("asciiExactCount", 0)
            for values in variant_by_field.values()
        ),
        default=0,
    )
    report = {
        "schemaVersion": "ocr-ho-v2-017i-recognizer-profile-variant-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-017I",
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticTargetFields": list(TARGET_FIELDS),
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocols": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "ORACLE_PROFILE_VARIANT_ATTRIBUTION_ONLY",
        },
        "sourceDigests": {
            "sealedManifestSha256": manifest["manifestSha256"],
            "candidate017bSha256": file_sha256(args.source_017b),
            "source017cSha256": file_sha256(args.source_017c),
            "candidateArtifactsSha256": candidate_digest(candidate_paths),
        },
        "sourceScope": {
            "source017b": {
                "documentCount": source_017b.get("documentCount"),
                "evaluatedFieldCount": source_017b.get("evaluatedFieldCount"),
                "developmentRegressionGate": source_017b.get("gates", {}).get(
                    "developmentRegressionGate"
                ),
            },
            "source017c": {
                "documentCount": source_017c.get("documentCount"),
                "targetEvaluatedFieldCount": source_017c.get("targetEvaluatedFieldCount"),
            },
        },
        "selectedCandidate017c": source_017c.get("selectedCandidateByField", {}),
        "profileDiagnostics": {
            "byField": profile_by_field,
            "aggregate": profile_aggregate,
            "bestByField": best_by_field(profile_by_field),
        },
        "variantDiagnostics": {
            "byField": variant_by_field,
            "aggregate": variant_aggregate,
            "bestByField": best_by_field(variant_by_field),
        },
        "profileVariantDiagnostics": combo_by_field,
        "residenceCeiling": {
            "gateAsciiExactCount": 13,
            "gateAsciiMatch": 0.85,
            "profileOracleBestMaxAsciiExactCount": residence_profile_max,
            "variantOracleBestMaxAsciiExactCount": residence_variant_max,
            "profileOrVariantReachesGate": residence_profile_max >= 13
            or residence_variant_max >= 13,
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
        "decision": {
            "status": "RECOGNIZER_PROFILE_VARIANT_DIAGNOSTIC_HOLD",
            "selectedLayer": "RECOGNIZER_PROFILE_VARIANT_DIAGNOSTIC",
            "runtimeChanged": False,
            "counterfactualReplayAuthorized": False,
            "reason": (
                "No profile or crop-variant oracle reaches the 85% residence ASCII gate; "
                "evidence remains attribution-only."
            ),
            "nextAction": (
                "Review aggregate profile/variant evidence before authorizing any single "
                "selector counterfactual."
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
                "documentCount": 15,
                "diagnosticFieldCount": 45,
                "profileCount": len(profile_by_field),
                "variantCount": len(variant_by_field),
                "residenceProfileMax": residence_profile_max,
                "residenceVariantMax": residence_variant_max,
            },
            ensure_ascii=False,
        )
    )


def candidates_by_profile(candidates: list[dict[str, Any]], profile: str) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if str(candidate.get("profile") or "unknown") == profile
    ]


def candidates_by_variant(candidates: list[dict[str, Any]], variant: str) -> list[dict[str, Any]]:
    return [
        candidate for candidate in candidates if variant_family(candidate.get("variant")) == variant
    ]


if __name__ == "__main__":
    main()
