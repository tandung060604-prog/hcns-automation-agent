from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.validate_external_dataset_splits import SplitValidationError, validate_splits


def _inventory(root: Path, label: str) -> Path:
    cases = []
    for index, family in enumerate(("contract", "cv", "ielts"), start=1):
        relative = f"{family}/{label}_{family}.txt"
        source = root / Path(*relative.split("/"))
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"{label}-{family}", encoding="utf-8")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        cases.append(
            {
                "caseId": f"{family}-{label}",
                "category": family,
                "sourceRelativePath": relative,
                "sourceSha256": f"sha256:{digest}",
                "sizeBytes": source.stat().st_size,
                "sourceFormat": "PLAIN_TEXT",
                "documentType": {
                    "contract": "EMPLOYMENT_CONTRACT",
                    "cv": "CV",
                    "ielts": "CERTIFICATE",
                }[family],
                "pageCount": 1,
                "lineageId": f"lineage-{label}-{index}",
            }
        )
    path = root / f"{label}-inventory.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0.0",
                "dataset": {
                    "datasetId": f"data22-{label}",
                    "version": "test",
                    "sourceCommit": "a" * 40,
                    "contentDigest": "sha256:" + "0" * 64,
                    "documentCount": len(cases),
                    "pageCount": len(cases),
                    "purpose": "test",
                    "rightsBasis": "TEST",
                    "dataOwner": "TEST",
                    "approvedBy": "TEST",
                    "approvalReference": "TEST",
                    "approvedAt": "2026-08-07",
                    "retentionUntil": "2099-01-01",
                    "authorizationStatus": "APPROVED",
                    "storageProtection": "UNVERIFIED",
                    "dataClassification": "CONFIDENTIAL",
                },
                "cases": cases,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _policy(root: Path, dev: Path, heldout: Path) -> Path:
    policy = root / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "roots": {"development": str(dev), "heldout": str(heldout)},
                "development": {"contract": 1, "cv": 1, "ielts": 1},
                "heldout": {"contract": 1, "cv": 1, "ielts": 1},
                "history": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return policy


def test_validate_splits_checks_counts_hashes_and_policy(tmp_path: Path) -> None:
    development_root = tmp_path / "development"
    heldout_root = tmp_path / "heldout"
    development = _inventory(development_root, "dev")
    heldout = _inventory(heldout_root, "heldout")
    policy = _policy(tmp_path, development_root, heldout_root)

    report = validate_splits(development, heldout, policy)

    assert report["decision"] == "PASS"
    assert report["development"]["documentCount"] == 3
    assert report["heldout"]["documentCount"] == 3
    assert report["totalByFamily"] == {"contract": 2, "cv": 2, "ielts": 2}


def test_validate_splits_rejects_sha_overlap(tmp_path: Path) -> None:
    development_root = tmp_path / "development"
    heldout_root = tmp_path / "heldout"
    development = _inventory(development_root, "dev")
    heldout = _inventory(heldout_root, "heldout")
    heldout_payload = json.loads(heldout.read_text(encoding="utf-8"))
    development_payload = json.loads(development.read_text(encoding="utf-8"))
    heldout_source = heldout_root / Path(
        *heldout_payload["cases"][0]["sourceRelativePath"].split("/")
    )
    development_source = development_root / Path(
        *development_payload["cases"][0]["sourceRelativePath"].split("/")
    )
    heldout_source.write_bytes(development_source.read_bytes())
    heldout_payload["cases"][0]["sourceSha256"] = development_payload["cases"][0][
        "sourceSha256"
    ]
    heldout.write_text(json.dumps(heldout_payload), encoding="utf-8")
    policy = _policy(tmp_path, development_root, heldout_root)

    with pytest.raises(SplitValidationError, match="SHA overlap"):
        validate_splits(development, heldout, policy)
