#!/usr/bin/env python3
"""Run and seal Phase 16 held-out predictions without exposing model text."""

from __future__ import annotations

import argparse
import hashlib
import sys
from argparse import Namespace
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_API = _ROOT / "apps" / "ocr_lab" / "api"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from hcns_agent.application.phase16_heldout import (  # noqa: E402
    LOCKED_POLICY_DIGEST,
    PARSER_VERSION,
    seal_predictions,
    sha256_file,
)
from scripts.phase15_benchmark import (  # noqa: E402
    POLICY_CONFIG,
    atomic_json,
    load_json,
    render_pages,
    run_paddle,
    run_vietocr,
)
from scripts.phase16_heldout import write_new_json  # noqa: E402


def policy_prediction_document(
    source: Mapping[str, Any],
    classification: Mapping[str, Any],
    extraction: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep fields and tables in the same locked prediction contract."""
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
        choices=("prepare", "paddle", "vietocr", "seal", "all"),
        default="all",
        help=(
            "Run one resumable stage. Use the Paddle environment for "
            "'prepare'/'paddle' and the VietOCR environment for 'vietocr'."
        ),
    )
    return parser.parse_args()


def build_prepared_manifest(
    dataset_root: Path,
    work_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    documents = []
    for document in manifest["documents"]:
        source_path = dataset_root / str(document["sourcePath"])
        if sha256_file(source_path) != str(document["sourceSha256"]):
            raise ValueError("Held-out source no longer matches locked SHA-256")
        if source_path.suffix.casefold() in {".pdf", ".png", ".jpg", ".jpeg"}:
            page_paths = render_pages(
                source_path,
                work_root / "pages" / str(document["documentId"]),
            )
        else:
            page_paths = []
        documents.append(
            {
                **document,
                "pagePaths": [
                    path.relative_to(work_root).as_posix() for path in page_paths
                ],
                "pageSha256": [sha256_file(path) for path in page_paths],
            }
        )
    return {
        "schemaVersion": "phase16-hidden-prediction-input/1.0.0",
        "stage": "PREPARED",
        "containsRealPII": True,
        "datasetKind": "REAL_FIVE_FAMILY_HELDOUT",
        "datasetId": manifest["datasetId"],
        "datasetDigest": manifest["datasetDigest"],
        "documentCount": len(documents),
        "policyDigest": LOCKED_POLICY_DIGEST,
        "parserVersion": PARSER_VERSION,
        "documents": documents,
    }


def prediction_payload(
    dataset_root: Path,
    prepared: dict[str, Any],
    recognition: dict[str, Any],
) -> dict[str, Any]:
    from phase12_ingestion import ingest_document
    from phase15_idp import (
        IDP_PARSER_VERSION,
        classify_phase15_document,
        extract_phase15_document,
    )

    recognition_by_id = {
        str(document["documentId"]): document
        for document in recognition["documents"]
    }
    documents = []
    for document in prepared["documents"]:
        document_id = str(document["documentId"])
        source_path = dataset_root / str(document["sourcePath"])
        recognized = recognition_by_id.get(document_id)
        if recognized is None:
            raise ValueError("Locked recognition output is missing a document")
        canonical = ingest_document(source_path, recognized["pages"])
        classification = classify_phase15_document(canonical)
        extraction = extract_phase15_document(canonical, classification)
        if extraction.get("parserVersion") != IDP_PARSER_VERSION:
            raise ValueError("Extraction did not use the locked Phase 16 parser")
        documents.append(
            policy_prediction_document(
                document,
                classification,
                extraction,
            )
        )
    return {
        "schemaVersion": "phase16-heldout-policy-predictions/1.0.0",
        "containsRealPII": True,
        "datasetId": prepared["datasetId"],
        "datasetDigest": prepared["datasetDigest"],
        "recognitionPolicyDigest": LOCKED_POLICY_DIGEST,
        "parserVersion": PARSER_VERSION,
        "documents": documents,
    }


def load_locked_manifest(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    dataset_root = args.dataset_root.resolve()
    manifest = load_json(dataset_root / "manifest_private.json")
    if manifest.get("recognitionPolicyDigest") != LOCKED_POLICY_DIGEST:
        raise ValueError("Manifest does not use the locked Phase 14.8 policy")
    if manifest.get("parserVersion") != PARSER_VERSION:
        raise ValueError("Manifest does not use the locked Phase 16 parser")
    return dataset_root, manifest


def run_prepare_stage(
    args: argparse.Namespace,
    dataset_root: Path,
    manifest: dict[str, Any],
) -> int:
    work_root = dataset_root / "predictions" / "private_work"
    sealed_path = dataset_root / "predictions" / "sealed_predictions_private.json"
    if sealed_path.exists():
        raise FileExistsError("Held-out predictions are already sealed")
    prepared = build_prepared_manifest(dataset_root, work_root, manifest)
    prepared_path = work_root / "prepared_manifest_private.json"
    if prepared_path.exists():
        raise FileExistsError("Prepared hidden-prediction input already exists")
    atomic_json(prepared_path, prepared)
    print(
        f"Hidden Phase 16 input prepared: "
        f"documents={len(prepared['documents'])}"
    )
    return 0


def runner_args(
    args: argparse.Namespace,
    dataset_root: Path,
) -> Namespace:
    return Namespace(
        dataset_root=dataset_root,
        work_root=dataset_root / "predictions" / "private_work",
        policy_config=args.policy_config,
        private_runtime=args.private_runtime,
        paddle_model_root=args.paddle_model_root,
        overwrite=False,
    )


def run_seal_stage(
    args: argparse.Namespace,
    dataset_root: Path,
    manifest: dict[str, Any],
) -> int:
    work_root = dataset_root / "predictions" / "private_work"
    sealed_path = dataset_root / "predictions" / "sealed_predictions_private.json"
    if sealed_path.exists():
        raise FileExistsError("Held-out predictions are already sealed")
    prepared = load_json(work_root / "prepared_manifest_private.json")
    recognition = load_json(work_root / "phase15_recognition_private.json")
    predictions = prediction_payload(dataset_root, prepared, recognition)
    private_path = (
        dataset_root
        / "predictions"
        / "phase16_policy_predictions_private.json"
    )
    write_new_json(private_path, predictions)
    sealed = seal_predictions(predictions, manifest)
    write_new_json(sealed_path, sealed)
    digest = hashlib.sha256(sealed_path.read_bytes()).hexdigest()
    write_new_json(
        dataset_root / "predictions" / "HIDDEN_PREDICTIONS_STATUS.json",
        {
            "schemaVersion": "phase16-hidden-predictions-status/1.0.0",
            "containsRealPII": False,
            "status": "BLINDED_PREDICTIONS_READY",
            "predictionsHiddenDuringReview": True,
            "documentCount": len(sealed["documents"]),
            "datasetDigest": sealed["datasetDigest"],
            "recognitionPolicyDigest": LOCKED_POLICY_DIGEST,
            "parserVersion": PARSER_VERSION,
            "sealedPredictionsSha256": digest,
        },
    )
    print(
        f"Hidden Phase 16 predictions sealed: "
        f"documents={len(sealed['documents'])} (values hidden)"
    )
    return 0


def main() -> int:
    args = parse_args()
    dataset_root, manifest = load_locked_manifest(args)
    stages = (
        ("prepare", "paddle", "vietocr", "seal")
        if args.stage == "all"
        else (args.stage,)
    )
    for stage in stages:
        if stage == "prepare":
            run_prepare_stage(args, dataset_root, manifest)
        elif stage == "paddle":
            run_paddle(runner_args(args, dataset_root))
        elif stage == "vietocr":
            run_vietocr(runner_args(args, dataset_root))
        else:
            run_seal_stage(args, dataset_root, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
