from __future__ import annotations

import hashlib
import json
from pathlib import Path

from apps.ocr_lab.api.external_dataset_prediction import FIELD_SPECS
from scripts.evaluate_external_dataset_heldout_once import evaluate_once
from tests.test_validate_data23_heldout_lock import _build_manifest, _locks


def test_evaluate_once_is_create_only_and_preserves_lock_policy(tmp_path: Path) -> None:
    manifest, _ = _build_manifest(tmp_path)
    prediction_lock, ground_truth_lock = _locks(tmp_path, manifest)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    documents = []
    ground_truth_cases = []
    for case in manifest_payload["cases"]:
        category = case["category"]
        fields = {
            name: {"value": None, "confidence": 1.0}
            for name in FIELD_SPECS[category]
        }
        documents.append(
            {
                "caseId": case["caseId"],
                "category": category,
                "predictedCategory": category,
                "fields": fields,
                "evaluationIncluded": True,
                "processing": {
                    "usesOcr": category == "ielts",
                    "recommendedAction": "MANUAL_REVIEW"
                    if category == "ielts"
                    else "USER_REVIEW",
                },
            }
        )
        ground_truth_cases.append(
            {
                "caseId": case["caseId"],
                "fields": [
                    {"name": name, "value": None, "sensitive": False}
                    for name in FIELD_SPECS[category]
                ],
            }
        )
    prediction_path = tmp_path / "prediction.json"
    ground_truth_path = tmp_path / "ground_truth.json"
    prediction_path.write_text(
        json.dumps(
            {
                "schemaVersion": "external-dataset-prediction/1.0.0",
                "datasetId": "data22-test",
                "documents": documents,
            }
        ),
        encoding="utf-8",
    )
    ground_truth_path.write_text(
        json.dumps(
            {
                "dataset": {"datasetId": "data22-test"},
                "review": {"status": "CONFIRMED"},
                "cases": ground_truth_cases,
            }
        ),
        encoding="utf-8",
    )
    prediction_lock_payload = json.loads(prediction_lock.read_text(encoding="utf-8"))
    prediction_lock_payload["predictionSha256"] = "sha256:" + hashlib.sha256(
        prediction_path.read_bytes()
    ).hexdigest()
    prediction_lock_payload["artifactPath"] = str(prediction_path)
    prediction_lock.write_text(json.dumps(prediction_lock_payload), encoding="utf-8")
    ground_truth_lock_payload = json.loads(ground_truth_lock.read_text(encoding="utf-8"))
    ground_truth_lock_payload["groundTruthSha256"] = "sha256:" + hashlib.sha256(
        ground_truth_path.read_bytes()
    ).hexdigest()
    ground_truth_lock_payload["artifactPath"] = str(ground_truth_path)
    ground_truth_lock.write_text(json.dumps(ground_truth_lock_payload), encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps({"approved": True, "approvalReference": "TEST-APPROVAL"}),
        encoding="utf-8",
    )
    output = tmp_path / "evaluate_once.json"
    marker = tmp_path / "EVALUATE_ONCE_LOCK.json"

    report, marker_payload = evaluate_once(
        manifest,
        prediction_lock,
        ground_truth_lock,
        prediction_path,
        ground_truth_path,
        approval,
        output,
        marker,
    )

    assert report["evaluationKind"] == "heldout-evaluate-once"
    assert report["decision"] == "HOLD"
    assert marker_payload["evaluateOnceArtifactTouched"] is True
    assert output.is_file() and marker.is_file()
