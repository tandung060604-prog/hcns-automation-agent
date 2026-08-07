#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017P residence geometry boundary review."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

FIELD = "placeOfResidence"
GEOMETRY_SOURCE = "phase11_10_geometry_line_segmentation"


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
    source_017h: dict[str, Any],
    source_017n: dict[str, Any],
    source_017o: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    if (
        source_017h.get("schemaVersion") != "ocr-ho-v2-017h-roi-boundary-diagnostic/1.0.0"
        or source_017h.get("datasetFamily") != "CCCD"
        or source_017h.get("datasetId") != "DATA-HO-014"
        or source_017h.get("documentCount") != 15
        or source_017h.get("evaluatedFieldCount") != 120
        or source_017h.get("roiDiagnosticFieldCount") != 45
    ):
        raise SystemExit("017H source scope/schema mismatch")
    if (
        source_017n.get("taskId") != "OCR-HO-V2-017N"
        or source_017o.get("taskId") != "OCR-HO-V2-017O"
    ):
        raise SystemExit("017N/017O lineage artifacts required")
    for source in (source_017h, source_017n, source_017o):
        if source.get("containsRawPII") is not False:
            raise SystemExit("Lineage artifacts must be aggregate-only")
    if (
        manifest.get("sealed") is not True
        or manifest.get("immutable") is not True
        or manifest.get("predictionOpened") is not False
        or manifest.get("manifestSha256") != manifest_digest(manifest)
        or len(manifest.get("documents", [])) != 15
    ):
        raise SystemExit("Sealed prediction-blind 15-document manifest required")


def bottom_overflow(line_bboxes: list[list[float]], bbox: list[float]) -> tuple[int, int]:
    if len(bbox) < 4:
        return 0, 0
    overflow_values = [
        max(0, int(round(float(line[3]) - float(bbox[3]))))
        for line in line_bboxes
        if len(line) >= 4
    ]
    return int(any(value > 0 for value in overflow_values)), max(overflow_values, default=0)


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    expected_line_count = sum(case["expectedLineCount"] for case in cases)
    region_line_count = sum(case["regionLineCount"] for case in cases)
    overlap_count = sum(case["sealedLineIdOverlapCount"] for case in cases)
    overflow_cases = sum(case["bottomOverflow"] for case in cases)
    return {
        "caseCount": len(cases),
        "regionSourceCounts": dict(sorted(Counter(case["regionSource"] for case in cases).items())),
        "normalizedBboxCounts": dict(
            sorted(Counter(case["normalizedBbox"] for case in cases).items())
        ),
        "maxValueLinesCounts": dict(
            sorted(Counter(str(case["maxValueLines"]) for case in cases).items())
        ),
        "expectedLineCount": expected_line_count,
        "regionLineCount": region_line_count,
        "sealedLineIdOverlapCount": overlap_count,
        "sealedLineIdOverlapRate": round(overlap_count / max(1, expected_line_count), 6),
        "bottomOverflowCaseCount": overflow_cases,
        "bottomOverflowCaseRate": round(overflow_cases / max(1, len(cases)), 6),
        "maxBottomOverflowPixels": max(
            (case["maxBottomOverflowPixels"] for case in cases), default=0
        ),
        "cropLineVariantEntryCount": sum(case["cropLineVariantEntryCount"] for case in cases),
    }


