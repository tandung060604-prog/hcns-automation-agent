#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017K line/token recognizer diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TARGET_FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
LINE_TOKEN_CLASSES = (
    "LINE_ID_MISS",
    "LINE_ORDER_MISMATCH",
    "TOKEN_OMISSION",
    "TOKEN_EXTRA",
    "TOKEN_SWAP",
    "DUPLICATE_LINE",
    "RECOGNIZER_DISAGREEMENT",
    "PARSER_CONTAMINATION",
    "UNCLASSIFIED",
)
FAILURE_CLASSES = set(LINE_TOKEN_CLASSES) - {"UNCLASSIFIED"}
PARSER_SIGNALS = {
    "label_contamination",
    "region_or_line_merge",
    "expiry_fragment",
    "date_fragment",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def nfc_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split())


def tokens(value: Any) -> tuple[str, ...]:
    return tuple(nfc_text(value).split())


def line_ids(candidate: dict[str, Any]) -> tuple[int, ...]:
    raw_ids = candidate.get("lineIds")
    if isinstance(raw_ids, list) and raw_ids:
        return tuple(int(item) for item in raw_ids if item is not None)
    raw_id = candidate.get("lineId")
    return (int(raw_id),) if raw_id is not None else ()


def variant_family(value: Any) -> str:
    value = str(value or "")
    if value.startswith("line") and "_" in value:
        return value.split("_", 1)[1]
    return value


def is_subsequence(shorter: tuple[str, ...], longer: tuple[str, ...]) -> bool:
    iterator = iter(longer)
    return all(any(token == item for item in iterator) for token in shorter)


def token_class(expected: tuple[str, ...], predicted: tuple[str, ...]) -> str:
    if expected == predicted:
        return "EXACT_LINE_TOKEN"
    if len(predicted) < len(expected) and is_subsequence(predicted, expected):
        return "TOKEN_OMISSION"
    if len(predicted) > len(expected) and is_subsequence(expected, predicted):
        return "TOKEN_EXTRA"
    if len(predicted) == len(expected) and sorted(predicted) == sorted(expected):
        return "TOKEN_SWAP"
    return "RECOGNIZER_DISAGREEMENT"


def new_bucket() -> dict[str, Any]:
    return {"groups": 0, "eligible": 0, "classes": Counter(), "signals": Counter()}


def add_class(bucket: dict[str, Any], label: str, *, eligible: bool = False) -> None:
    bucket["groups"] += 1
    bucket["eligible"] += int(eligible)
    if label in LINE_TOKEN_CLASSES:
        bucket["classes"][label] += 1


def normalize_counts(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "groups": value["groups"],
        "eligibleLineTokenGroups": value["eligible"],
        "classCounts": {name: value["classes"].get(name, 0) for name in LINE_TOKEN_CLASSES},
        "signalCounts": {
            "recognizerDisagreement": value["signals"].get("RECOGNIZER_DISAGREEMENT", 0),
            "parserContamination": value["signals"].get("PARSER_CONTAMINATION", 0),
        },
    }


def selected_has_parser_contamination(field: dict[str, Any]) -> bool:
    signals = {str(signal) for signal in field.get("errorSignals", [])}
    return bool(signals.intersection(PARSER_SIGNALS))


def classify_group(
    expected_line_ids: tuple[int, ...],
    expected_text: str,
    candidates: list[dict[str, Any]],
) -> tuple[str, bool]:
    ordered = sorted(
        candidates,
        key=lambda item: (int(item.get("lineOrder", 0)), line_ids(item)),
    )
    observed_ids = tuple(item_id for candidate in ordered for item_id in line_ids(candidate))
    if len(observed_ids) != len(set(observed_ids)):
        return "DUPLICATE_LINE", False
    if not set(expected_line_ids).issubset(set(observed_ids)):
        return "LINE_ID_MISS", False
    if observed_ids != expected_line_ids:
        return "LINE_ORDER_MISMATCH", False
    predicted_text = " ".join(str(item.get("value") or "").strip() for item in ordered).strip()
    return token_class(tokens(expected_text), tokens(predicted_text)), True


