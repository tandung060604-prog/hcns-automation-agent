#!/usr/bin/env python3
"""Run the locked Phase 11.5 CCCD multi-recognizer development benchmark."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import cv2

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "ocr_lab" / "api"
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from phase11_5_cccd import (  # noqa: E402
    FIELD_ORDER,
    build_crop_variants,
    build_identity_card,
    business_values,
    field_candidate,
    locate_field_regions,
)
from serve_dashboard_api import UserOCRService  # noqa: E402

TARGET_FIELDS = FIELD_ORDER
prepare_line_pages = None
assemble_line_candidates = None
phase_module: Any = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--secondary-python", type=Path, required=True)
    parser.add_argument(
        "--secondary-pythonpath",
        type=Path,
        action="append",
        default=[],
        help="Additional site-package roots visible only to the secondary worker.",
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=REPO_ROOT / "config" / "phase11_5_cccd_policy.json",
    )
    parser.add_argument("--phase-module", default="phase11_5_cccd")
    parser.add_argument("--phase-key", default="phase11_5")
    parser.add_argument("--phase-version", default="11.5.0")
    parser.add_argument("--phase-root", default="phase11_5")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--paddle-only",
        action="store_true",
        help="Publish the primary Paddle candidates without optional secondary OCR.",
    )
    parser.add_argument("--document-index", type=int, action="append", default=[])
    return parser.parse_args()


def configure_phase(module_name: str) -> None:
    global phase_module
    module = importlib.import_module(module_name)
    phase_module = module
    globals().update(
        {
            "FIELD_ORDER": module.FIELD_ORDER,
            "TARGET_FIELDS": getattr(module, "TARGET_FIELDS", module.FIELD_ORDER),
            "build_crop_variants": module.build_crop_variants,
            "build_identity_card": module.build_identity_card,
            "business_values": module.business_values,
            "field_candidate": module.field_candidate,
            "locate_field_regions": module.locate_field_regions,
            "assemble_line_candidates": getattr(module, "assemble_line_candidates", None),
            "prepare_line_pages": getattr(module, "prepare_line_pages", None),
        }
    )


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def session_root(data_root: Path) -> Path:
    """Resolve normal or archived development session layout."""

    archived = data_root / "user_uploads-sessions"
    if archived.is_dir():
        return archived
    normal = data_root / "user_uploads" / "sessions"
    if normal.is_dir():
        return normal
    raise FileNotFoundError(f"No CCCD session root under {data_root}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_locks(args: argparse.Namespace) -> None:
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    locks = {item["profile"]: item["sha256"] for item in policy["modelLocks"]}
    paths = {
        "paddle_ppocrv5_detector": (
            Path.home()
            / ".paddlex"
            / "official_models"
            / "PP-OCRv5_mobile_det"
            / "inference.pdiparams"
        ),
        "paddle_ppocrv5_recognizer": (
            Path.home()
            / ".paddlex"
            / "official_models"
            / "latin_PP-OCRv5_mobile_rec"
            / "inference.pdiparams"
        ),
    }
    for profile, path in paths.items():
        if not path.is_file() or sha256(path) != locks[profile]:
            raise RuntimeError(f"Locked model mismatch: {profile}")


def paddle_candidate(
    service: UserOCRService,
    crop_path: Path,
    field_name: str,
    variant: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    prediction = service.predict_page(crop_path, None)
    raw_value = " ".join(prediction.get("recognizedTexts", []))
    return {
        "value": field_candidate(field_name, raw_value),
        "rawValue": raw_value,
        "confidence": float(prediction.get("avgConfidence") or 0.0),
        "durationMs": round((time.perf_counter() - started) * 1000, 3),
        "profile": "paddle_ppocrv5",
        "variant": variant,
        "lines": [
            {
                "text": text,
                "confidence": score,
                "bbox": box,
            }
            for text, score, box in zip(
                prediction.get("recognizedTexts", []),
                prediction.get("recognitionScores", []),
                prediction.get("recognizedBoxes", []),
                strict=False,
            )
        ],
    }


def prepare(
    args: argparse.Namespace,
    records: list[dict[str, Any]],
    work_root: Path,
    checkpoint_path: Path | None = None,
    prepared: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    service = UserOCRService(args.data_root)
    jobs: list[dict[str, Any]] = list((prepared or {}).get("jobs", []))
    documents: list[dict[str, Any]] = list((prepared or {}).get("documents", []))
    completed_sessions = {str(item.get("sessionId")) for item in documents}
    sessions_root = session_root(args.data_root)
    for record in records:
        session_id = str(record["sessionId"])
        if session_id in completed_sessions:
            continue
        session_dir = sessions_root / session_id
        result = json.loads((session_dir / "result.json").read_text(encoding="utf-8"))
        pages = result.get("phase11", {}).get("pages") or []
        page_paths = sorted((session_dir / "phase11" / "pages").glob("page_*.png"))
        if not page_paths:
            page_paths = sorted((session_dir / "pages").glob("page_*.png"))
        images = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in page_paths]
        if not images or any(image is None for image in images):
            raise RuntimeError(f"Missing selected CCCD page: {session_id}")
        if prepare_line_pages is not None:
            pages, images = prepare_line_pages(session_dir, pages, images)
        regions = locate_field_regions(
            pages,
            [(image.shape[1], image.shape[0]) for image in images],
        )
        confirmed_fields = record.get("fields") or {}
        if confirmed_fields:
            boxes = (pages[0] if pages else {}).get("recognizedBoxes", [])
            all_lines = [
                {"lineId": index, "box": box}
                for index, box in enumerate(boxes)
            ]
            for field_name, field in confirmed_fields.items():
                if field_name not in regions or not isinstance(field, dict):
                    continue
                line_ids = field.get("lineIds") or []
                if not line_ids:
                    continue
                selected = []
                for line_id in line_ids:
                    if not isinstance(line_id, int) or not 0 <= line_id < len(boxes):
                        raise ValueError(f"Invalid confirmed line ID {session_id}:{field_name}:{line_id}")
                    selected.append({"lineId": line_id, "box": boxes[line_id]})
                regions[field_name]["lineBboxes"] = [
                    phase_module._trim_line_top(item, all_lines)
                    if hasattr(phase_module, "_trim_line_top")
                    else [
                        int(min(point[0] for point in item["box"])),
                        int(min(point[1] for point in item["box"])),
                        int(max(point[0] for point in item["box"])),
                        int(max(point[1] for point in item["box"])),
                    ]
                    for item in selected
                ]
                regions[field_name]["lineIds"] = line_ids
                regions[field_name]["regionSource"] = "sealed_gt_line_mapping"
        candidates: dict[str, list[dict[str, Any]]] = {name: [] for name in FIELD_ORDER}
        crop_records: dict[str, Any] = {}
        for field_name in TARGET_FIELDS:
            region = regions[field_name]
            line_bboxes = region.get("lineBboxes") or [region["bbox"]]
            crop_records[field_name] = {}
            for line_order, line_bbox in enumerate(line_bboxes):
                variants = build_crop_variants(images[int(region["pageIndex"])], line_bbox)
                for variant_name, variant in variants.items():
                    suffix = f"-line{line_order}" if len(line_bboxes) > 1 else ""
                    case_id = (
                        f"{int(record['documentIndex']):03d}-{field_name}{suffix}-{variant_name}"
                    )
                    crop_path = (
                        work_root
                        / "crops"
                        / f"{int(record['documentIndex']):03d}"
                        / f"{field_name}_line{line_order}_{variant_name}.png"
                    )
                    crop_path.parent.mkdir(parents=True, exist_ok=True)
                    if not cv2.imwrite(str(crop_path), variant["image"]):
                        raise OSError(f"Cannot write crop: {crop_path}")
                    candidate = paddle_candidate(service, crop_path, field_name, variant_name)
                    candidate["lineOrder"] = line_order
                    candidate["lineId"] = (region.get("lineIds") or [None])[line_order]
                    candidates[field_name].append(candidate)
                    jobs.append(
                        {
                            "caseId": case_id,
                            "documentIndex": int(record["documentIndex"]),
                            "fieldName": field_name,
                            "variant": variant_name,
                            "lineOrder": line_order,
                            "lineId": candidate["lineId"],
                            "cropPath": str(crop_path),
                        }
                    )
                    crop_records[field_name][f"line{line_order}_{variant_name}"] = {
                        "caseId": case_id,
                        "path": str(crop_path),
                        "sha256": sha256(crop_path),
                        "paddle": candidate,
                    }
        documents.append(
            {
                "documentIndex": int(record["documentIndex"]),
                "sessionId": session_id,
                "regions": regions,
                "crops": crop_records,
                "candidates": candidates,
            }
        )
        if checkpoint_path is not None:
            write_json(checkpoint_path, {"complete": False, "jobs": jobs, "documents": documents})
        print(
            json.dumps(
                {
                    "stage": "paddle",
                    "documentIndex": int(record["documentIndex"]),
                    "documentCount": len(records),
                }
            ),
            flush=True,
        )
    return jobs, documents


def merge_secondary(
    documents: list[dict[str, Any]],
    secondary: dict[str, Any],
) -> None:
    predictions = secondary["results"]
    for document in documents:
        for field_name, crop_profiles in document["crops"].items():
            for variant_name, crop in crop_profiles.items():
                for profile, prediction in predictions[crop["caseId"]].items():
                    document["candidates"][field_name].append(
                        {
                            "value": field_candidate(
                                field_name,
                                prediction.get("value"),
                            ),
                            "rawValue": prediction.get("value"),
                            "confidence": prediction.get("confidence", 0.0),
                            "durationMs": prediction.get("durationMs", 0.0),
                            "profile": profile,
                            "variant": variant_name,
                            "lines": prediction.get("lines", []),
                            "lineOrder": crop["paddle"].get("lineOrder", 0),
                            "lineId": crop["paddle"].get("lineId"),
                        }
                    )


def publish(
    args: argparse.Namespace,
    documents: list[dict[str, Any]],
    work_root: Path,
) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    sessions_root = session_root(args.data_root)
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    for document in documents:
        started = time.perf_counter()
        recognition_duration_ms = round(
            sum(
                float(candidate.get("durationMs") or 0.0)
                for candidates in document["candidates"].values()
                for candidate in candidates
            ),
            3,
        )
        session_dir = sessions_root / document["sessionId"]
        result_path = session_dir / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        baseline_fields = None
        if args.phase_key != "phase11_5":
            baseline_path = session_dir / "phase11_5" / "identity_card.json"
            if not baseline_path.is_file():
                raise FileNotFoundError(
                    f"Phase 11.5 baseline is required for protected replay: {baseline_path}"
                )
            baseline_fields = json.loads(baseline_path.read_text(encoding="utf-8")).get(
                "fields", {}
            )
        candidates = document["candidates"]
        if assemble_line_candidates:
            candidates = assemble_line_candidates(candidates)
        identity_card = build_identity_card(
            candidates,
            document["regions"],
            **({"baseline_fields": baseline_fields} if baseline_fields is not None else {}),
        )
        current_identity = result.get("phase11", {}).get("identityCard")
        history = session_dir / "phase11" / "history" / "identity_card_phase11_4.json"
        if current_identity and not history.is_file():
            write_json(history, current_identity)
        if args.phase_key != "phase11_5" and current_identity:
            prior_identity = session_dir / "phase11_5" / "identity_card.json"
            if not prior_identity.is_file():
                write_json(prior_identity, current_identity)
        write_json(session_dir / "phase11" / "identity_card.json", identity_card)
        result.setdefault("phase11", {})["version"] = args.phase_version
        result["phase11"]["identityCard"] = identity_card
        result["phase11"]["status"] = "NEEDS_REVIEW"
        result["document"]["structuredFields"] = identity_card["fields"]
        policy_duration_ms = round((time.perf_counter() - started) * 1000, 3)
        total_duration_ms = round(
            recognition_duration_ms + policy_duration_ms,
            3,
        )
        result[args.phase_key] = {
            "version": args.phase_version,
            "status": "COMPLETE",
            "mode": "SHADOW_REVIEW_ONLY",
            "strategy": policy.get(
                "strategy",
                "normalized_roi_four_recognizer_consensus",
            ),
            "recognizers": (
                ["paddle_ppocrv5"]
                if args.paddle_only
                else [
                    "paddle_ppocrv5",
                    "easyocr_vi",
                    "vietocr_vgg_seq2seq",
                    "vietocr_vgg_transformer",
                ]
            ),
            "cropProfiles": [
                "color_original",
                "grayscale_clahe",
                "lanczos_upscale",
                "balanced_padding",
            ],
            "policyLock": {
                "recognitionPolicySha256": policy["recognitionPolicySha256"],
                "cropProfileSha256": policy["cropProfileSha256"],
                "schemaSha256": policy["schemaSha256"],
                "modelSha256": {item["profile"]: item["sha256"] for item in policy["modelLocks"]},
            },
            "recognitionDurationMs": recognition_duration_ms,
            "policyDurationMs": policy_duration_ms,
            "durationMs": total_duration_ms,
        }
        result.setdefault("processing", {})[f"{args.phase_key}DurationMs"] = total_duration_ms
        write_json(result_path, result)
        private_path = session_dir / args.phase_root / "field_consensus.json"
        write_json(
            session_dir / args.phase_root / "business.json",
            {
                "schemaVersion": f"{args.phase_key.replace('_', '.')}-cccd-business/1.0.0",
                "documentType": "VIETNAM_CITIZEN_ID_FRONT",
                "containsRealPII": True,
                "policyMode": "SHADOW_REVIEW_ONLY",
                "fields": business_values(identity_card),
                "note": (
                    "Only accepted Unicode values are exposed; asciiValue "
                    "never replaces a legal field value."
                ),
            },
        )
        write_json(
            private_path,
            {
                "schemaVersion": (f"{args.phase_key.replace('_', '.')}-private-evidence/1.0.0"),
                "containsRealPII": True,
                "sessionId": document["sessionId"],
                "policyLock": result[args.phase_key]["policyLock"],
                "regions": document["regions"],
                "crops": document["crops"],
                "candidates": candidates,
                "identityCard": identity_card,
            },
        )
        sanitized.append(
            {
                "documentIndex": document["documentIndex"],
                "status": "SUCCESS",
                "presentFieldCount": identity_card["summary"]["presentFieldCount"],
                "acceptedFieldCount": identity_card["summary"]["acceptedFieldCount"],
                "needsReviewFieldCount": identity_card["summary"]["needsReviewFieldCount"],
                "documentCompleteness": identity_card["summary"]["documentCompleteness"],
                "durationMs": total_duration_ms,
            }
        )
    return sanitized


def main() -> int:
    args = parse_args()
    configure_phase(args.phase_module)
    verify_model_locks(args)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = [
        record
        for record in (manifest.get("records") or [
            {
                "documentIndex": item.get("documentIndex"),
                "sessionId": item.get("sessionId") or item.get("documentId"),
                "selectedRotationDegrees": item.get("selectedRotationDegrees", 0),
                "fields": item.get("fields", {}),
            }
            for item in manifest.get("documents", [])
        ])
        if record.get("sessionId")
        and (not args.document_index or int(record["documentIndex"]) in args.document_index)
    ]
    if not records:
        raise SystemExit("No selected CCCD sessions")
    work_root = args.manifest.parent / f"{args.phase_root}_private"
    prepared_path = work_root / "prepared_private.json"
    job_path = work_root / "secondary_job_private.json"
    secondary_path = work_root / "secondary_predictions_private.json"
    prepared = None
    if prepared_path.is_file() and not args.overwrite:
        prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    if prepared and prepared.get("complete") is True:
        jobs, documents = prepared["jobs"], prepared["documents"]
    else:
        jobs, documents = prepare(args, records, work_root, prepared_path, prepared)
        write_json(prepared_path, {"complete": True, "jobs": jobs, "documents": documents})
        write_json(job_path, {"items": jobs})
    if args.prepare_only:
        return 0
    if not job_path.is_file():
        write_json(job_path, {"items": jobs})
    if args.paddle_only:
        secondary = {"results": {}}
    elif not secondary_path.is_file() or args.overwrite:
        command = [
            str(args.secondary_python),
            str(REPO_ROOT / "scripts" / "phase11_5_secondary_worker.py"),
            "--job",
            str(job_path),
            "--output",
            str(secondary_path),
            "--runtime-root",
            str(args.runtime_root),
            "--policy",
            str(args.policy),
        ]
        secondary_env = None
        if args.secondary_pythonpath:
            secondary_env = os.environ.copy()
            extra_path = os.pathsep.join(str(path.resolve()) for path in args.secondary_pythonpath)
            inherited = secondary_env.get("PYTHONPATH")
            secondary_env["PYTHONPATH"] = (
                extra_path + os.pathsep + inherited if inherited else extra_path
            )
        subprocess.run(command, check=True, env=secondary_env)
        secondary = json.loads(secondary_path.read_text(encoding="utf-8"))
    else:
        secondary = json.loads(secondary_path.read_text(encoding="utf-8"))
    if not args.paddle_only:
        merge_secondary(documents, secondary)
    records_out = publish(args, documents, work_root)
    summary = {
        "documentCount": len(records_out),
        "successfulDocumentCount": sum(record["status"] == "SUCCESS" for record in records_out),
        "meanCompleteness": round(
            mean(record["documentCompleteness"] for record in records_out),
            6,
        ),
        "acceptedFieldCount": sum(record["acceptedFieldCount"] for record in records_out),
        "meanDurationMs": round(
            mean(record["durationMs"] for record in records_out),
            3,
        ),
    }
    report = {
        "schemaVersion": f"{args.phase_key.replace('_', '.')}-run/1.0.0",
        "createdAt": utc_now(),
        "containsRawPII": False,
        "status": "SHADOW_REVIEW_ONLY",
        "manifestSha256": sha256(args.manifest),
        "policyConfigSha256": sha256(args.policy),
        "records": records_out,
        "summary": summary,
    }
    write_json(args.manifest.parent / f"{args.phase_key.upper()}_RESULTS.json", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