def review(
    source_017h: dict[str, Any],
    source_017n: dict[str, Any],
    source_017o: dict[str, Any],
    manifest: dict[str, Any],
    data_root: Path,
    candidate_paths: list[Path],
    digests: dict[str, str],
) -> dict[str, Any]:
    bottom_entries = [
        item
        for item in source_017h["missDetailsAggregateOnly"]
        if item.get("field") == FIELD and item.get("category") == "bottom_boundary"
    ]
    cases: list[dict[str, Any]] = []
    for entry in bottom_entries:
        index = int(entry["documentIndex"])
        record = manifest["documents"][index - 1]
        candidate_path = (
            data_root
            / "user_uploads-sessions"
            / str(record["sessionId"])
            / "phase11_10_v2_017b"
            / "field_consensus.json"
        )
        artifact = load(candidate_path)
        region = artifact["regions"][FIELD]
        expected_ids = tuple(int(item) for item in record["fields"][FIELD]["lineIds"])
        region_ids = tuple(int(item) for item in region.get("lineIds") or [])
        line_bboxes = region.get("lineBboxes") or []
        overflow, max_overflow = bottom_overflow(line_bboxes, region.get("bbox") or [])
        crop_entries = artifact.get("crops", {}).get(FIELD, {}) or {}
        cases.append(
            {
                "expectedLineCount": len(expected_ids),
                "regionLineCount": len(region_ids),
                "sealedLineIdOverlapCount": len(set(expected_ids).intersection(region_ids)),
                "regionSource": str(region.get("regionSource") or "unknown"),
                "normalizedBbox": ",".join(
                    f"{float(value):.4f}" for value in (region.get("normalizedBbox") or [])
                ),
                "maxValueLines": int(region.get("maxValueLines") or 0),
                "bottomOverflow": overflow,
                "maxBottomOverflowPixels": max_overflow,
                "cropLineVariantEntryCount": len(crop_entries),
            }
        )

    summary = summarize_cases(cases)
    return {
        "schemaVersion": "ocr-ho-v2-017p-residence-geometry-segmentation-boundary-review/1.0.0",
        "taskId": "OCR-HO-V2-017P",
        "candidateVersion": source_017h["candidateVersion"],
        "baselineVersion": source_017h["baselineVersion"],
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
            "diagnostic": "RESIDENCE_GEOMETRY_SEGMENTATION_BOUNDARY_REVIEW_ONLY",
        },
        "sourceDigests": digests,
        "evidence": {
            "field": FIELD,
            "bottomBoundaryCases": summary,
            "priorCandidateRule": source_017o["candidateRule"],
            "priorGlobalBoundaryContext": source_017n["evidence"]["automaticDetectorAggregate"],
        },
        "candidateRule": {
            "field": FIELD,
            "category": "GEOMETRY_BOTTOM_BOUNDARY_AND_LINE_ID_MAPPING",
            "caseCount": summary["caseCount"],
            "bottomOverflowCaseRate": summary["bottomOverflowCaseRate"],
            "sealedLineIdOverlapRate": summary["sealedLineIdOverlapRate"],
            "regionSource": GEOMETRY_SOURCE,
            "status": "CANDIDATE_ONLY_NO_RUNTIME_PATCH",
            "roiPatchAuthorized": False,
            "counterfactualAuthorized": False,
        },
        "decision": {
            "status": "RESIDENCE_GEOMETRY_SEGMENTATION_REVIEW_HOLD",
            "recommendedNextTask": "OCR-HO-V2-017Q",
            "recommendedNextDiagnostic": "RESIDENCE_GEOMETRY_MINIMAL_BOUNDARY_RULE_REVIEW",
            "reason": (
                "All three cases share the geometry segmentation source and a common normalized "
                "region band; two of three show bottom bbox overflow and sealed line-id overlap "
                "is zero. This supports a bounded review, not an automatic ROI patch."
            ),
            "runtimeChanged": False,
            "roiPatchAuthorized": False,
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
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--artifact-017h", type=Path, required=True)
    parser.add_argument("--artifact-017n", type=Path, required=True)
    parser.add_argument("--artifact-017o", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_017h = load(args.artifact_017h)
    source_017n = load(args.artifact_017n)
    source_017o = load(args.artifact_017o)
    manifest = load(args.sealed_manifest)
    validate_sources(source_017h, source_017n, source_017o, manifest)
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
    report = review(
        source_017h,
        source_017n,
        source_017o,
        manifest,
        args.data_root,
        candidate_paths,
        {
            "artifact017h": sha256(args.artifact_017h),
            "artifact017n": sha256(args.artifact_017n),
            "artifact017o": sha256(args.artifact_017o),
            "sealedManifestSha256": manifest["manifestSha256"],
            "candidateArtifactsSha256": candidate_digest(candidate_paths),
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
                "caseCount": report["candidateRule"]["caseCount"],
                "bottomOverflowCaseRate": report["candidateRule"]["bottomOverflowCaseRate"],
                "sealedLineIdOverlapRate": report["candidateRule"]["sealedLineIdOverlapRate"],
                "nextTask": "OCR-HO-V2-017Q",
                "roiPatchAuthorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
