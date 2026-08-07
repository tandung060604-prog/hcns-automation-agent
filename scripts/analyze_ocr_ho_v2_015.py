#!/usr/bin/env python3
"""Canonical, aggregate-only OCR-HO-V2-015 development diagnostic."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps" / "ocr_lab" / "api"), str(ROOT / "scripts"), str(ROOT / "src")]

from evaluate_cccd_phase11_5 import FIELD_ORDER, error_class, evaluate_variant, value  # noqa: E402
from ocr_ho_v2_014_evaluation import aggregate, diagnostic_gates  # noqa: E402
from phase11_10_cccd_v2 import locate_field_regions, prepare_line_pages  # noqa: E402

from hcns_agent.application.ocr_metrics import evaluate_text_pairs  # noqa: E402

TARGET_FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
PROTECTED_FIELDS = ("identityNumber", "dateOfBirth", "sex", "nationality", "dateOfExpiry")
CLASS_NAMES = ("ROI_MISS", "RECOGNIZER_MISS", "DIACRITIC_MISS", "SELECTOR_MISS", "PARSER_CONTAMINATION", "EXACT")
LABELS = ("full name", "place of origin", "place of residence", "date of expiry", "date of birth", "nationality")
SNAPSHOT_EXPECTED = {
    "documentCount": 15,
    "evaluatedFieldCount": 120,
    "baselineVersion": "11.9.1",
    "baseline": {"strictFieldExactMatch": 0.6083, "asciiFieldExactMatch": 0.625, "cer": 0.4209, "der": 0.1146, "fieldPresence": 0.9583},
    "candidate": {"strictFieldExactMatch": 0.6333, "asciiFieldExactMatch": 0.6917, "cer": 0.3062, "der": 0.166, "fieldPresence": 0.9583},
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sealed_digest(payload: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in payload.items() if key != "manifestSha256"}
    return hashlib.sha256(json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def candidate_artifact_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def normalized(text: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(text or "")).split()).casefold()


def ascii_normalized(text: Any) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", str(text or "")).casefold() if not unicodedata.combining(char))


def field_candidates(field: dict[str, Any], artifact: dict[str, Any], name: str) -> list[dict[str, Any]]:
    candidates = artifact.get("candidates", {}).get(name)
    if isinstance(candidates, list):
        return [item for item in candidates if isinstance(item, dict)]
    return [item for item in field.get("evidence", {}).get("candidates", []) if isinstance(item, dict)]


def contaminated(field: dict[str, Any], candidates: list[dict[str, Any]]) -> bool:
    signals = {str(signal) for signal in field.get("errorSignals", [])}
    if signals.intersection({"label_contamination", "region_or_line_merge"}):
        return True
    values = [field.get("value")] + [item.get("value") for item in candidates]
    return any(any(label in normalized(item) for label in LABELS) for item in values if item)


def classify(*, expected: str, field: dict[str, Any], candidates: list[dict[str, Any]], roi_hit: bool) -> str:
    if not roi_hit:
        return "ROI_MISS"
    if normalized(field.get("value")) == normalized(expected):
        return "EXACT"
    if contaminated(field, candidates):
        return "PARSER_CONTAMINATION"
    candidate_values = [normalized(item.get("value")) for item in candidates]
    if normalized(expected) in candidate_values:
        return "SELECTOR_MISS"
    if ascii_normalized(expected) in {ascii_normalized(item) for item in candidate_values}:
        return "DIACRITIC_MISS"
    return "RECOGNIZER_MISS"


def make_documents(
    root: Path,
    sealed: dict[str, Any],
    candidate_phase_root: str = "phase11_10_v2",
    candidate_result_key: str = "phase11_10_v2",
    oracle_phase_root: str | None = None,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for record in sealed["documents"]:
        session = root / "user_uploads-sessions" / str(record["sessionId"])
        gt = json.loads((session / "phase10" / "ground_truth.json").read_text(encoding="utf-8"))
        baseline_artifact = json.loads((session / "phase11_9_v2" / "field_consensus.json").read_text(encoding="utf-8"))
        candidate_artifact = json.loads(
            (session / candidate_phase_root / "field_consensus.json").read_text(
                encoding="utf-8"
            )
        )
        oracle_artifact = None
        if oracle_phase_root:
            oracle_artifact = json.loads(
                (session / oracle_phase_root / "field_consensus.json").read_text(
                    encoding="utf-8"
                )
            )
        result = json.loads((session / "result.json").read_text(encoding="utf-8"))
        assertions = gt.get("identityFields", {})
        if set(assertions) != set(FIELD_ORDER):
            raise SystemExit("Ground Truth schema is not the canonical eight-field CCCD schema")
        documents.append({
            "groundTruth": {
                name: item["value"] if isinstance(item, dict) else item
                for name, item in assertions.items()
            },
            "baseline": baseline_artifact.get("identityCard", {}).get("fields", {}),
            "phase11_10": candidate_artifact.get("identityCard", {}).get("fields", {}),
            "candidateArtifact": candidate_artifact,
            "oracle": (oracle_artifact or {}).get("identityCard", {}).get("fields", {}),
            "oracleArtifact": oracle_artifact,
            "gtFields": record["fields"],
            "durations": {
                "baseline": result.get("phase11_9_v2", result.get("phase11_5", {})).get("durationMs", 0.0),
                "phase11_10": result.get(candidate_result_key, {}).get("durationMs", 0.0),
            },
        })
    return documents


def class_report(documents: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    labels: list[tuple[str, str]] = []
    roi_hits, evaluated = Counter(), Counter()
    for document in documents:
        fields = document[variant]
        for name in TARGET_FIELDS:
            expected = str(document["groundTruth"].get(name) or "")
            field = fields.get(name) or {}
            if not expected:
                continue
            if variant in {"phase11_10", "oracle"}:
                gt_ids = set(document["gtFields"][name]["lineIds"])
                artifact_key = "candidateArtifact" if variant == "phase11_10" else "oracleArtifact"
                artifact = document.get(artifact_key) or {}
                roi_ids = set((artifact.get("regions", {}).get(name) or {}).get("lineIds") or [])
                roi_hit = bool(gt_ids) and gt_ids.issubset(roi_ids)
                candidates = field_candidates(field, artifact, name)
            else:
                roi_hit = bool((field.get("evidence") or {}).get("bbox"))
                candidates = [item for item in field.get("evidence", {}).get("candidates", []) if isinstance(item, dict)]
            evaluated[name] += 1
            roi_hits[name] += int(roi_hit)
            labels.append((name, classify(expected=expected, field=field, candidates=candidates, roi_hit=roi_hit)))
    return {"classCountsByField": aggregate(labels), "roiByField": {name: {"correct": roi_hits[name], "evaluated": evaluated[name], "accuracy": round(roi_hits[name] / max(1, evaluated[name]), 6)} for name in TARGET_FIELDS}}


def automatic_roi_report(root: Path, sealed: dict[str, Any]) -> dict[str, Any]:
    counts = {name: {"correct": 0, "evaluated": 0, "lineMiss": 0, "missingPage": 0} for name in TARGET_FIELDS}
    for record in sealed["documents"]:
        session = root / "user_uploads-sessions" / str(record["sessionId"])
        result = json.loads((session / "result.json").read_text(encoding="utf-8"))
        detected_pages = result.get("phase11", {}).get("pages", [])
        pages = [
            cv2.imread(
                str(session / "phase11" / "pages" / f"page_{page['pageIndex']:03d}.png"),
                cv2.IMREAD_COLOR,
            )
            for page in detected_pages
        ]
        if not pages or any(page is None for page in pages):
            for item in counts.values():
                item["missingPage"] += 1
            continue
        prepared, _ = prepare_line_pages(session, detected_pages, pages)
        regions = locate_field_regions(prepared, [(page.shape[1], page.shape[0]) for page in pages])
        for name in TARGET_FIELDS:
            expected_ids = set(record["fields"][name]["lineIds"])
            actual_ids = set((regions.get(name) or {}).get("lineIds") or [])
            counts[name]["evaluated"] += 1
            hit = bool(expected_ids) and expected_ids.issubset(actual_ids)
            counts[name]["correct"] += int(hit)
            counts[name]["lineMiss"] += int(not hit)
    return {name: {**item, "accuracy": round(item["correct"] / max(1, item["evaluated"]), 6)} for name, item in counts.items()}


def roi_failure_attribution(root: Path, sealed: dict[str, Any]) -> dict[str, Any]:
    """Separate missing detector lines from field-boundary exclusion."""

    fields = ("fullName", "placeOfOrigin", "placeOfResidence")
    counts = {
        name: {
            "evaluated": 0,
            "autoHit": 0,
            "detectorMiss": 0,
            "cropMiss": 0,
            "boundaryMiss": 0,
            "boundaryOutsideRegionBbox": 0,
            "boundaryInsideRegionBboxNotSelected": 0,
            "missingPage": 0,
        }
        for name in fields
    }
    for record in sealed["documents"]:
        session = root / "user_uploads-sessions" / str(record["sessionId"])
        result = json.loads((session / "result.json").read_text(encoding="utf-8"))
        detected_pages = result.get("phase11", {}).get("pages", [])
        image_paths = [
            session / "phase11" / "pages" / f"page_{page['pageIndex']:03d}.png"
            for page in detected_pages
        ]
        images = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in image_paths]
        if not detected_pages or not images or any(image is None for image in images):
            for name in fields:
                counts[name]["evaluated"] += 1
                counts[name]["cropMiss"] += 1
                counts[name]["missingPage"] += 1
            continue
        prepared, _ = prepare_line_pages(session, detected_pages, images)
        regions = locate_field_regions(
            prepared, [(image.shape[1], image.shape[0]) for image in images]
        )
        page = prepared[0]
        boxes = page.get("recognizedBoxes", [])

        def box_bounds(box: Any) -> tuple[float, float, float, float]:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            return min(xs), min(ys), max(xs), max(ys)

        for name in fields:
            counts[name]["evaluated"] += 1
            expected_ids = set(record["fields"][name]["lineIds"])
            region = regions.get(name) or {}
            selected_ids = set(region.get("lineIds") or [])
            valid_detector_ids = all(
                isinstance(line_id, int) and 0 <= line_id < len(boxes)
                for line_id in expected_ids
            )
            if not valid_detector_ids:
                counts[name]["detectorMiss"] += 1
                continue
            if expected_ids.issubset(selected_ids):
                if expected_ids and len(region.get("lineBboxes") or []) >= len(expected_ids):
                    counts[name]["autoHit"] += 1
                else:
                    counts[name]["cropMiss"] += 1
                continue
            counts[name]["boundaryMiss"] += 1
            region_bbox = region.get("bbox") or []
            if len(region_bbox) != 4:
                counts[name]["boundaryOutsideRegionBbox"] += 1
                continue
            inside_region = True
            for line_id in expected_ids:
                left, top, right, bottom = box_bounds(boxes[line_id])
                center_x, center_y = (left + right) / 2, (top + bottom) / 2
                inside_region &= (
                    float(region_bbox[0]) <= center_x <= float(region_bbox[2])
                    and float(region_bbox[1]) <= center_y <= float(region_bbox[3])
                )
            counts[name][
                "boundaryInsideRegionBboxNotSelected"
                if inside_region
                else "boundaryOutsideRegionBbox"
            ] += 1
    return {
        "basis": "phase11_pages_detector_line_id_universe",
        "byField": counts,
    }


def der_breakdown(documents: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    by_field: dict[str, dict[str, int | float]] = {}
    total_reference = total_errors = 0
    for name in FIELD_ORDER:
        metrics = evaluate_text_pairs(
            [(document["groundTruth"][name], value(document[variant].get(name))) for document in documents]
        )
        reference, errors = metrics.reference_diacritic_count, metrics.diacritic_error_count
        total_reference += reference
        total_errors += errors
        by_field[name] = {"evaluatedFieldCount": len(documents), "referenceDiacriticCount": reference, "diacriticErrorCount": errors, "der": round(float(metrics.diacritic_error_rate), 6)}
    return {"byField": by_field, "evaluatedFieldCount": len(documents) * len(FIELD_ORDER), "referenceDiacriticCount": total_reference, "diacriticErrorCount": total_errors, "der": round(total_errors / max(1, total_reference), 6)}


def error_transition(documents: list[dict[str, Any]], after_variant: str = "phase11_10") -> dict[str, dict[str, int]]:
    transitions: dict[str, Counter[str]] = {name: Counter() for name in FIELD_ORDER}
    for document in documents:
        for name in FIELD_ORDER:
            expected = document["groundTruth"][name]
            before_field = document["baseline"].get(name, {})
            after_field = document[after_variant].get(name, {})
            before_class = error_class(expected, value(before_field), before_field)
            after_class = error_class(expected, value(after_field), after_field)
            transitions[name][f"{before_class}->{after_class}"] += 1
    return {name: dict(items) for name, items in transitions.items()}


def snapshot_status(before: dict[str, Any], after: dict[str, Any], document_count: int, field_count: int) -> tuple[str, dict[str, Any]]:
    observed = {"documentCount": document_count, "evaluatedFieldCount": field_count, "baselineVersion": "11.9.1", "baseline": {key: round(float(before[key]), 4) for key in SNAPSHOT_EXPECTED["baseline"]}, "candidate": {key: round(float(after[key]), 4) for key in SNAPSHOT_EXPECTED["candidate"]}}
    return ("MATCH" if observed == SNAPSHOT_EXPECTED else "SNAPSHOT_MISMATCH"), observed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--candidate-phase-root", default="phase11_10_v2")
    parser.add_argument("--candidate-result-key", default="phase11_10_v2")
    parser.add_argument("--candidate-version", default="11.10.0")
    parser.add_argument("--oracle-phase-root", default=None)
    args = parser.parse_args()
    root, sealed_path = args.data_root.resolve(), args.sealed_manifest.resolve()
    sealed = json.loads(sealed_path.read_text(encoding="utf-8"))
    if sealed.get("sealed") is not True or sealed.get("predictionOpened") is not False or sealed.get("manifestSha256") != sealed_digest(sealed):
        raise SystemExit("Sealed prediction-blind manifest required")
    paths = [
        root
        / "user_uploads-sessions"
        / str(record["sessionId"])
        / args.candidate_phase_root
        / "field_consensus.json"
        for record in sealed["documents"]
    ]
    if len(paths) != 15 or not all(path.is_file() for path in paths):
        raise SystemExit("Candidate artifacts are incomplete for the sealed replay")
    if args.oracle_phase_root:
        oracle_paths = [
            root
            / "user_uploads-sessions"
            / str(record["sessionId"])
            / args.oracle_phase_root
            / "field_consensus.json"
            for record in sealed["documents"]
        ]
        if len(oracle_paths) != 15 or not all(path.is_file() for path in oracle_paths):
            raise SystemExit("Oracle artifacts are incomplete for the sealed replay")
    documents = make_documents(
        root,
        sealed,
        args.candidate_phase_root,
        args.candidate_result_key,
        args.oracle_phase_root,
    )
    field_count = len(documents) * len(FIELD_ORDER)
    if len(documents) != sealed.get("documentCount") or field_count != 120:
        raise SystemExit("Replay and sealed scope differ")
    before, after = evaluate_variant(documents, "baseline"), evaluate_variant(documents, "phase11_10")
    improvements = sum(value(document["baseline"].get(name)) != value(document["groundTruth"].get(name)) and value(document["phase11_10"].get(name)) == value(document["groundTruth"].get(name)) for document in documents for name in FIELD_ORDER)
    regressions = sum(value(document["baseline"].get(name)) == value(document["groundTruth"].get(name)) and value(document["phase11_10"].get(name)) != value(document["groundTruth"].get(name)) for document in documents for name in FIELD_ORDER)
    schema_errors = sum(not isinstance(document["phase11_10"].get(name), dict) for document in documents for name in FIELD_ORDER)
    all_manual = all(field.get("status") != "accepted" for document in documents for field in document["phase11_10"].values() if isinstance(field, dict))
    protected_regressions = sum(value(document["baseline"].get(name)) != value(document["phase11_10"].get(name)) for document in documents for name in PROTECTED_FIELDS)
    snapshot, observed = snapshot_status(before, after, len(documents), field_count)
    automatic_roi = automatic_roi_report(root, sealed)
    roi_attribution = roi_failure_attribution(root, sealed)
    baseline_classes, candidate_classes = class_report(documents, "baseline"), class_report(documents, "phase11_10")
    oracle_classes = class_report(documents, "oracle") if args.oracle_phase_root else None
    gates = diagnostic_gates(before, after, improvements=improvements, regressions=regressions, schema_errors=schema_errors, all_manual_review=all_manual, protected_regressions=protected_regressions, snapshot_status=snapshot, document_count=len(documents), evaluated_field_count=field_count, automatic_roi={name: item["accuracy"] for name, item in automatic_roi.items()})
    candidate_tag = f"candidate_{args.candidate_version.replace('.', '_')}"
    candidate_protocol = (
        "ORACLE_LINE_DIAGNOSTIC"
        if args.candidate_version == "11.10.0"
        else "AUTO_DETECTOR"
    )
    report_schema = (
        "ocr-ho-v2-016a-r1-diagnostic/1.0.0"
        if args.oracle_phase_root
        else "ocr-ho-v2-015-diagnostic/1.0.0"
        if args.candidate_version == "11.10.0"
        else "ocr-ho-v2-016b-development/1.0.0"
        if args.candidate_version == "11.10.2"
        else "ocr-ho-v2-016a-development/1.0.0"
    )
    oracle_tag = f"oracle_{args.candidate_version.replace('.', '_')}"
    oracle_paths = [
        root
        / "user_uploads-sessions"
        / str(record["sessionId"])
        / args.oracle_phase_root
        / "field_consensus.json"
        for record in sealed["documents"]
    ] if args.oracle_phase_root else []
    report = {
        "schemaVersion": report_schema,
        "candidateVersion": args.candidate_version,
        "baselineVersion": "11.9.1",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": len(documents),
        "evaluatedFieldCount": field_count,
        "containsRawPII": False,
        "predictionOpened": False,
        "candidateArtifactDigest": candidate_artifact_digest(paths),
        **({"oracleArtifactDigest": candidate_artifact_digest(oracle_paths)} if oracle_classes else {}),
        "sealedManifestSha256": sealed["manifestSha256"],
        "sealedManifestFileSha256": file_sha256(sealed_path),
        "protocols": {
            "gate": "AUTO_DETECTOR",
            "candidateMetrics": candidate_protocol,
            "oracleDiagnostic": "ORACLE_LINE_DIAGNOSTIC" if oracle_classes else "NOT_RUN",
        },
        "snapshot": {"status": snapshot, "expected": SNAPSHOT_EXPECTED, "observed": observed},
        "metrics": {
            "baseline_11_9_1": before,
            candidate_tag: after,
            **({oracle_tag: evaluate_variant(documents, "oracle")} if oracle_classes else {}),
        },
        "derBreakdown": {
            "baseline_11_9_1": der_breakdown(documents, "baseline"),
            candidate_tag: der_breakdown(documents, "phase11_10"),
            **({oracle_tag: der_breakdown(documents, "oracle")} if oracle_classes else {}),
        },
        "errorAnalyzer": {
            "classes": CLASS_NAMES,
            "baseline_11_9_1": baseline_classes,
            candidate_tag: candidate_classes,
            **({oracle_tag: oracle_classes} if oracle_classes else {}),
            "transitionByField": error_transition(documents),
            **({"oracleTransitionByField": error_transition(documents, "oracle")} if oracle_classes else {}),
        },
        "roiDiagnostics": {
            "automaticDetector": automatic_roi,
            "failureAttribution": roi_attribution,
            "oracleLineDiagnostic": oracle_classes["roiByField"] if oracle_classes else {"status": "NOT_RUN"},
        },
        "gates": gates,
        "exactImprovementCount": improvements,
        "exactRegressionCount": regressions,
        "schemaErrorCount": schema_errors,
        "protectedFieldRegressionCount": protected_regressions,
        "replay": {
            "candidatePhaseRoot": args.candidate_phase_root,
            **({"oraclePhaseRoot": args.oracle_phase_root} if oracle_classes else {}),
            "lineMapping": (
                "sealed_ground_truth_line_ids_oracle_only"
                if candidate_protocol == "ORACLE_LINE_DIAGNOSTIC"
                else "AUTO_DETECTOR"
            ),
        },
    }
    output = (args.output or root / "output" / "phase11" / "reports" / "CCCD_OCR_HO_V2_015_DIAGNOSTIC.json").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["gates"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
