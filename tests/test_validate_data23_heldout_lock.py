from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.validate_data23_heldout_lock import HeldoutLockError, validate_heldout_lock


def _build_manifest(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "heldout"
    cases = []
    for family, count in (("contract", 10), ("cv", 10), ("ielts", 5)):
        for index in range(count):
            relative = f"{family}/{index:02d}.txt"
            source = root / Path(*relative.split("/"))
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(f"{family}-{index}", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            cases.append(
                {
                    "caseId": f"{family}-{index:03d}",
                    "category": family,
                    "sourceRelativePath": relative,
                    "sourceSha256": f"sha256:{digest}",
                    "sourceFormat": "IMAGE" if family == "ielts" else "PLAIN_TEXT",
                    "manualReviewRequired": True,
                }
            )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cases": cases}, indent=2), encoding="utf-8")
    return manifest, root


def _locks(tmp_path: Path, manifest: Path) -> tuple[Path, Path]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    manifest_sha = "sha256:" + hashlib.sha256(canonical).hexdigest()
    prediction_artifact = tmp_path / "prediction.json"
    ground_truth_artifact = tmp_path / "ground_truth.json"
    prediction_artifact.write_text("prediction", encoding="utf-8")
    ground_truth_artifact.write_text("ground-truth", encoding="utf-8")
    prediction = tmp_path / "PREDICTION_LOCK.json"
    prediction.write_text(
        json.dumps(
            {
                "manifestSha256": manifest_sha,
                "predictionsOpened": False,
                "immutable": True,
                "predictionSha256": "sha256:" + hashlib.sha256(
                    prediction_artifact.read_bytes()
                ).hexdigest(),
                "artifactPath": str(prediction_artifact),
            }
        ),
        encoding="utf-8",
    )
    ground_truth = tmp_path / "GROUND_TRUTH_LOCK.json"
    ground_truth.write_text(
        json.dumps(
            {
                "manifestSha256": manifest_sha,
                "predictionsOpened": False,
                "immutable": True,
                "groundTruthStatus": "SEALED",
                "reviewStatus": "CONFIRMED",
                "groundTruthSha256": "sha256:" + hashlib.sha256(
                    ground_truth_artifact.read_bytes()
                ).hexdigest(),
                "artifactPath": str(ground_truth_artifact),
            }
        ),
        encoding="utf-8",
    )
    return prediction, ground_truth


def test_validate_heldout_lock_passes_without_metrics(tmp_path: Path) -> None:
    manifest, _ = _build_manifest(tmp_path)
    prediction, ground_truth = _locks(tmp_path, manifest)

    report = validate_heldout_lock(manifest, prediction, ground_truth)

    assert report["decision"] == "PASS"
    assert report["manifest"]["caseCount"] == 25
    assert report["metricsComputed"] is False


def test_validate_heldout_lock_rejects_open_predictions(tmp_path: Path) -> None:
    manifest, _ = _build_manifest(tmp_path)
    prediction, ground_truth = _locks(tmp_path, manifest)
    payload = json.loads(prediction.read_text(encoding="utf-8"))
    payload["predictionsOpened"] = True
    prediction.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(HeldoutLockError, match="predictions were opened"):
        validate_heldout_lock(manifest, prediction, ground_truth)
