#!/usr/bin/env python3
"""Prepare, run, and seal a private Phase 11.6 CCCD held-out pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "ocr_lab" / "api"
sys.path.insert(0, str(API_ROOT))

FIELD_ORDER = (
    "identityNumber",
    "fullName",
    "dateOfBirth",
    "sex",
    "nationality",
    "placeOfOrigin",
    "placeOfResidence",
    "dateOfExpiry",
)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
NAMESPACE = uuid.UUID("72d56f4c-f2ac-4e5f-a1e4-3b94eb2ea87f")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path.name}")
    return value


def write_new_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite locked artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_authorization(root: Path) -> dict[str, Any]:
    authorization = load_json(root / "authorization.json")
    required = (
        "authorizedLocalDocumentsOnly",
        "processingRightsConfirmed",
        "documentOwnerConsentOrLawfulBasisConfirmed",
    )
    if any(authorization.get(key) is not True for key in required):
        raise PermissionError("Held-out authorization is incomplete")
    if not str(authorization.get("rightsBasis", "")).strip():
        raise PermissionError("Held-out authorization has no rights basis")
    return authorization


def development_hashes(manifests: list[Path]) -> set[str]:
    hashes: set[str] = set()
    for path in manifests:
        manifest = load_json(path)
        records = manifest.get("records")
        if not isinstance(records, list) or not records:
            raise ValueError(f"Development manifest has no records: {path}")
        hashes.update(str(record["sourceSha256"]) for record in records)
    return hashes


def select_novel_sources(
    source_dir: Path,
    excluded_hashes: set[str],
) -> list[tuple[Path, str]]:
    selected: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for path in sorted(source_dir.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.casefold() not in IMAGE_SUFFIXES:
            continue
        digest = sha256_file(path)
        if digest in excluded_hashes or digest in seen:
            continue
        with Image.open(path) as image:
            image.verify()
        seen.add(digest)
        selected.append((path, digest))
    return sorted(selected, key=lambda item: item[1])


def verify_manifest_lock(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest_private.json"
    lock_path = root / "locks" / "manifest_private.sha256"
    if not manifest_path.is_file() or not lock_path.is_file():
        raise FileNotFoundError("Held-out manifest lock is missing")
    expected = lock_path.read_text(encoding="ascii").split()[0]
    actual = sha256_file(manifest_path)
    if actual != expected:
        raise ValueError("Held-out manifest SHA-256 mismatch")
    manifest = load_json(manifest_path)
    records = manifest.get("records")
    if not isinstance(records, list) or len(records) != int(
        manifest.get("documentCount", -1)
    ):
        raise ValueError("Held-out manifest document count mismatch")
    for record in records:
        source = root / str(record["sourcePath"])
        if not source.is_file() or sha256_file(source) != record["sourceSha256"]:
            raise ValueError("Held-out source no longer matches manifest")
    return manifest


def persist_phase11_5_snapshots(
    root: Path,
    manifest: dict[str, Any],
) -> None:
    """Freeze fresh Phase 11.5 output before protected Phase 11.6 replay."""
    sessions = root / "user_uploads" / "sessions"
    for record in manifest["records"]:
        session = sessions / str(record["sessionId"])
        result = load_json(session / "result.json")
        if result.get("phase11_5", {}).get("status") != "COMPLETE":
            raise ValueError("Held-out Phase 11.5 prediction is incomplete")
        identity_card = result.get("phase11", {}).get("identityCard")
        if not isinstance(identity_card, dict):
            raise ValueError("Held-out Phase 11.5 identity card is missing")
        target = session / "phase11_5" / "identity_card.json"
        if target.exists():
            if load_json(target) != identity_card:
                raise ValueError("Held-out Phase 11.5 snapshot mismatch")
            continue
        write_new_json(target, identity_card)


def prepare(args: argparse.Namespace) -> int:
    root = args.dataset_root.resolve()
    authorization = validate_authorization(root)
    if (root / "manifest_private.json").exists():
        raise FileExistsError("Held-out manifest already exists")
    excluded = development_hashes(args.development_manifest)
    sources = select_novel_sources(args.source_dir.resolve(), excluded)
    if not sources:
        raise ValueError("No unseen CCCD image remains after SHA-256 exclusion")

    policy_path = args.phase11_6_policy.resolve()
    policy_digest = sha256_file(policy_path)
    authorization_digest = sha256_file(root / "authorization.json")
    records: list[dict[str, Any]] = []
    copied_paths: list[Path] = []
    try:
        for index, (source, digest) in enumerate(sources, start=1):
            extension = source.suffix.casefold()
            document_id = f"CCCD-HO-{index:03d}"
            destination = root / "source" / f"{document_id}{extension}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise FileExistsError(f"Held-out source already exists: {destination}")
            shutil.copy2(source, destination)
            copied_paths.append(destination)
            if sha256_file(destination) != digest:
                raise OSError("Copied held-out source hash mismatch")
            records.append(
                {
                    "documentId": document_id,
                    "documentIndex": index,
                    "sessionId": str(uuid.uuid5(NAMESPACE, digest)),
                    "sourcePath": destination.relative_to(root).as_posix(),
                    "sourceSha256": digest,
                    "sizeBytes": destination.stat().st_size,
                    "sourceFormat": extension.lstrip(".").upper(),
                }
            )
    except Exception:
        for path in copied_paths:
            path.unlink(missing_ok=True)
        raise

    core = {
        "datasetId": args.dataset_id,
        "authorizationSha256": authorization_digest,
        "policyConfigSha256": policy_digest,
        "developmentManifestSha256": [
            sha256_file(path) for path in args.development_manifest
        ],
        "records": records,
    }
    manifest = {
        "schemaVersion": "phase11.6-cccd-heldout-manifest/1.0.0",
        "createdAt": utc_now(),
        "containsRealPII": True,
        "predictionsVisibleDuringGroundTruthReview": False,
        "groundTruthStatus": "PENDING_HUMAN_CONFIRMATION",
        "promotionEligible": False,
        "minimumPromotionDocumentCount": 15,
        "documentCount": len(records),
        "datasetDigest": f"sha256:{object_sha256(core)}",
        **core,
    }
    queue = {
        "schemaVersion": "phase11.6-cccd-heldout-review/1.0.0",
        "createdAt": utc_now(),
        "containsRealPII": True,
        "predictionsVisibleDuringGroundTruthReview": False,
        "groundTruthStatus": "PENDING_HUMAN_CONFIRMATION",
        "datasetId": manifest["datasetId"],
        "datasetDigest": manifest["datasetDigest"],
        "documentCount": len(records),
        "documents": [
            {
                "documentId": record["documentId"],
                "sourcePath": record["sourcePath"],
                "sourceSha256": record["sourceSha256"],
                "status": "PENDING",
                "fields": {
                    name: {"value": "", "notPresent": False} for name in FIELD_ORDER
                },
                "verificationAssertions": {
                    "comparedWithImage": False,
                    "allTextChecked": False,
                },
            }
            for record in records
        ],
    }
    write_new_json(root / "manifest_private.json", manifest)
    manifest_digest = sha256_file(root / "manifest_private.json")
    (root / "locks").mkdir(parents=True, exist_ok=True)
    (root / "locks" / "manifest_private.sha256").write_text(
        f"{manifest_digest}  manifest_private.json\n",
        encoding="ascii",
    )
    write_new_json(root / "ground_truth" / "review_queue_private.json", queue)
    print(
        json.dumps(
            {
                "status": "MANIFEST_LOCKED",
                "documentCount": len(records),
                "minimumPromotionDocumentCount": 15,
                "sampleGate": (
                    "SUFFICIENT"
                    if len(records) >= 15
                    else "INSUFFICIENT_DOCUMENTS"
                ),
                "authorizationDatasetId": authorization.get("datasetId"),
            }
        )
    )
    return 0


def ingest(args: argparse.Namespace) -> int:
    from serve_dashboard_api import UserOCRService

    root = args.dataset_root.resolve()
    validate_authorization(root)
    manifest = verify_manifest_lock(root)
    service = UserOCRService(root)
    completed = 0
    for record in manifest["records"]:
        session = root / "user_uploads" / "sessions" / str(record["sessionId"])
        result_path = session / "result.json"
        if result_path.is_file():
            inputs = list((session / "input").glob("*"))
            if len(inputs) != 1 or sha256_file(inputs[0]) != record["sourceSha256"]:
                raise ValueError("Existing held-out session does not match manifest")
        else:
            if session.exists():
                raise FileExistsError("Incomplete held-out session already exists")
            source = root / str(record["sourcePath"])
            service.process_upload(
                str(record["sessionId"]),
                f"{record['documentId']}.{str(record['sourceFormat']).casefold()}",
                source.suffix.casefold(),
                source.read_bytes(),
            )
        completed += 1
        print(
            json.dumps(
                {
                    "stage": "ingest",
                    "progress": completed,
                    "total": manifest["documentCount"],
                    "contentHidden": True,
                }
            ),
            flush=True,
        )
    write_new_json(
        root / "predictions" / "INGEST_STATUS.json",
        {
            "schemaVersion": "phase11.6-cccd-heldout-ingest-status/1.0.0",
            "createdAt": utc_now(),
            "containsRawPII": False,
            "status": "INGEST_COMPLETE",
            "documentCount": completed,
            "predictionsVisibleDuringGroundTruthReview": False,
        },
    )
    return 0


def predict(args: argparse.Namespace) -> int:
    root = args.dataset_root.resolve()
    manifest = verify_manifest_lock(root)
    validate_authorization(root)
    if not (root / "predictions" / "INGEST_STATUS.json").is_file():
        raise FileNotFoundError("Run held-out ingest before prediction")
    if (root / "predictions" / "sealed_predictions_private.json").exists():
        raise FileExistsError("Held-out predictions are already sealed")
    baseline_runtime_policy = root / "locks" / "phase11_5_heldout_policy.json"
    if not baseline_runtime_policy.exists():
        baseline_policy = load_json(args.phase11_5_policy.resolve())
        phase11_6_policy = load_json(args.phase11_6_policy.resolve())
        baseline_policy["status"] = "SHADOW_REVIEW_ONLY"
        baseline_policy["heldoutRuntimeOverride"] = {
            "source": "phase11_6_locked_runtime",
            "reason": "avoid_unbounded_beamsearch_on_large_private_crops",
        }
        baseline_policy["recognitionRuntime"] = phase11_6_policy[
            "recognitionRuntime"
        ]
        write_new_json(baseline_runtime_policy, baseline_policy)
    common = [
        "--data-root",
        str(root),
        "--manifest",
        str(root / "manifest_private.json"),
        "--secondary-python",
        str(args.secondary_python.resolve()),
        "--runtime-root",
        str(args.runtime_root.resolve()),
    ]
    subprocess.run(
        [
            str(args.primary_python.resolve()),
            str(REPO_ROOT / "scripts" / "run_cccd_phase11_5.py"),
            *common,
            "--policy",
            str(baseline_runtime_policy),
            "--phase-module",
            "phase11_5_cccd",
            "--phase-key",
            "phase11_5",
            "--phase-version",
            "11.5.0",
            "--phase-root",
            "phase11_5",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    persist_phase11_5_snapshots(root, manifest)
    subprocess.run(
        [
            str(args.primary_python.resolve()),
            str(REPO_ROOT / "scripts" / "run_cccd_phase11_5.py"),
            *common,
            "--policy",
            str(args.phase11_6_policy.resolve()),
            "--phase-module",
            "phase11_6_cccd",
            "--phase-key",
            "phase11_6",
            "--phase-version",
            "11.6.0",
            "--phase-root",
            "phase11_6",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    seal_predictions(root, manifest, args.phase11_6_policy.resolve())
    return 0


def seal_predictions(
    root: Path,
    manifest: dict[str, Any],
    policy_path: Path,
) -> None:
    documents: list[dict[str, Any]] = []
    sessions = root / "user_uploads" / "sessions"
    for record in manifest["records"]:
        session = sessions / str(record["sessionId"])
        result = load_json(session / "result.json")
        if result.get("phase11_5", {}).get("status") != "COMPLETE":
            raise ValueError("Held-out Phase 11.5 prediction is incomplete")
        if result.get("phase11_6", {}).get("status") != "COMPLETE":
            raise ValueError("Held-out Phase 11.6 prediction is incomplete")
        baseline = load_json(session / "phase11_5" / "identity_card.json")
        candidate = result.get("phase11", {}).get("identityCard")
        if not isinstance(candidate, dict):
            raise ValueError("Held-out Phase 11.6 identity card is missing")
        documents.append(
            {
                "documentId": record["documentId"],
                "sourceSha256": record["sourceSha256"],
                "phase11_5": baseline,
                "phase11_6": candidate,
            }
        )
    snapshot = {
        "schemaVersion": "phase11.6-cccd-heldout-predictions/1.0.0",
        "sealedAt": utc_now(),
        "containsRealPII": True,
        "predictionsHiddenDuringGroundTruthReview": True,
        "groundTruthPresent": False,
        "policyMode": "SHADOW_REVIEW_ONLY",
        "datasetId": manifest["datasetId"],
        "datasetDigest": manifest["datasetDigest"],
        "manifestSha256": sha256_file(root / "manifest_private.json"),
        "policyConfigSha256": sha256_file(policy_path),
        "baselineRuntimePolicySha256": sha256_file(
            root / "locks" / "phase11_5_heldout_policy.json"
        ),
        "documentCount": len(documents),
        "documents": documents,
    }
    private_path = root / "predictions" / "sealed_predictions_private.json"
    write_new_json(private_path, snapshot)
    private_digest = sha256_file(private_path)
    (root / "locks" / "sealed_predictions_private.sha256").write_text(
        f"{private_digest}  predictions/sealed_predictions_private.json\n",
        encoding="ascii",
    )
    write_new_json(
        root / "predictions" / "HIDDEN_PREDICTIONS_STATUS.json",
        {
            "schemaVersion": "phase11.6-cccd-heldout-status/1.0.0",
            "createdAt": utc_now(),
            "containsRawPII": False,
            "status": "BLINDED_PREDICTIONS_READY",
            "predictionsHiddenDuringGroundTruthReview": True,
            "groundTruthPresent": False,
            "policyMode": "SHADOW_REVIEW_ONLY",
            "documentCount": len(documents),
            "minimumPromotionDocumentCount": 15,
            "sampleGate": (
                "SUFFICIENT"
                if len(documents) >= 15
                else "INSUFFICIENT_DOCUMENTS"
            ),
            "manifestSha256": snapshot["manifestSha256"],
            "policyConfigSha256": snapshot["policyConfigSha256"],
            "privateArtifactSha256": private_digest,
            "unlockRule": (
                "Lock and confirm Ground Truth before opening predictions; "
                "evaluate exactly once without threshold changes."
            ),
        },
    )
    print(
        json.dumps(
            {
                "status": "BLINDED_PREDICTIONS_READY",
                "documentCount": len(documents),
                "sampleGate": (
                    "SUFFICIENT"
                    if len(documents) >= 15
                    else "INSUFFICIENT_DOCUMENTS"
                ),
                "contentHidden": True,
            }
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--source-dir", type=Path, required=True)
    prepare_parser.add_argument(
        "--development-manifest",
        type=Path,
        action="append",
        required=True,
    )
    prepare_parser.add_argument(
        "--phase11-6-policy",
        type=Path,
        default=REPO_ROOT / "config" / "phase11_6_cccd_policy.json",
    )
    prepare_parser.add_argument(
        "--dataset-id",
        default="phase11.6-real-cccd-heldout-v1",
    )
    subparsers.add_parser("ingest")
    predict_parser = subparsers.add_parser("predict")
    predict_parser.add_argument("--primary-python", type=Path, required=True)
    predict_parser.add_argument("--secondary-python", type=Path, required=True)
    predict_parser.add_argument("--runtime-root", type=Path, required=True)
    predict_parser.add_argument(
        "--phase11-5-policy",
        type=Path,
        default=REPO_ROOT / "config" / "phase11_5_cccd_policy.json",
    )
    predict_parser.add_argument(
        "--phase11-6-policy",
        type=Path,
        default=REPO_ROOT / "config" / "phase11_6_cccd_policy.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        return prepare(args)
    if args.command == "ingest":
        return ingest(args)
    return predict(args)


if __name__ == "__main__":
    raise SystemExit(main())
