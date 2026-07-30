#!/usr/bin/env python3
"""Replay 15 consumed Phase 16 documents with the current locked pipeline.

This is a post-Ground-Truth audit, not a new held-out evaluation. It never
overwrites the sealed predictions or the evaluate-once report.
"""

from __future__ import annotations

import argparse
import sys
from argparse import Namespace
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "ocr_lab" / "api"
SRC_ROOT = ROOT / "src"
for import_root in (ROOT, API_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from phase12_ingestion import ingest_document  # noqa: E402
from phase15_idp import (  # noqa: E402
    IDP_PARSER_VERSION,
    classify_phase15_document,
    extract_phase15_document,
)

from hcns_agent.application.phase16_heldout import (  # noqa: E402
    LOCKED_POLICY_DIGEST,
    METRIC_SPEC_VERSION,
    evaluate_once,
    sha256_file,
)
from scripts.phase15_benchmark import (  # noqa: E402
    POLICY_CONFIG,
    atomic_json,
    load_json,
    policy_config,
    render_pages,
    run_paddle,
    run_vietocr,
)
from scripts.validate_phase17_parser_lock import validate_lock  # noqa: E402

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
VISUAL_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def policy_prediction_document(
    source: Mapping[str, Any],
    classification: Mapping[str, Any],
    extraction: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "documentId": source["documentId"],
        "sourceSha256": source["sourceSha256"],
        "documentFamily": classification["documentFamily"],
        "documentType": classification["documentType"],
        "classificationStatus": classification["status"],
        "classificationConfidence": classification["confidence"],
        "fields": extraction["fields"],
        "tables": extraction.get("tables", []),
        "summary": extraction["summary"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--private-runtime", type=Path, required=True)
    parser.add_argument("--paddle-model-root", type=Path, required=True)
    parser.add_argument("--policy-config", type=Path, default=POLICY_CONFIG)
    parser.add_argument(
        "--stage",
        choices=("prepare", "paddle", "vietocr", "build", "evaluate"),
        required=True,
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def replay_root(dataset_root: Path) -> Path:
    return dataset_root / "predictions" / "latest_replay_private"


def runner_args(args: argparse.Namespace) -> Namespace:
    return Namespace(
        dataset_root=args.dataset_root.resolve(),
        work_root=replay_root(args.dataset_root.resolve()),
        policy_config=args.policy_config,
        private_runtime=args.private_runtime,
        paddle_model_root=args.paddle_model_root,
        overwrite=args.overwrite,
    )


def selected_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {
        str(document["documentId"]): document
        for document in manifest.get("documents", [])
    }
    missing = [document_id for document_id in REPLAY_IDS if document_id not in by_id]
    if missing:
        raise ValueError(f"Replay manifest is missing IDs: {missing}")
    return [by_id[document_id] for document_id in REPLAY_IDS]


def prepare(args: argparse.Namespace) -> None:
    validate_lock()
    dataset_root = args.dataset_root.resolve()
    output_root = replay_root(dataset_root)
    output_path = output_root / "prepared_manifest_private.json"
    if output_path.exists() and not args.overwrite:
        raise FileExistsError("Latest replay is already prepared")
    manifest = load_json(dataset_root / "manifest_private.json")
    policy = policy_config(args)
    documents = []
    for index, source in enumerate(selected_documents(manifest), start=1):
        source_path = dataset_root / str(source["sourcePath"])
        if sha256_file(source_path) != source["sourceSha256"]:
            raise ValueError("Replay source no longer matches manifest SHA-256")
        pages = (
            render_pages(
                source_path,
                output_root / "pages" / str(source["documentId"]),
            )
            if source_path.suffix.casefold() in VISUAL_SUFFIXES
            else []
        )
        documents.append(
            {
                **source,
                "pagePaths": [
                    path.relative_to(output_root).as_posix() for path in pages
                ],
                "pageSha256": [sha256_file(path) for path in pages],
            }
        )
        print(f"Replay prepare {index}/{len(REPLAY_IDS)} (content hidden)")
    atomic_json(
        output_path,
        {
            "schemaVersion": "phase17-latest-replay-input/1.0.0",
            "createdAt": utc_now(),
            "containsRealPII": True,
            "datasetKind": "CONSUMED_HELDOUT_POST_GT_REPLAY",
            "datasetId": manifest["datasetId"],
            "datasetDigest": manifest["datasetDigest"],
            "documentCount": len(documents),
            "visualDocumentCount": sum(bool(item["pagePaths"]) for item in documents),
            "recognitionPolicyDigest": policy["policy"]["policyDigest"],
            "parserVersion": IDP_PARSER_VERSION,
            "promotionEligible": False,
            "documents": documents,
        },
    )


def build(args: argparse.Namespace) -> None:
    validate_lock()
    dataset_root = args.dataset_root.resolve()
    output_root = replay_root(dataset_root)
    output_path = output_root / "latest_replay_predictions_private.json"
    if output_path.exists() and not args.overwrite:
        raise FileExistsError("Latest replay predictions already exist")
    prepared = load_json(output_root / "prepared_manifest_private.json")
    recognition = load_json(output_root / "phase15_recognition_private.json")
    recognition_by_id = {
        str(document["documentId"]): document
        for document in recognition["documents"]
    }
    predictions = []
    for index, source in enumerate(prepared["documents"], start=1):
        document_id = str(source["documentId"])
        recognized = recognition_by_id.get(document_id)
        if recognized is None:
            raise ValueError("Replay recognition output is incomplete")
        source_path = dataset_root / str(source["sourcePath"])
        canonical = ingest_document(source_path, recognized["pages"])
        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)
        if extraction.get("parserVersion") != IDP_PARSER_VERSION:
            raise ValueError("Replay extraction did not use the locked parser")
        predictions.append(
            policy_prediction_document(source, classification, extraction)
        )
        print(f"Replay build {index}/{prepared['documentCount']} (values hidden)")
    atomic_json(
        output_path,
        {
            "schemaVersion": "phase17-latest-replay-predictions/1.0.0",
            "createdAt": utc_now(),
            "containsRealPII": True,
            "evaluationKind": "POST_GROUND_TRUTH_REPLAY_AUDIT",
            "groundTruthUsedDuringPrediction": False,
            "groundTruthWasAlreadyAvailable": True,
            "promotionEligible": False,
            "datasetId": prepared["datasetId"],
            "datasetDigest": prepared["datasetDigest"],
            "documentCount": len(predictions),
            "recognitionPolicyDigest": LOCKED_POLICY_DIGEST,
            "parserVersion": IDP_PARSER_VERSION,
            "metricSpecVersion": METRIC_SPEC_VERSION,
            "documents": predictions,
        },
    )


def subset_document_payload(
    payload: dict[str, Any],
    *,
    documents_key: str = "documents",
) -> dict[str, Any]:
    selected = set(REPLAY_IDS)
    return {
        **payload,
        documents_key: [
            document
            for document in payload.get(documents_key, [])
            if str(document.get("documentId")) in selected
        ],
    }


def metric_delta(
    baseline: dict[str, Any],
    latest: dict[str, Any],
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
    validate_lock()
    dataset_root = args.dataset_root.resolve()
    output_root = replay_root(dataset_root)
    output_path = output_root / "latest_replay_evaluation.json"
    if output_path.exists() and not args.overwrite:
        raise FileExistsError("Latest replay evaluation already exists")
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
        output_root / "latest_replay_predictions_private.json"
    )
    pseudo_latest = {
        **latest_predictions,
        "predictionsHiddenDuringReview": True,
    }
    baseline_metrics = evaluate_once(baseline, truth)
    latest_metrics = evaluate_once(pseudo_latest, truth)
    by_family_delta = {
        family: metric_delta(
            baseline_metrics["byFamily"][family],
            latest_metrics["byFamily"][family],
        )
        for family in latest_metrics["byFamily"]
    }
    atomic_json(
        output_path,
        {
            "schemaVersion": "phase17-latest-replay-evaluation/1.0.0",
            "evaluatedAt": utc_now(),
            "containsRealPII": False,
            "evaluationKind": "POST_GROUND_TRUTH_REPLAY_AUDIT",
            "documentCount": len(REPLAY_IDS),
            "visualDocumentsReOcred": sum(
                Path(str(document["sourcePath"])).suffix.casefold()
                in VISUAL_SUFFIXES
                for document in selected_documents(
                    load_json(dataset_root / "manifest_private.json")
                )
            ),
            "nativeDocumentsReparsed": sum(
                Path(str(document["sourcePath"])).suffix.casefold()
                not in VISUAL_SUFFIXES
                for document in selected_documents(
                    load_json(dataset_root / "manifest_private.json")
                )
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
            },
            "baseline": baseline_metrics,
            "latest": latest_metrics,
            "delta": metric_delta(
                baseline_metrics["overall"],
                latest_metrics["overall"],
            ),
            "byFamilyDelta": by_family_delta,
            "decision": {
                "status": "REPLAY_AUDIT_ONLY",
                "production": "NOT_PRODUCTION_READY",
                "reason": (
                    "Ground Truth existed before replay; use a new held-out "
                    "corpus for promotion."
                ),
            },
        },
    )


def main() -> int:
    args = parse_args()
    if args.stage == "prepare":
        prepare(args)
    elif args.stage == "paddle":
        run_paddle(runner_args(args))
    elif args.stage == "vietocr":
        run_vietocr(runner_args(args))
    elif args.stage == "build":
        build(args)
    else:
        evaluate(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