def summarize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    return normalize_counts(bucket)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--source-017b", type=Path, required=True)
    parser.add_argument("--source-017i", type=Path, required=True)
    parser.add_argument("--source-017j", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_json(args.sealed_manifest)
    if (
        manifest.get("sealed") is not True
        or manifest.get("immutable") is not True
        or manifest.get("predictionOpened") is not False
        or manifest.get("manifestSha256") != manifest_digest(manifest)
        or len(manifest.get("documents", [])) != 15
    ):
        raise SystemExit("Sealed prediction-blind 15-document manifest required")

    source_017b = load_json(args.source_017b)
    source_017i = load_json(args.source_017i)
    source_017j = load_json(args.source_017j)
    if source_017j.get("decision", {}).get("counterfactualAuthorized") is not False:
        raise SystemExit("017J must deny selector counterfactual authorization")
    candidate_paths = [
        args.data_root
        / "user_uploads-sessions"
        / str(record["sessionId"])
        / "phase11_10_v2_017b"
        / "field_consensus.json"
        for record in manifest["documents"]
    ]
    if not all(path.is_file() for path in candidate_paths):
        raise SystemExit("Complete sealed 017B candidate artifacts are required")

    by_field = {field: new_bucket() for field in TARGET_FIELDS}
    by_profile = defaultdict(new_bucket)
    by_variant = defaultdict(new_bucket)
    aggregate = new_bucket()
    auto_region = Counter()
    for record, candidate_path in zip(manifest["documents"], candidate_paths, strict=True):
        session = args.data_root / "user_uploads-sessions" / str(record["sessionId"])
        ground_truth = load_json(session / "phase10" / "ground_truth.json")["identityFields"]
        artifact = load_json(candidate_path)
        selected_fields = artifact.get("identityCard", {}).get("fields", {})
        for field in TARGET_FIELDS:
            expected = ground_truth[field]
            expected_text = str(
                expected.get("value", "") if isinstance(expected, dict) else expected or ""
            )
            expected_line_ids = tuple(int(item) for item in record["fields"][field]["lineIds"])
            region_ids = tuple(
                int(item)
                for item in (artifact.get("regions", {}).get(field, {}) or {}).get("lineIds") or []
            )
            auto_region["hit" if set(expected_line_ids).issubset(set(region_ids)) else "miss"] += 1
            candidates = [
                item
                for item in (artifact.get("candidates", {}).get(field, []) or [])
                if isinstance(item, dict)
            ]
            groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for candidate in candidates:
                groups[
                    (
                        str(candidate.get("profile") or "unknown"),
                        variant_family(candidate.get("variant")),
                    )
                ].append(candidate)
            field_bucket = by_field[field]
            parser_contamination = selected_has_parser_contamination(
                selected_fields.get(field) or {}
            )
            field_bucket["signals"]["PARSER_CONTAMINATION"] += int(parser_contamination)
            aggregate["signals"]["PARSER_CONTAMINATION"] += int(parser_contamination)
            field_bucket["classes"]["PARSER_CONTAMINATION"] += int(parser_contamination)
            aggregate["classes"]["PARSER_CONTAMINATION"] += int(parser_contamination)
            for (profile, variant), group in groups.items():
                label, eligible = classify_group(expected_line_ids, expected_text, group)
                for bucket in (aggregate, field_bucket, by_profile[profile], by_variant[variant]):
                    add_class(bucket, label, eligible=eligible)
                if label == "RECOGNIZER_DISAGREEMENT":
                    for bucket in (
                        aggregate,
                        field_bucket,
                        by_profile[profile],
                        by_variant[variant],
                    ):
                        bucket["signals"]["RECOGNIZER_DISAGREEMENT"] += 1

    failure_counts = Counter()
    for name, count in aggregate["classes"].items():
        if name in FAILURE_CLASSES:
            failure_counts[name] += count
    eligible_failures = sum(failure_counts.values())
    dominant_category, dominant_count = (None, 0)
    if failure_counts:
        dominant_category, dominant_count = failure_counts.most_common(1)[0]
    dominant_rate = round(dominant_count / max(1, eligible_failures), 6)
    candidate_rule = {
        "dominantCategory": dominant_category,
        "dominantCount": dominant_count,
        "eligibleFailureCount": eligible_failures,
        "dominantRate": dominant_rate,
        "meets50PercentThreshold": dominant_rate >= 0.5,
        "counterfactualAuthorized": False,
    }
    report = {
        "schemaVersion": "ocr-ho-v2-017k-line-token-diagnostic/1.0.0",
        "taskId": "OCR-HO-V2-017K",
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
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "ORACLE_LINE_TOKEN_ATTRIBUTION_ONLY",
        },
        "lineTokenClasses": list(LINE_TOKEN_CLASSES),
        "tokenDefinition": "NFC-normalized whitespace-delimited tokens; no model token IDs",
        "sourceDigests": {
            "sealedManifestSha256": manifest["manifestSha256"],
            "candidate017bSha256": file_sha256(args.source_017b),
            "source017iSha256": file_sha256(args.source_017i),
            "source017jSha256": file_sha256(args.source_017j),
            "candidateArtifactsSha256": candidate_digest(candidate_paths),
        },
        "sourceScope": {
            "source017b": {
                "documentCount": source_017b.get("documentCount"),
                "evaluatedFieldCount": source_017b.get("evaluatedFieldCount"),
            },
            "source017i": {"diagnosticFieldCount": source_017i.get("diagnosticFieldCount")},
            "source017j": {"decision": source_017j.get("decision", {}).get("status")},
        },
        "automaticRegion": {
            "evaluated": 45,
            "hit": auto_region["hit"],
            "miss": auto_region["miss"],
        },
        "aggregate": {
            **summarize_bucket(aggregate),
            "eligibleFailureCount": eligible_failures,
            "dominantCategory": dominant_category,
            "dominantCategoryCount": dominant_count,
            "dominantCategoryRate": dominant_rate,
        },
        "byField": {field: summarize_bucket(bucket) for field, bucket in by_field.items()},
        "byProfile": {
            name: summarize_bucket(bucket) for name, bucket in sorted(by_profile.items())
        },
        "byVariant": {
            name: summarize_bucket(bucket) for name, bucket in sorted(by_variant.items())
        },
        "candidateRule": candidate_rule,
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
            "status": "LINE_TOKEN_DIAGNOSTIC_HOLD",
            "counterfactualAuthorized": False,
            "reason": (
                "Line/token evidence is attribution-only; no selector or runtime change "
                "is authorized in 017K."
            ),
            "nextAction": (
                "Use candidateRule only to scope a separately approved future review; "
                "do not run counterfactual here."
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
                "diagnosticFieldCount": 45,
                "candidateGroupCount": aggregate["groups"],
                "dominantCategory": dominant_category,
                "dominantRate": dominant_rate,
                "counterfactualAuthorized": False,
            }
        )
    )


if __name__ == "__main__":
    main()
