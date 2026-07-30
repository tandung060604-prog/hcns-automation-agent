#!/usr/bin/env python3
"""Replay 15 consumed held-out documents through the current localhost pipeline.

This is a post-Ground-Truth audit. It writes only to private-data, preserves the
sealed evaluate-once artifacts and is never eligible for model promotion.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from hcns_agent.application.phase16_heldout import (  # noqa: E402
    LOCKED_POLICY_DIGEST,
    METRIC_SPEC_VERSION,
    evaluate_once,
    sha256_file,
)

REPLAY_IDS = (
    "H16-C-001",
    "H16-C-002",
    "H16-C-003",
    "H16-C-004",
    "H16-C-005",
    "H16-AR-001",
    "H16-CD-001",
    "H16-CD-003",
    "H16-CD-004",
    "H16-DC-001",
    "H16-DC-002",
    "H16-DC-003",
    "H16-DC-004",
    "H16-EFT-001",
    "H16-EFT-003",
)
EXPECTED_PARSER_VERSION = "phase17-structured-hr-parser/2.0.0"
EXPECTED_VISUAL_PROFILE = "phase14.8-seq2seq-transformer-verifier"
EXPECTED_DETECTOR = "PP-OCRv5_mobile_det"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8765/user/upload",
    )
    parser.add_argument(
        "--sessions-root",
        type=Path,
        help=(
            "Optional localhost session root. A SHA-256-identical result is "
            "reused only when it already matches the current v5/parser policy."
        ),
    )
    parser.add_argument(
        "--stage",
        choices=("run", "evaluate"),
        required=True,
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path.name}")
    return value


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def replay_root(dataset_root: Path) -> Path:
    return dataset_root / "predictions" / "latest_live_v5_replay_private"


def selected_documents(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_id = {
        str(document["documentId"]): document
        for document in manifest.get("documents", [])
    }
    missing = [document_id for document_id in REPLAY_IDS if document_id not in by_id]
    if missing:
        raise ValueError(f"Replay manifest is missing IDs: {missing}")
    return [by_id[document_id] for document_id in REPLAY_IDS]


def multipart_body(
    *,
    filename: str,
    content: bytes,
    media_type: str,
) -> tuple[bytes, str]:
    boundary = f"----hcns-replay-{uuid.uuid4().hex}"
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {media_type}\r\n\r\n"
    ).encode("ascii")
    body = prefix + content + f"\r\n--{boundary}--\r\n".encode("ascii")
    return body, boundary


def upload_document(
    api_url: str,
    *,
    document_id: str,
    source_path: Path,
) -> dict[str, Any]:
    content = source_path.read_bytes()
    safe_filename = f"{document_id}{source_path.suffix.casefold()}"
    media_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
    body, boundary = multipart_body(
        filename=safe_filename,
        content=content,
        media_type=media_type,
    )
    request = urllib.request.Request(
        api_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=3600) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Local OCR API rejected {document_id} with HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Local OCR API is unavailable") from exc
    if not isinstance(payload, dict):
        raise TypeError("Local OCR API returned an invalid payload")
    return payload


def reusable_result(
    sessions_root: Path | None,
    source_sha256: str,
) -> dict[str, Any] | None:
    if sessions_root is None or not sessions_root.is_dir():
        return None
    candidates: list[tuple[float, dict[str, Any]]] = []
    for session_dir in sessions_root.iterdir():
        if not session_dir.is_dir():
            continue
        inputs = list((session_dir / "input").glob("*"))
        result_path = session_dir / "result.json"
        if len(inputs) != 1 or not result_path.is_file():
            continue
        if sha256_file(inputs[0]) != source_sha256:
            continue
        try:
            result = load_json(result_path)
            phase15 = result.get("phase15", {})
            extraction = phase15.get("extraction", {})
            processing = result.get("processing", {})
            if extraction.get("parserVersion") != EXPECTED_PARSER_VERSION:
                continue
            if processing.get("profile") != "phase12_native":
                models = processing.get("models", {})
                if (
                    processing.get("profile") != EXPECTED_VISUAL_PROFILE
                    or models.get("textDetection") != EXPECTED_DETECTOR
                ):
                    continue
            candidates.append((result_path.stat().st_mtime, result))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def prediction_document(
    source: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    phase15 = result.get("phase15")
    if not isinstance(phase15, dict):
        raise ValueError("Local pipeline did not produce Phase 15 output")
    classification = phase15.get("classification")
    extraction = phase15.get("extraction")
    if not isinstance(classification, dict) or not isinstance(extraction, dict):
        raise ValueError("Local pipeline returned an incomplete Phase 15 result")
    if extraction.get("parserVersion") != EXPECTED_PARSER_VERSION:
        raise ValueError("Local pipeline did not use the locked Phase 17 parser")

    processing = result.get("processing", {})
    source_format = str(source.get("sourceFormat", "")).upper()
    is_native = processing.get("profile") == "phase12_native"
    if not is_native:
        if processing.get("profile") != EXPECTED_VISUAL_PROFILE:
            raise ValueError("Visual input did not use the Phase 14.8 recognizer policy")
        models = processing.get("models", {})
        if models.get("textDetection") != EXPECTED_DETECTOR:
            raise ValueError("Visual input did not use the current PP-OCRv5 detector")

    return {
        "documentId": source["documentId"],
        "sourceSha256": source["sourceSha256"],
        "sourceFormat": source_format,
        "pipelineMode": "NATIVE" if is_native else "OCR_V5_PHASE14_8",
        "sessionId": result.get("sessionId"),
        "documentFamily": classification["documentFamily"],
        "documentType": classification["documentType"],
        "classificationStatus": classification["status"],
        "classificationConfidence": classification["confidence"],
        "fields": extraction.get("fields", {}),
        "tables": extraction.get("tables", []),
        "summary": extraction.get("summary", {}),
    }


def run(args: argparse.Namespace) -> None:
    dataset_root = args.dataset_root.resolve()
    output_root = replay_root(dataset_root)
    output_path = output_root / "latest_live_v5_predictions_private.json"
    progress_path = output_root / "progress_private.json"
    if output_path.exists() and not args.overwrite:
        raise FileExistsError("Live v5 replay already exists; pass --overwrite")

    manifest = load_json(dataset_root / "manifest_private.json")
    selected = selected_documents(manifest)
    progress = (
        load_json(progress_path)
        if progress_path.is_file() and not args.overwrite
        else {
            "schemaVersion": "phase17-live-v5-replay-progress/1.0.0",
            "createdAt": utc_now(),
            "containsRealPII": True,
            "documents": [],
        }
    )
    completed = {
        str(document["documentId"]): document
        for document in progress.get("documents", [])
    }

    for index, source in enumerate(selected, start=1):
        document_id = str(source["documentId"])
        if document_id in completed:
            print(f"Live v5 replay {index}/{len(selected)} resumed (content hidden)")
            continue
        source_path = dataset_root / str(source["sourcePath"])
        if sha256_file(source_path) != source["sourceSha256"]:
            raise ValueError("Replay source no longer matches manifest SHA-256")
        result = reusable_result(args.sessions_root, str(source["sourceSha256"]))
        reused = result is not None
        if result is None:
            result = upload_document(
                args.api_url,
                document_id=document_id,
                source_path=source_path,
            )
        prediction = prediction_document(source, result)
        completed[document_id] = prediction
        progress["documents"] = [
            completed[key]
            for key in REPLAY_IDS
            if key in completed
        ]
        progress["updatedAt"] = utc_now()
        atomic_json(progress_path, progress)
        action = "reused" if reused else "processed"
        print(
            f"Live v5 replay {index}/{len(selected)} {action} "
            "(content hidden)"
        )

    predictions = [completed[document_id] for document_id in REPLAY_IDS]
    atomic_json(
        output_path,
        {
            "schemaVersion": "phase17-live-v5-replay-predictions/1.0.0",
            "createdAt": utc_now(),
            "containsRealPII": True,
            "evaluationKind": "POST_GROUND_TRUTH_LIVE_V5_REPLAY_AUDIT",
            "groundTruthUsedDuringPrediction": False,
            "groundTruthWasAlreadyAvailable": True,
            "promotionEligible": False,
            "datasetId": manifest["datasetId"],
            "datasetDigest": manifest["datasetDigest"],
            "documentCount": len(predictions),
            "ocrPipeline": (
                "PP-OCRv5 detector -> VietOCR vgg_seq2seq primary "
                "-> vgg_transformer verifier"
            ),
            "recognitionPolicyDigest": LOCKED_POLICY_DIGEST,
            "parserVersion": EXPECTED_PARSER_VERSION,
            "metricSpecVersion": METRIC_SPEC_VERSION,
            "documents": predictions,
        },
    )


def subset_document_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    selected = set(REPLAY_IDS)
    return {
        **payload,
        "documents": [
            document
            for document in payload.get("documents", [])
            if str(document.get("documentId")) in selected
        ],
    }


def metric_delta(
    baseline: Mapping[str, Any],
    latest: Mapping[str, Any],
) -> dict[str, float]:
    keys = (
        "classificationAccuracy",
        "fieldExactMatchRate",
        "fieldCompleteness",
        "acceptedFieldRate",
        "cer",
        "wer",
        "der",
        "tableExactRowRate",
        "tableExactCellRate",
        "tableCompleteness",
    )
    return {
        key: round(float(latest.get(key, 0)) - float(baseline.get(key, 0)), 6)
        for key in keys
    }


def evaluate(args: argparse.Namespace) -> None:
    dataset_root = args.dataset_root.resolve()
    output_root = replay_root(dataset_root)
    output_path = output_root / "latest_live_v5_evaluation.json"
    if output_path.exists() and not args.overwrite:
        raise FileExistsError("Live v5 replay evaluation already exists")
    truth = subset_document_payload(
        load_json(
            dataset_root
            / "ground_truth"
            / "ground_truth_confirmed_private.json"
        )
    )
    baseline = subset_document_payload(
        load_json(
            dataset_root
            / "predictions"
            / "sealed_predictions_private.json"
        )
    )
    latest_predictions = load_json(
        output_root / "latest_live_v5_predictions_private.json"
    )
    baseline_metrics = evaluate_once(baseline, truth)
    latest_metrics = evaluate_once(
        {
            **latest_predictions,
            "predictionsHiddenDuringReview": True,
        },
        truth,
    )
    atomic_json(
        output_path,
        {
            "schemaVersion": "phase17-live-v5-replay-evaluation/1.0.0",
            "evaluatedAt": utc_now(),
            "containsRealPII": False,
            "evaluationKind": "POST_GROUND_TRUTH_LIVE_V5_REPLAY_AUDIT",
            "documentCount": len(REPLAY_IDS),
            "ocrPipeline": latest_predictions["ocrPipeline"],
            "nativeDocumentCount": sum(
                document["pipelineMode"] == "NATIVE"
                for document in latest_predictions["documents"]
            ),
            "visualDocumentCount": sum(
                document["pipelineMode"] == "OCR_V5_PHASE14_8"
                for document in latest_predictions["documents"]
            ),
            "groundTruthWasAlreadyAvailable": True,
            "eligibleForPromotion": False,
            "thresholdRetuned": False,
            "sealedReference": {
                "parserVersion": baseline.get("parserVersion"),
                "recognitionPolicyDigest": baseline.get(
                    "recognitionPolicyDigest"
                ),
            },
            "latestReplay": {
                "parserVersion": latest_predictions["parserVersion"],
                "recognitionPolicyDigest": latest_predictions[
                    "recognitionPolicyDigest"
                ],
                "ocrPipeline": latest_predictions["ocrPipeline"],
            },
            "baseline": baseline_metrics,
            "latest": latest_metrics,
            "delta": metric_delta(
                baseline_metrics["overall"],
                latest_metrics["overall"],
            ),
            "byFamilyDelta": {
                family: metric_delta(
                    baseline_metrics["byFamily"][family],
                    latest_metrics["byFamily"][family],
                )
                for family in latest_metrics["byFamily"]
            },
            "decision": {
                "status": "LIVE_V5_REPLAY_AUDIT_ONLY",
                "production": "NOT_PRODUCTION_READY",
                "reason": (
                    "Ground Truth existed before replay; collect a new held-out "
                    "corpus before any promotion decision."
                ),
            },
        },
    )


def main() -> int:
    args = parse_args()
    if args.stage == "run":
        run(args)
    else:
        evaluate(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
