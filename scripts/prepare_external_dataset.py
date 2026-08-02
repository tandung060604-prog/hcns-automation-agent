"""Create and verify a privacy-preserving inventory for the external dataset.

This script deliberately excludes README.md, generator scripts and Git metadata.
The generated inventory belongs in a private staging root, not in this repository.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from hcns_agent.adapters.external_dataset import count_source_format_and_pages
from hcns_agent.application.external_dataset import (
    ExternalDatasetError,
    inventory_dataset,
    provisional_governance,
    validate_inventory,
    write_inventory,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-id", default="vuhocpublic-data")
    parser.add_argument("--dataset-version", default="2026-07-31-dec17acb")
    parser.add_argument(
        "--source-commit",
        default="dec17acbe2b409e0aa5daeb4db820d3e95d05bdf",
    )
    parser.add_argument("--data-owner", default="UNCONFIRMED")
    parser.add_argument("--rights-basis", default="PENDING_OWNER_CONFIRMATION")
    parser.add_argument("--approved-by", default="UNCONFIRMED")
    parser.add_argument("--approval-reference", default="PENDING_OWNER_CONFIRMATION")
    parser.add_argument(
        "--authorization-status",
        choices=("DRAFT", "APPROVED", "REVOKED"),
        default="DRAFT",
    )
    parser.add_argument(
        "--storage-protection",
        choices=("UNVERIFIED", "ENCRYPTED_VOLUME", "EFS", "ENTERPRISE_MANAGED"),
        default="UNVERIFIED",
    )
    parser.add_argument(
        "--data-classification",
        choices=("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"),
        default="CONFIDENTIAL",
    )
    parser.add_argument("--retention-days", type=int, default=365)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.retention_days <= 0:
        raise SystemExit("--retention-days must be positive")
    today = date.today()
    governance = provisional_governance(today=today)
    governance.update(
        {
            "dataOwner": args.data_owner,
            "rightsBasis": args.rights_basis,
            "approvedBy": args.approved_by,
            "approvalReference": args.approval_reference,
            "authorizationStatus": args.authorization_status,
            "storageProtection": args.storage_protection,
            "dataClassification": args.data_classification,
            "retentionUntil": date.fromordinal(
                today.toordinal() + args.retention_days
            ).isoformat(),
        }
    )
    try:
        inventory = inventory_dataset(
            args.dataset_root,
            dataset_id=args.dataset_id,
            version=args.dataset_version,
            source_commit=args.source_commit,
            governance=governance,
            page_counter=count_source_format_and_pages,
        )
        validate_inventory(
            args.dataset_root,
            inventory,
            page_counter=count_source_format_and_pages,
        )
        write_inventory(args.output, inventory)
    except ExternalDatasetError as error:
        raise SystemExit(f"Inventory rejected: {error}") from error
    dataset = inventory["dataset"]
    assert isinstance(dataset, dict)
    print(
        "Inventory complete: "
        f"documents={dataset['documentCount']} pages={dataset['pageCount']} "
        f"authorization={dataset['authorizationStatus']} "
        f"digest={dataset['contentDigest']}"
    )
    print(f"Inventory written outside repository: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
