#!/usr/bin/env python3
"""Evaluate the sealed CCCD held-out prediction exactly once.

The output contains aggregate metrics only.  Ground Truth and predictions are
read from the private staging root and never copied into a Git-tracked report.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "ocr_lab" / "api"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from evaluate_cccd_phase11_6 import evaluate_variant, gate  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    root = args.data_root.resolve()
    report_path = root / "evaluation" / "evaluate_once_private.json"
    if report_path.exists():
        raise SystemExit("Evaluate-once has already run")
    confirmed_path = root / "ground_truth" / "ground_truth_confirmed_private.json"
    sealed_path = root / "predictions" / "sealed_predictions_private.json"
    if not confirmed_path.is_file() or not sealed_path.is_file():
        raise SystemExit("Ground Truth lock and sealed predictions are required")

    ground_truth = load_json(confirmed_path)
    sealed = load_json(sealed_path)
    if ground_truth.get("groundTruthStatus") != "CONFIRMED":
        raise SystemExit("Ground Truth is not confirmed")
    if sealed.get("predictionsHiddenDuringGroundTruthReview") is not True:
        raise SystemExit("Sealed prediction privacy assertion is missing")
    if sealed.get("groundTruthPresent") is not False:
        raise SystemExit("Prediction snapshot was not sealed before Ground Truth")

    prediction_by_id = {
        item.get("documentId"): item for item in sealed.get("documents", [])
    }
    source_document_count = int(
        ground_truth.get("sourceDocumentCount", ground_truth.get("documentCount", 0))
    )
    excluded_document_count = int(ground_truth.get("excludedDocumentCount", 0))
    documents: list[dict[str, Any]] = []
    for item in ground_truth.get("documents", []):
        if item.get("disposition") == "OUT_OF_SCOPE_BACK":
            continue
        document_id = item.get("documentId")
        prediction = prediction_by_id.get(document_id)
        if prediction is None:
            raise SystemExit(f"Missing sealed prediction for {document_id}")
        if item.get("status") != "REVIEWED":
            raise SystemExit(f"Ground Truth document is not reviewed: {document_id}")
        assertions = item.get("verificationAssertions", {})
        if not (
            assertions.get("comparedWithImage") is True
            and assertions.get("allTextChecked") is True
        ):
            raise SystemExit(f"Ground Truth assertions are incomplete: {document_id}")
        documents.append(
            {
                "groundTruth": {
                    name: field
                    for name, field in (item.get("fields") or {}).items()
                    if isinstance(field, dict) and field.get("notPresent") is not True
                },
                "phase11_5": prediction.get("phase11_5", {}).get("fields", {}),
                "phase11_6": prediction.get("phase11_6", {}).get("fields", {}),
                "durations": {"phase11_5": 0.0, "phase11_6": 0.0},
            }
        )

    if len(documents) != int(ground_truth.get("documentCount", 0)):
        raise SystemExit("Ground Truth document count is inconsistent")
    before = evaluate_variant(documents, "phase11_5")
    after = evaluate_variant(documents, "phase11_6")
    report = {
        "schemaVersion": "phase11.6-cccd-heldout-evaluation/1.0.0",
        "evaluationKind": "BLINDED_EVALUATE_ONCE",
        "evaluatedAt": utc_now(),
        "containsRawPII": False,
        "datasetRole": "HELD_OUT",
        "documentCount": len(documents),
        "sourceDocumentCount": source_document_count,
        "excludedDocumentCount": excluded_document_count,
        "groundTruthSha256": sha256(confirmed_path),
        "sealedPredictionSha256": sha256(sealed_path),
        "metrics": {"phase11_5": before, "phase11_6": after},
        "promotionGate": gate(before, after, documents),
        "decision": {
            "status": gate(before, after, documents).get("status"),
            "production": (
                "PROMOTE_PHASE_11_6"
                if gate(before, after, documents).get("status") == "READY_FOR_NEW_HELDOUT"
                else "KEEP_PHASE_11_5_PRIMARY"
            ),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["promotionGate"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
