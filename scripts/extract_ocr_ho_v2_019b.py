#!/usr/bin/env python3
"""Extract independent aggregate residence boundary/profile/variant cross-tab."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
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
FIELD = "placeOfResidence"
AUTH_SCHEMA = "ocr-ho-v2-019b-independent-residence-crosstab-authorization-record/1.0.0"
ERROR_CLASSES = ("LINE_ID_MISS", "LINE_ORDER_MISMATCH", "DUPLICATE_LINE", "LINE_ID_MATCH")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def line_ids(candidate: dict[str, Any]) -> tuple[int, ...]:
    raw_ids = candidate.get("lineIds")
    if isinstance(raw_ids, list) and raw_ids:
        return tuple(int(item) for item in raw_ids if item is not None)
    raw_id = candidate.get("lineId")
    return (int(raw_id),) if raw_id is not None else ()


def variant_family(value: Any) -> str:
    value = str(value or "")
    return value.split("_", 1)[1] if value.startswith("line") and "_" in value else value


def classify_line_ids(expected: tuple[int, ...], candidates: list[dict[str, Any]]) -> str:
    ordered = sorted(
        candidates,
        key=lambda item: (int(item.get("lineOrder", 0)), line_ids(item)),
    )
    observed = tuple(item_id for candidate in ordered for item_id in line_ids(candidate))
    if len(observed) != len(set(observed)):
        return "DUPLICATE_LINE"
    if not set(expected).issubset(set(observed)):
        return "LINE_ID_MISS"
    if observed != expected:
        return "LINE_ORDER_MISMATCH"
    return "LINE_ID_MATCH"


def validate_scope(source: dict[str, Any], schema: str, task_id: str) -> None:
    task_matches = source.get("taskId") == task_id or (
        task_id == "OCR-HO-V2-017H" and source.get("taskId") is None
    )
    if source.get("schemaVersion") != schema or not task_matches:
        raise SystemExit(f"{task_id} source schema mismatch")
    for key, expected in SCOPE.items():
        actual = source.get(key)
        if key == "diagnosticFieldCount" and task_id == "OCR-HO-V2-017H":
            actual = source.get("diagnosticFieldCount", source.get("roiDiagnosticFieldCount"))
        if actual != expected:
            raise SystemExit(f"{task_id} source scope mismatch: {key}")
    if source.get("containsRawPII") is not False or source.get("predictionOpened") is not False:
        raise SystemExit(f"{task_id} must remain aggregate-only and sealed")


def validate_manifest(manifest: dict[str, Any], manifest_digest: str) -> None:
    if (
        manifest.get("sealed") is not True
        or manifest.get("immutable") is not True
        or manifest.get("localOnly") is not True
        or manifest.get("predictionOpened") is not False
        or manifest.get("manifestSha256") != manifest_digest
        or manifest.get("documentCount") != 15
        or len(manifest.get("documents", [])) != 15
    ):
        raise SystemExit("sealed prediction-blind 15-document manifest required")


def validate_authorization(record: dict[str, Any] | None, manifest_digest: str) -> None:
    if record is None:
        raise SystemExit("019B standing local-only diagnostic authorization required")
    approval = record.get("approval", {})
    if (
        record.get("schemaVersion") != AUTH_SCHEMA
        or record.get("taskId") != "OCR-HO-V2-019B"
        or record.get("datasetFamily") != SCOPE["datasetFamily"]
        or record.get("datasetId") != SCOPE["datasetId"]
        or record.get("candidateVersion") != SCOPE["candidateVersion"]
        or record.get("baselineVersion") != SCOPE["baselineVersion"]
        or record.get("containsRawPII") is not False
        or str(record.get("sealedManifestSha256") or "").casefold()
        != manifest_digest.casefold()
        or approval.get("approved") is not True
        or approval.get("approverRole") != "OCR_REVIEW_OWNER"
        or approval.get("localOnly") is not True
        or approval.get("independentResidenceCrossTabAuthorized") is not True
    ):
        raise SystemExit("019B authorization record invalid")
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
            raise SystemExit(f"019B prohibited authorization is not false: {key}")


def validate_sources(
    source_019a: dict[str, Any],
    source_018w: dict[str, Any],
    source_017h: dict[str, Any],
) -> None:
    validate_scope(
        source_019a,
        "ocr-ho-v2-019a-residence-patch-review-decision/1.0.0",
        "OCR-HO-V2-019A",
    )
    validate_scope(
        source_018w,
        "ocr-ho-v2-018w-sealed-joint-residence-profile-variant-error-class-extractor/1.0.0",
        "OCR-HO-V2-018W",
    )
    validate_scope(source_017h, "ocr-ho-v2-017h-roi-boundary-diagnostic/1.0.0", "OCR-HO-V2-017H")
    if source_019a["decision"]["patchReviewEligible"] is not False:
        raise SystemExit("019A patch review must remain closed")
    rows = source_018w["jointEvidence"]["rows"]
    if len(rows) != 16 or any(row.get("evaluatedDocuments") != 15 for row in rows):
        raise SystemExit("018W complete joint rows required")
    if any("value" in row or "text" in row for row in rows):
        raise SystemExit("018W raw value emitted")
    line_id_miss_total = sum(
        int(row.get("classCounts", {}).get("LINE_ID_MISS", 0))
        for row in rows
    )
    if line_id_miss_total != 81:
        raise SystemExit("018W line-ID miss lineage drift")


def boundary_by_document(source_017h: dict[str, Any]) -> dict[int, str]:
    output: dict[int, str] = {}
    for entry in source_017h.get("missDetailsAggregateOnly", []):
        if entry.get("field") != FIELD:
            continue
        index = int(entry["documentIndex"])
        category = str(entry.get("category") or "unclassified")
        if index in output and output[index] != category:
            raise SystemExit("017H has conflicting residence boundary categories")
        output[index] = category
    return output


def build_cross_tab(
    manifest: dict[str, Any],
    candidate_documents: list[dict[str, Any]],
    boundary_documents: dict[int, str],
) -> dict[str, Any]:
    counts: Counter[tuple[str, str, str]] = Counter()
    profile_variant_totals: Counter[tuple[str, str]] = Counter()
    class_totals: Counter[str] = Counter()
    boundary_group_count = 0
    for document_index, (document, artifact) in enumerate(
        zip(manifest["documents"], candidate_documents, strict=True), 1
    ):
        expected = tuple(int(item) for item in document["fields"][FIELD]["lineIds"])
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for candidate in artifact.get("candidates", {}).get(FIELD, []) or []:
            profile = str(candidate.get("profile") or "unknown")
            variant = variant_family(candidate.get("variant"))
            groups[(profile, variant)].append(candidate)
        category = boundary_documents.get(document_index)
        for key, candidates in groups.items():
            label = classify_line_ids(expected, candidates)
            profile_variant_totals[key] += 1
            class_totals[label] += 1
            if label == "LINE_ID_MISS" and category is not None:
                counts[(key[0], key[1], category)] += 1
                boundary_group_count += 1
    rows = [
        {
            "profile": profile,
            "variant": variant,
            "boundaryCategory": category,
            "lineIdMissGroups": count,
        }
        for (profile, variant, category), count in sorted(counts.items())
    ]
    return {
        "rows": rows,
        "profileVariantCombinationCount": len(profile_variant_totals),
        "profileVariantDocumentGroups": sum(profile_variant_totals.values()),
        "lineIdClassTotals": dict(sorted(class_totals.items())),
        "boundaryAttributedLineIdMissGroups": boundary_group_count,
        "boundaryDocumentCount": len(boundary_documents),
    }


def build_report(
    source_019a: dict[str, Any],
    source_018w: dict[str, Any],
    source_017h: dict[str, Any],
    cross_tab: dict[str, Any],
    digests: dict[str, str],
) -> dict[str, Any]:
    return {
        "schemaVersion": (
            "ocr-ho-v2-019b-independent-residence-boundary-profile-variant-crosstab/1.0.0"
        ),
        "taskId": "OCR-HO-V2-019B",
        **SCOPE,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "gtUsedForAttribution": True,
        "protocol": {
            "gate": "AUTO_DETECTOR",
            "diagnostic": "INDEPENDENT_RESIDENCE_BOUNDARY_PROFILE_VARIANT_CROSSTAB_ONLY",
        },
        "sourceDigests": digests,
        "lineage": {
            "source019aPatchReviewClosed": source_019a["decision"]["patchReviewEligible"] is False,
            "source018wJointRows": len(source_018w["jointEvidence"]["rows"]),
            "source017hBoundaryCases": cross_tab["boundaryDocumentCount"],
            "candidateMetadataOnly": True,
            "rawValuesOpened": False,
            "crossTabIndependentOf017HProfileCounts": True,
        },
        "crossTab": {
            "field": FIELD,
            **cross_tab,
            "available": bool(cross_tab["rows"]),
            "rawValuesEmitted": False,
            "groundTruthLineIdsUsedForAttributionOnly": True,
        },
        "decision": {
            "status": "INDEPENDENT_RESIDENCE_CROSSTAB_EXTRACTED_HOLD",
            "crossTabAvailable": bool(cross_tab["rows"]),
            "patchReviewEligible": False,
            "patchAuthorizationIssued": False,
            "profileVariantWinner": None,
            "selectorChanged": False,
            "counterfactualAuthorized": False,
            "runtimeChanged": False,
            "replayExecuted": False,
            "heldoutOpened": False,
            "promotionAllowed": False,
            "reason": (
                "The independent cross-tab is aggregate evidence only; it does not select "
                "a profile/variant or authorize a patch. Review remains HOLD."
            ),
            "nextTask": "OCR-HO-V2-019C",
            "nextAction": (
                "Review independent boundary/profile cross-tab; keep selector, patch, replay "
                "and promotion closed."
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
    parser.add_argument("--source-019a", type=Path, required=True)
    parser.add_argument("--source-018w", type=Path, required=True)
    parser.add_argument("--source-017h", type=Path, required=True)
    parser.add_argument("--authorization-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = load(args.sealed_manifest)
    source_019a = load(args.source_019a)
    source_018w = load(args.source_018w)
    source_017h = load(args.source_017h)
    authorization = load(args.authorization_record)
    manifest_digest = manifest.get("manifestSha256", "")
    validate_manifest(manifest, manifest_digest)
    validate_sources(source_019a, source_018w, source_017h)
    validate_authorization(authorization, manifest_digest)
    candidate_documents: list[dict[str, Any]] = []
    for document in manifest["documents"]:
        candidate_path = (
            args.data_root
            / "user_uploads-sessions"
            / str(document["sessionId"])
            / "phase11_10_v2_017b"
            / "field_consensus.json"
        )
        if not candidate_path.is_file():
            raise SystemExit("complete sealed 017B candidate artifacts required")
        candidate_documents.append(load(candidate_path))
    cross_tab = build_cross_tab(manifest, candidate_documents, boundary_by_document(source_017h))
    source_paths = {
        "sealedManifestFileSha256": args.sealed_manifest,
        "source019aSha256": args.source_019a,
        "source018wSha256": args.source_018w,
        "source017hSha256": args.source_017h,
        "authorizationRecordSha256": args.authorization_record,
    }
    report = build_report(
        source_019a,
        source_018w,
        source_017h,
        cross_tab,
        {
            **{name: sha256(path) for name, path in source_paths.items()},
            "sealedManifestDigest": manifest_digest,
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
                "rows": len(cross_tab["rows"]),
                "nextTask": report["decision"]["nextTask"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
