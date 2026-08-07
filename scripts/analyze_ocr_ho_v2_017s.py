#!/usr/bin/env python3
"""Aggregate-only OCR-HO-V2-017S independent line-ID mapping evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

TARGET_FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
INDEPENDENT_SCHEMA = "13.3.0-pilot"
IOU_THRESHOLD = 0.05


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_digest(payload: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "manifestSha256"}
    return hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def digest_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def box_to_xyxy(value: Any) -> tuple[float, float, float, float] | None:
    if (
        isinstance(value, list)
        and len(value) >= 4
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value[:4])
    ):
        x1, y1, x2, y2 = map(float, value[:4])
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    if (
        isinstance(value, list)
        and len(value) >= 4
        and all(
            isinstance(item, list)
            and len(item) >= 2
            and all(isinstance(coord, (int, float)) for coord in item[:2])
            for item in value[:4]
        )
    ):
        xs = [float(item[0]) for item in value[:4]]
        ys = [float(item[1]) for item in value[:4]]
        return min(xs), min(ys), max(xs), max(ys)
    return None


def iou(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def independent_lines(
    source: dict[str, Any],
) -> tuple[dict[int, tuple[float, float, float, float]], int]:
    lines: dict[int, tuple[float, float, float, float]] = {}
    duplicate_count = 0
    for page in source.get("pages", []):
        for line in page.get("lines", []):
            line_id = line.get("lineIndex")
            box = box_to_xyxy(line.get("box"))
            if not isinstance(line_id, int) or isinstance(line_id, bool) or box is None:
                continue
            if line_id in lines:
                duplicate_count += 1
                continue
            lines[line_id] = box
    return lines, duplicate_count


def field_mapping(
    expected_line_ids: list[int],
    region: dict[str, Any],
    source_lines: dict[int, tuple[float, float, float, float]],
) -> dict[str, int | float]:
    expected = {int(item) for item in expected_line_ids}
    region_boxes = [
        box
        for raw in (region.get("lineBboxes") or [])
        if (box := box_to_xyxy(raw)) is not None
    ]
    region_hits = {
        line_id
        for line_id, line_box in source_lines.items()
        if any(iou(line_box, region_box) >= IOU_THRESHOLD for region_box in region_boxes)
    }
    independent_overlap = expected.intersection(source_lines)
    expected_region_overlap = expected.intersection(region_hits)
    return {
        "expectedLineCount": len(expected),
        "independentSourceLineCount": len(source_lines),
        "independentLineIdOverlapCount": len(independent_overlap),
        "independentLineIdOverlapRate": round(len(independent_overlap) / max(1, len(expected)), 6),
        "regionLineBoxCount": len(region_boxes),
        "independentRegionMappedLineCount": len(region_hits),
        "expectedRegionMappedLineCount": len(expected_region_overlap),
        "expectedRegionMappedRate": round(
            len(expected_region_overlap) / max(1, len(expected)), 6
        ),
    }


def validate_manifest(manifest: dict[str, Any]) -> None:
    if (
        manifest.get("sealed") is not True
        or manifest.get("immutable") is not True
        or manifest.get("predictionOpened") is not False
        or manifest.get("manifestSha256") != manifest_digest(manifest)
        or manifest.get("documentCount") != 15
        or manifest.get("fieldCount") != 45
        or len(manifest.get("documents", [])) != 15
    ):
        raise SystemExit("Sealed prediction-blind CCCD 15-document manifest required")


def validate_lineage(source_017b: dict[str, Any], source_017r: dict[str, Any]) -> None:
    if (
        source_017b.get("schemaVersion") != "ocr-ho-v2-016b-development/1.0.0"
        or source_017b.get("candidateVersion") != "11.10.2"
        or source_017b.get("baselineVersion") != "11.9.1"
        or source_017b.get("datasetFamily") != "CCCD"
        or source_017b.get("datasetId") != "DATA-HO-014"
        or source_017b.get("documentCount") != 15
        or source_017b.get("evaluatedFieldCount") != 120
    ):
        raise SystemExit("017B candidate scope/schema mismatch")
    if source_017b.get("containsRawPII") is not False:
        raise SystemExit("017B must be aggregate-only")
    if (
        source_017r.get("schemaVersion")
        != "ocr-ho-v2-017r-residence-geometry-patch-gated-review/1.0.0"
        or source_017r.get("taskId") != "OCR-HO-V2-017R"
        or source_017r.get("datasetFamily") != "CCCD"
        or source_017r.get("datasetId") != "DATA-HO-014"
        or source_017r.get("documentCount") != 15
        or source_017r.get("evaluatedFieldCount") != 120
    ):
        raise SystemExit("017R lineage scope/schema mismatch")
    if source_017r.get("containsRawPII") is not False:
        raise SystemExit("017R must be aggregate-only")


def validate_independent_source(source: dict[str, Any]) -> None:
    if source.get("schemaVersion") != INDEPENDENT_SCHEMA:
        raise SystemExit("Independent phase13.3 line-map source schema mismatch")
    if not isinstance(source.get("pages"), list) or not source["pages"]:
        raise SystemExit("Independent line-map source has no pages")


def aggregate_mapping(rows: list[dict[str, int | float]]) -> dict[str, int | float]:
    expected = sum(int(row["expectedLineCount"]) for row in rows)
    overlap = sum(int(row["independentLineIdOverlapCount"]) for row in rows)
    expected_region = sum(int(row["expectedRegionMappedLineCount"]) for row in rows)
    return {
        "fieldCount": len(rows),
        "expectedLineCount": expected,
        "independentLineIdOverlapCount": overlap,
        "independentLineIdOverlapRate": round(overlap / max(1, expected), 6),
        "expectedRegionMappedLineCount": expected_region,
        "expectedRegionMappedRate": round(expected_region / max(1, expected), 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--source-017b", type=Path, required=True)
    parser.add_argument("--artifact-017r", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = load(args.sealed_manifest)
    source_017b = load(args.source_017b)
    source_017r = load(args.artifact_017r)
    validate_manifest(manifest)
    validate_lineage(source_017b, source_017r)

    candidate_paths: list[Path] = []
    independent_paths: list[Path] = []
    by_field: dict[str, list[dict[str, int | float]]] = {field: [] for field in TARGET_FIELDS}
    source_line_total = 0
    source_duplicate_total = 0
    independent_document_count = 0
    source_schema_counts: Counter[str] = Counter()
    for record in manifest["documents"]:
        session = args.data_root / "user_uploads-sessions" / str(record["sessionId"])
        candidate_path = session / "phase11_10_v2_017b" / "field_consensus.json"
        independent_path = session / "phase13_3" / "hybrid_ocr.json"
        if not candidate_path.is_file() or not independent_path.is_file():
            raise SystemExit("Complete 017B and independent phase13.3 artifacts are required")
        candidate_paths.append(candidate_path)
        independent_paths.append(independent_path)
        candidate = load(candidate_path)
        independent = load(independent_path)
        validate_independent_source(independent)
        independent_document_count += 1
        source_schema_counts[str(independent.get("schemaVersion"))] += 1
        lines, duplicate_count = independent_lines(independent)
        source_line_total += len(lines)
        source_duplicate_total += duplicate_count
        for field in TARGET_FIELDS:
            mapping = field_mapping(
                [int(item) for item in record["fields"][field]["lineIds"]],
                candidate.get("regions", {}).get(field, {}) or {},
                lines,
            )
            by_field[field].append(mapping)

    aggregate = aggregate_mapping([row for rows in by_field.values() for row in rows])
    field_summary = {field: aggregate_mapping(rows) for field, rows in by_field.items()}
    expected = int(aggregate["expectedLineCount"])
    overlap = int(aggregate["independentLineIdOverlapCount"])
    evidence_available = independent_document_count == 15 and expected > 0 and overlap > 0
    source_digest = digest_files(independent_paths)
    report = {
        "schemaVersion": "ocr-ho-v2-017s-independent-line-id-mapping-evidence/1.0.0",
        "taskId": "OCR-HO-V2-017S",
        "candidateVersion": source_017b["candidateVersion"],
        "baselineVersion": source_017b["baselineVersion"],
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
            "diagnostic": "INDEPENDENT_LINE_ID_MAPPING_EVIDENCE_ONLY",
        },
        "sourceDigests": {
            "sealedManifestSha256": manifest["manifestSha256"],
            "candidate017bSha256": sha256(args.source_017b),
            "artifact017rSha256": sha256(args.artifact_017r),
            "independentPhase13Sha256": source_digest,
        },
        "sourceInventory": {
            "independentSource": "phase13_3_hybrid_ocr_line_index_bbox",
            "independentSourceSchema": INDEPENDENT_SCHEMA,
            "independentFromCandidate": True,
            "rawTextConsumed": False,
            "availableDocumentCount": independent_document_count,
            "sourceLineCount": source_line_total,
            "duplicateLineIndexCount": source_duplicate_total,
            "schemaVersionCounts": dict(source_schema_counts),
        },
        "mappingDefinition": (
            "Independent lineIndex is compared with sealed line IDs after prediction; "
            "geometry attribution uses IoU against candidate lineBboxes at threshold 0.05."
        ),
        "aggregate": aggregate,
        "byField": field_summary,
        "evidenceAssessment": {
            "independentSourceAvailable": evidence_available,
            "independentDocumentCoverage": independent_document_count,
            "independentLineIdOverlapCount": overlap,
            "independentLineIdOverlapRate": round(overlap / max(1, expected), 6),
            "lineIdEvidenceGate": "PASS" if evidence_available else "HOLD",
        },
        "decision": {
            "status": (
                "INDEPENDENT_LINE_ID_EVIDENCE_AVAILABLE"
                if evidence_available
                else "INDEPENDENT_LINE_ID_EVIDENCE_BLOCKED"
            ),
            "recommendedNextTask": "OCR-HO-V2-017T" if evidence_available else "OCR-HO-V2-017S",
            "recommendedNextDiagnostic": "PATCH_GATE_RECONCILIATION",
            "reason": (
                "A separate phase13.3 line-index/bbox source covers all 15 documents and has "
                "non-zero sealed line-ID overlap. This is attribution evidence only; it does "
                "not authorize a runtime patch, replay, selector counterfactual, or promotion."
                if evidence_available
                else "No independent line-ID source with non-zero overlap is available."
            ),
            "counterfactualAuthorized": False,
            "patchAuthorized": False,
            "replayAuthorized": False,
            "runtimeChanged": False,
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
                "independentDocumentCoverage": independent_document_count,
                "lineIdOverlap": f"{overlap}/{expected}",
                "lineIdEvidenceGate": report["evidenceAssessment"]["lineIdEvidenceGate"],
                "nextTask": report["decision"]["recommendedNextTask"],
                "patchAuthorized": False,
                "replayAuthorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
