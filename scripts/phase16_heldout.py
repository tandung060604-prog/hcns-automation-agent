#!/usr/bin/env python3
"""Manage the private Phase 16 real five-family held-out benchmark."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from hcns_agent.application.phase16_heldout import (
    FAMILY_SPECS,
    audit_sources,
    authorization_template,
    collect_known_hashes,
    confirmed_ground_truth,
    evaluate_once,
    prepare_manifest,
    seal_predictions,
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError("Expected a JSON object")
    return value


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite locked artifact: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def bootstrap(root: Path) -> None:
    for spec in FAMILY_SPECS.values():
        (root / "source" / str(spec["directory"])).mkdir(
            parents=True,
            exist_ok=True,
        )
    (root / "ground_truth").mkdir(parents=True, exist_ok=True)
    (root / "predictions").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    authorization_path = root / "authorization.json"
    if not authorization_path.exists():
        write_new_json(authorization_path, authorization_template())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument(
        "--exclude-root",
        action="append",
        type=Path,
        default=[],
        help="Previously seen corpus root; may be repeated",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("bootstrap")
    subparsers.add_parser("status")
    subparsers.add_parser("prepare")
    subparsers.add_parser("confirm-ground-truth")
    seal = subparsers.add_parser("seal-predictions")
    seal.add_argument("--input", type=Path, required=True)
    evaluate = subparsers.add_parser("evaluate-once")
    evaluate.add_argument("--sealed-predictions", type=Path, required=True)
    evaluate.add_argument("--ground-truth", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.dataset_root.resolve()
    if args.command == "bootstrap":
        bootstrap(root)
        print(f"Held-out intake ready: {root}")
        return 0

    known_hashes = collect_known_hashes(args.exclude_root)
    audit = audit_sources(root, known_hashes=known_hashes)
    if args.command == "status":
        print(
            json.dumps(
                {
                    key: value
                    for key, value in audit.items()
                    if key != "documents"
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    manifest_path = root / "manifest_private.json"
    queue_path = root / "ground_truth" / "review_queue_private.json"
    if args.command == "prepare":
        authorization = read_json(root / "authorization.json")
        manifest, queue = prepare_manifest(root, authorization, audit)
        write_new_json(manifest_path, manifest)
        write_new_json(queue_path, queue)
        print(f"Held-out manifest locked: {manifest['documentCount']} documents")
        return 0

    if args.command == "confirm-ground-truth":
        ground_truth = confirmed_ground_truth(read_json(queue_path))
        write_new_json(
            root / "ground_truth" / "ground_truth_confirmed_private.json",
            ground_truth,
        )
        print("Held-out Ground Truth confirmed; predictions remain hidden")
        return 0

    if args.command == "seal-predictions":
        sealed = seal_predictions(read_json(args.input), read_json(manifest_path))
        write_new_json(
            root / "predictions" / "sealed_predictions_private.json",
            sealed,
        )
        print("Held-out predictions sealed and hidden")
        return 0

    report_path = root / "reports" / "PHASE16_HELDOUT_RESULTS.json"
    report = evaluate_once(
        read_json(args.sealed_predictions),
        read_json(args.ground_truth),
    )
    write_new_json(report_path, report)
    print(
        f"Held-out evaluated once: documents={report['documentCount']}, "
        f"decision={report['decision']['controlledPilot']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
