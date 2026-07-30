#!/usr/bin/env python3
"""Validate the complete Phase 11.5 development lock before OCR/evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "ocr_lab" / "api"))

from phase11_5_cccd import FRONT_FIELD_ROIS, ROI_REFINEMENT  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument(
        "--paddlex-model-root",
        type=Path,
        default=Path.home() / ".paddlex" / "official_models",
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def main() -> int:
    args = parse_args()
    config_path = REPO_ROOT / "config" / "phase11_5_cccd_policy.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    expected_manifest = config["developmentManifest"]["sha256"]
    if file_sha256(args.manifest) != expected_manifest:
        raise RuntimeError("Phase 11.5 development manifest hash mismatch")
    paths = {
        "paddle_ppocrv5_detector": (
            args.paddlex_model_root / "PP-OCRv5_mobile_det" / "inference.pdiparams"
        ),
        "paddle_ppocrv5_recognizer": (
            args.paddlex_model_root / "latin_PP-OCRv5_mobile_rec" / "inference.pdiparams"
        ),
        "easyocr_detector": (args.runtime_root / "easyocr_models" / "craft_mlt_25k.pth"),
        "easyocr_vi": args.runtime_root / "easyocr_models" / "latin_g2.pth",
        "vietocr_vgg_seq2seq": (args.runtime_root / "vietocr_models" / "vgg_seq2seq.pth"),
        "vietocr_vgg_transformer": (args.runtime_root / "vietocr_models" / "vgg_transformer.pth"),
    }
    locks = {item["profile"]: item for item in config["modelLocks"]}
    for profile, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Locked model missing: {profile}")
        if path.stat().st_size != int(locks[profile]["bytes"]):
            raise RuntimeError(f"Locked model size mismatch: {profile}")
        if file_sha256(path) != locks[profile]["sha256"]:
            raise RuntimeError(f"Locked model hash mismatch: {profile}")
    crop_profile = {
        "rois": FRONT_FIELD_ROIS,
        "crops": config["cropProfiles"],
        "roiRefinement": ROI_REFINEMENT,
    }
    if object_sha256(crop_profile) != config["cropProfileSha256"]:
        raise RuntimeError("Phase 11.5 crop profile hash mismatch")
    if object_sha256(config["selection"]) != config["recognitionPolicySha256"]:
        raise RuntimeError("Phase 11.5 recognition policy hash mismatch")
    if (
        file_sha256(REPO_ROOT / "apps" / "ocr_lab" / "api" / "phase11_5_cccd.py")
        != config["implementationSha256"]
    ):
        raise RuntimeError("Phase 11.5 implementation hash mismatch")
    if (
        file_sha256(REPO_ROOT / "schemas" / "vietnam_identity_card_phase11_5.schema.json")
        != config["schemaSha256"]
    ):
        raise RuntimeError("Phase 11.5 schema hash mismatch")
    print(
        json.dumps(
            {
                "status": "LOCK_VERIFIED",
                "phaseVersion": config["phaseVersion"],
                "modelCount": len(paths),
                "documentCount": config["developmentManifest"]["documentCount"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
