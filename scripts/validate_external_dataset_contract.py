"""Validate external dataset inventory and contract mapping version pairing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hcns_agent.adapters.external_dataset import count_source_format_and_pages
from hcns_agent.application.external_dataset import (
    ExternalDatasetError,
    read_inventory,
    validate_inventory,
    validate_mapping,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = read_inventory(args.inventory)
    try:
        mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
        if not isinstance(mapping, dict):
            raise ExternalDatasetError("Mapping must be a JSON object")
        validate_inventory(
            args.dataset_root,
            inventory,
            page_counter=count_source_format_and_pages,
        )
        validate_mapping(inventory, mapping)
    except (OSError, json.JSONDecodeError, ExternalDatasetError) as error:
        raise SystemExit(f"External dataset contract rejected: {error}") from error
    print("External dataset inventory and mapping: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
