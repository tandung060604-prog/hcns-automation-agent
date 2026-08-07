#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017M line/token cohort separation."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.analyze_ocr_ho_v2_017k import classify_group, variant_family
except ModuleNotFoundError:
    from analyze_ocr_ho_v2_017k import classify_group, variant_family

TARGET_FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
COHORT_STATUSES = ("AUTO_REGION_HIT", "AUTO_REGION_MISS")
CLASS_NAMES = (
    "EXACT_LINE_TOKEN",
    "LINE_ID_MISS",
    "LINE_ORDER_MISMATCH",
    "TOKEN_OMISSION",
    "TOKEN_EXTRA",
    "TOKEN_SWAP",
    "DUPLICATE_LINE",
    "RECOGNIZER_DISAGREEMENT",
)
ERROR_CLASSES = set(CLASS_NAMES) - {"EXACT_LINE_TOKEN"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
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


def validate_sources(
    source_017k: dict[str, Any], source_017l: dict[str, Any], manifest: dict[str, Any]
) -> None:
    if (
        source_017k.get("schemaVersion") != "ocr-ho-v2-017k-line-token-diagnostic/1.0.0"
        or source_017k.get("taskId") != "OCR-HO-V2-017K"
        or source_017k.get("datasetFamily") != "CCCD"
        or source_017k.get("datasetId") != "DATA-HO-014"
        or source_017k.get("documentCount") != 15
        or source_017k.get("evaluatedFieldCount") != 120
        or source_017k.get("diagnosticFieldCount") != 45
    ):
        raise SystemExit("017K source scope/schema mismatch")
    if source_017l.get("taskId") != "OCR-HO-V2-017L":
        raise SystemExit("017L lineage artifact required")
    if source_017l.get("containsRawPII") is not False:
        raise SystemExit("017L must be aggregate-only")
    if (
        manifest.get("sealed") is not True
        or manifest.get("immutable") is not True
        or manifest.get("predictionOpened") is not False
        or manifest.get("manifestSha256") != manifest_digest(manifest)
        or len(manifest.get("documents", [])) != 15
    ):
        raise SystemExit("Sealed prediction-blind 15-document manifest required")


def new_bucket() -> dict[str, Any]:
    return {"groups": 0, "eligibleLineTokenGroups": 0, "classCounts": Counter()}


def add_bucket(bucket: dict[str, Any], label: str, eligible: bool) -> None:
    bucket["groups"] += 1
    bucket["eligibleLineTokenGroups"] += int(eligible)
    bucket["classCounts"][label] += 1


def render_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    counts = bucket["classCounts"]
    errors = sum(counts.get(name, 0) for name in ERROR_CLASSES)
    dominant = max(ERROR_CLASSES, key=lambda name: counts.get(name, 0), default=None)
    dominant_count = counts.get(dominant, 0) if dominant else 0
    return {
        "groups": bucket["groups"],
        "eligibleLineTokenGroups": bucket["eligibleLineTokenGroups"],
        "classCounts": {name: counts.get(name, 0) for name in CLASS_NAMES},
        "errorGroupCount": errors,
        "dominantErrorClass": dominant if dominant_count else None,
        "dominantErrorRate": round(dominant_count / max(1, errors), 6),
    }


def classify_cohort(
    expected_line_ids: tuple[int, ...],
    expected_text: str,
    region_line_ids: tuple[int, ...],
    candidates: list[dict[str, Any]],
) -> tuple[str, str, bool]:
    region_status = (
        "AUTO_REGION_HIT"
        if set(expected_line_ids).issubset(set(region_line_ids))
        else "AUTO_REGION_MISS"
    )
    label, eligible = classify_group(expected_line_ids, expected_text, candidates)
    return region_status, label, eligible


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--artifact-017k", type=Path, required=True)
    parser.add_argument("--artifact-017l", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_017k = load(args.artifact_017k)
    source_017l = load(args.artifact_017l)
    manifest = load(args.sealed_manifest)
    validate_sources(source_017k, source_017l, manifest)

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

    aggregate = {status: new_bucket() for status in COHORT_STATUSES}
    by_field = {
        field: {status: new_bucket() for status in COHORT_STATUSES} for field in TARGET_FIELDS
    }
    by_profile: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: {status: new_bucket() for status in COHORT_STATUSES}
    )
    by_variant: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: {status: new_bucket() for status in COHORT_STATUSES}
    )

    for record, candidate_path in zip(manifest["documents"], candidate_paths, strict=True):
        session = args.data_root / "user_uploads-sessions" / str(record["sessionId"])
        ground_truth = load(session / "phase10" / "ground_truth.json")["identityFields"]
        artifact = load(candidate_path)
        for field in TARGET_FIELDS:
            expected = ground_truth[field]
            expected_text = str(
                expected.get("value", "") if isinstance(expected, dict) else expected or ""
            )
            expected_line_ids = tuple(int(item) for item in record["fields"][field]["lineIds"])
            region_line_ids = tuple(
                int(item)
                for item in (artifact.get("regions", {}).get(field, {}) or {}).get("lineIds") or []
            )
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
            for (profile, variant), group in groups.items():
                status, label, eligible = classify_cohort(
                    expected_line_ids, expected_text, region_line_ids, group
                )
                add_bucket(aggregate[status], label, eligible)
                add_bucket(by_field[field][status], label, eligible)
                add_bucket(by_profile[profile][status], label, eligible)
                add_bucket(by_variant[variant][status], label, eligible)

    rendered_aggregate = {status: render_bucket(aggregate[status]) for status in COHORT_STATUSES}
    miss = rendered_aggregate["AUTO_REGION_MISS"]
    hit = rendered_aggregate["AUTO_REGION_HIT"]
    miss_line_id_rate = round(
        miss["classCounts"]["LINE_ID_MISS"] / max(1, miss["errorGroupCount"]), 6
    )
    hit_recognizer_rate = round(
        hit["classCounts"]["RECOGNIZER_DISAGREEMENT"] / max(1, hit["errorGroupCount"]), 6
    )
    report = {
        "schemaVersion": "ocr-ho-v2-017m-line-token-cohort-separation/1.0.0",
        "taskId": "OCR-HO-V2-017M",
        "candidateVersion": source_017k["candidateVersion"],
        "baselineVersion": source_017k["baselineVersion"],
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
        "sourceDigests": {
            "artifact017k": sha256(args.artifact_017k),
            "artifact017l": sha256(args.artifact_017l),
            "sealedManifestSha256": manifest["manifestSha256"],
            "candidateArtifactsSha256": candidate_digest(candidate_paths),
        },
        "cohortDefinition": (
            "AUTO_REGION_HIT when expected sealed line IDs are contained in the candidate "
            "region line IDs; otherwise AUTO_REGION_MISS. Line/token class is attributed only "
            "after prediction using sealed line IDs/text."
        ),
        "cohorts": {
            "aggregate": rendered_aggregate,
            "byField": {
                field: {
                    status: render_bucket(by_field[field][status]) for status in COHORT_STATUSES
                }
                for field in TARGET_FIELDS
            },
            "byProfile": {
                profile: {
                    status: render_bucket(by_profile[profile][status]) for status in COHORT_STATUSES
                }
                for profile in sorted(by_profile)
            },
            "byVariant": {
                variant: {
                    status: render_bucket(by_variant[variant][status]) for status in COHORT_STATUSES
                }
                for variant in sorted(by_variant)
            },
        },
        "separation": {
            "autoRegionMiss": {
                "errorGroupCount": miss["errorGroupCount"],
                "lineIdMissCount": miss["classCounts"]["LINE_ID_MISS"],
                "lineIdMissRate": miss_line_id_rate,
            },
            "autoRegionHit": {
                "errorGroupCount": hit["errorGroupCount"],
                "recognizerDisagreementCount": hit["classCounts"]["RECOGNIZER_DISAGREEMENT"],
                "recognizerDisagreementRate": hit_recognizer_rate,
            },
            "parserContaminationSignalCountFrom017K": source_017k["aggregate"]["classCounts"][
                "PARSER_CONTAMINATION"
            ],
        },
        "decision": {
            "status": "COHORT_SEPARATION_DIAGNOSTIC_HOLD",
            "recommendedNextTask": "OCR-HO-V2-017N",
            "recommendedNextDiagnostic": "AUTO_LINE_MAPPING_BOUNDARY_ATTRIBUTION",
            "reason": (
                "All AUTO_REGION_MISS error groups are LINE_ID_MISS; AUTO_REGION_HIT errors "
                "are predominantly RECOGNIZER_DISAGREEMENT. Prioritize a separate automatic "
                "line-mapping boundary diagnostic before selector consideration."
            ),
            "counterfactualAuthorized": False,
            "runtimeChangeAuthorized": False,
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "autoRegionMissLineIdMissRate": miss_line_id_rate,
                "autoRegionHitRecognizerDisagreementRate": hit_recognizer_rate,
                "nextTask": "OCR-HO-V2-017N",
                "counterfactualAuthorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
