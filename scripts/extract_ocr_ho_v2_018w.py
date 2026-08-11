#!/usr/bin/env python3
"""Extract sealed joint residence profile/variant error classes, fail-closed."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:
    from scripts.analyze_ocr_ho_v2_017k import (
        classify_group,
        load_json,
        manifest_digest,
        variant_family,
    )
except ModuleNotFoundError:
    from analyze_ocr_ho_v2_017k import (
        classify_group,
        load_json,
        manifest_digest,
        variant_family,
    )

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
TARGET_FIELD = "placeOfResidence"
ERROR_CLASSES = (
    "LINE_ID_MISS",
    "LINE_ORDER_MISMATCH",
    "TOKEN_OMISSION",
    "TOKEN_EXTRA",
    "TOKEN_SWAP",
    "DUPLICATE_LINE",
    "RECOGNIZER_DISAGREEMENT",
)
AUTH_SCHEMA = "ocr-ho-v2-018w-sealed-joint-extractor-authorization-record/1.0.0"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_018v(source: dict[str, Any]) -> None:
    if (
        source.get("schemaVersion")
        != "ocr-ho-v2-018v-profile-variant-error-class-diagnostic/1.0.0"
        or source.get("taskId") != "OCR-HO-V2-018V"
    ):
        raise SystemExit("018V source schema mismatch")
    for key, expected in SCOPE.items():
        if source.get(key) != expected:
            raise SystemExit(f"018V scope mismatch: {key}")
    if (
        source.get("containsRawPII") is not False
        or source.get("predictionOpened") is not False
        or source.get("gtUsedAtSelection") is not False
        or source.get("gtUsedForAttribution") is not True
    ):
        raise SystemExit("018V must remain aggregate-only")
    if source.get("authorization", {}).get(
        "aggregateProfileVariantErrorClassReviewAuthorized"
    ) is not True:
        raise SystemExit("018V review authorization missing")
    decision = source.get("decision", {})
    if (
        decision.get("evidenceReviewExecuted") is not True
        or decision.get("selectorChanged") is not False
        or decision.get("counterfactualAuthorized") is not False
        or decision.get("runtimeChanged") is not False
        or decision.get("replayExecuted") is not False
        or decision.get("heldoutOpened") is not False
        or decision.get("promotionAllowed") is not False
    ):
        raise SystemExit("018V authorization boundary mismatch")


def validate_manifest(manifest: dict[str, Any]) -> None:
    if (
        manifest.get("sealed") is not True
        or manifest.get("immutable") is not True
        or manifest.get("localOnly") is not True
        or manifest.get("predictionOpened") is not False
        or manifest.get("manifestSha256") != manifest_digest(manifest)
        or manifest.get("documentCount") != 15
        or len(manifest.get("documents", [])) != 15
    ):
        raise SystemExit("sealed prediction-blind 15-document manifest required")


def validate_authorization(record: dict[str, Any] | None, manifest_sha: str) -> None:
    if record is None:
        raise SystemExit("018W explicit sealed-extractor authorization required")
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != AUTH_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-018W"
        or record.get("datasetFamily") != SCOPE["datasetFamily"]
        or record.get("datasetId") != SCOPE["datasetId"]
        or record.get("candidateVersion") != SCOPE["candidateVersion"]
        or record.get("baselineVersion") != SCOPE["baselineVersion"]
        or record.get("containsRawPII") is not False
        or str(record.get("sealedManifestSha256") or "").casefold()
        != manifest_sha.casefold()
        or approval.get("approved") is not True
        or not str(approval.get("approverRole") or "").strip()
        or approval.get("localOnly") is not True
        or approval.get("aggregateExtractorExecutionAuthorized") is not True
    ):
        raise SystemExit("018W authorization record invalid")
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
            raise SystemExit(f"018W prohibited authorization is not false: {key}")


def build_joint_table(
    group_records: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for record in group_records:
        profile = str(record.get("profile") or "unknown")
        variant = str(record.get("variant") or "unknown")
        key = f"{profile}::{variant}"
        row = table.setdefault(
            key,
            {
                "profile": profile,
                "variant": variant,
                "evaluatedDocuments": 0,
                "groups": 0,
                "eligibleLineTokenGroups": 0,
                "classCounts": Counter(),
            },
        )
        row["evaluatedDocuments"] += int(record.get("documentEvaluated", False))
        row["groups"] += 1
        row["eligibleLineTokenGroups"] += int(record.get("eligible", False))
        label = str(record.get("label") or "UNCLASSIFIED")
        if label in ERROR_CLASSES:
            row["classCounts"][label] += 1
    output: dict[str, dict[str, Any]] = {}
    for key, row in sorted(table.items()):
        counts = {name: row["classCounts"].get(name, 0) for name in ERROR_CLASSES}
        total_errors = sum(counts.values())
        dominant = max(counts, key=counts.get) if total_errors else None
        output[key] = {
            "profile": row["profile"],
            "variant": row["variant"],
            "evaluatedDocuments": row["evaluatedDocuments"],
            "groups": row["groups"],
            "eligibleLineTokenGroups": row["eligibleLineTokenGroups"],
            "errorGroupCount": total_errors,
            "classCounts": counts,
            "dominantErrorClass": dominant,
            "dominantErrorRate": round(
                counts[dominant] / total_errors, 6
            )
            if dominant
            else 0.0,
        }
    return output


def collect_group_records(
    manifest: dict[str, Any], data_root: Path
) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    candidate_paths: list[Path] = []
    for document in manifest["documents"]:
        session = data_root / "user_uploads-sessions" / str(document["sessionId"])
        candidate_path = session / "phase11_10_v2_017b" / "field_consensus.json"
        gt_path = session / "phase10" / "ground_truth.json"
        if not candidate_path.is_file() or not gt_path.is_file():
            raise SystemExit("complete sealed 017B candidate/GT artifacts required")
        candidate_paths.append(candidate_path)
        artifact = load_json(candidate_path)
        ground_truth = load_json(gt_path)["identityFields"]
        expected = ground_truth[TARGET_FIELD]
        expected_text = str(
            expected.get("value", "") if isinstance(expected, dict) else expected or ""
        )
        expected_line_ids = tuple(
            int(item) for item in document["fields"][TARGET_FIELD]["lineIds"]
        )
        candidates = [
            item
            for item in (artifact.get("candidates", {}).get(TARGET_FIELD, []) or [])
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
            label, eligible = classify_group(expected_line_ids, expected_text, group)
            records.append(
                {
                    "profile": profile,
                    "variant": variant,
                    "label": label,
                    "eligible": eligible,
                    "documentEvaluated": True,
                }
            )
    return records, candidate_paths


def build_report(
    source_018v: dict[str, Any],
    manifest: dict[str, Any],
    rows: dict[str, dict[str, Any]],
    digests: dict[str, str],
) -> dict[str, Any]:
    complete_rows = [row for row in rows.values() if row["evaluatedDocuments"] == 15]
    joint_available = bool(complete_rows) and len(complete_rows) == len(rows)
    return {
        "schemaVersion": (
            "ocr-ho-v2-018w-sealed-joint-residence-profile-variant-error-class-"
            "extractor/1.0.0"
        ),
        "taskId": "OCR-HO-V2-018W",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "SEALED_JOINT_RESIDENCE_PROFILE_VARIANT_ERROR_CLASS_EXTRACTION_ONLY",
        },
        "sourceDigests": digests,
        "sourceScope": {
            "source018vStatus": source_018v["decision"]["status"],
            "sealedManifestSha256": manifest["manifestSha256"],
            "targetField": TARGET_FIELD,
        },
        "jointEvidence": {
            "available": joint_available,
            "combinationCount": len(rows),
            "completeCombinationCount": len(complete_rows),
            "evaluatedDocumentsPerCompleteCombination": 15,
            "rows": list(rows.values()),
            "rawValuesEmitted": False,
        },
        "decision": {
            "status": "JOINT_RESIDENCE_PROFILE_VARIANT_ERROR_CLASS_EXTRACTED_HOLD",
            "jointEvidenceAvailable": joint_available,
            "profileVariantWinner": None,
            "selectionEligible": False,
            "selectorChanged": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "The sealed extractor emits aggregate joint residence profile×variant×"
                "error-class counts only. It does not select a profile/variant or alter "
                "runtime, even when the joint table is complete."
            ),
            "nextTask": "OCR-HO-V2-018X",
            "nextAction": (
                "Review the sealed joint table aggregate-only; keep selector, replay, "
                "runtime, held-out and promotion closed."
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
            "source018vAuthorizationReviewed": True,
            "sealedManifestValidated": True,
            "groundTruthUsedAtSelection": False,
            "groundTruthUsedForAttribution": True,
            "rawPredictionOpened": False,
            "selectorChanged": False,
            "counterfactualExecuted": False,
            "replayExecuted": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--source-018v", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_018v = load_json(args.source_018v)
    manifest = load_json(args.sealed_manifest)
    authorization_record = load_json(args.authorization_record)
    validate_018v(source_018v)
    validate_manifest(manifest)
    validate_authorization(authorization_record, manifest["manifestSha256"])
    group_records, candidate_paths = collect_group_records(manifest, args.data_root)
    rows = build_joint_table(group_records)
    report = build_report(
        source_018v,
        manifest,
        rows,
        {
            "artifact018vSha256": sha256(args.source_018v),
            "sealedManifestFileSha256": sha256(args.sealed_manifest),
            "candidateArtifactsSha256": hashlib.sha256(
                b"".join(path.read_bytes() for path in sorted(candidate_paths))
            ).hexdigest(),
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
                "decision": report["decision"]["status"],
                "combinationCount": report["jointEvidence"]["combinationCount"],
                "jointEvidenceAvailable": report["jointEvidence"]["available"],
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
