"""Synthetic unit tests for DATA-31 IELTS crop benchmark runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.benchmark_data31_ielts_crop import (
    PROFILE_CONFIGS,
    REPORT_SCHEMA_VERSION,
    calculate_ielts_aggregate_metrics,
    parse_args,
    validate_cli_args,
)


def test_profile_configs_match_spec() -> None:
    assert set(PROFILE_CONFIGS) == {"baseline", "hires", "hires-autocontrast"}

    baseline = PROFILE_CONFIGS["baseline"]
    assert baseline["canvasSize"] == 1280
    assert baseline["magRatio"] == 1.3
    assert baseline["preprocessProfile"] == "none"

    hires = PROFILE_CONFIGS["hires"]
    assert hires["canvasSize"] == 2560
    assert hires["magRatio"] == 1.3
    assert hires["preprocessProfile"] == "none"

    hires_auto = PROFILE_CONFIGS["hires-autocontrast"]
    assert hires_auto["canvasSize"] == 2560
    assert hires_auto["magRatio"] == 1.3
    assert hires_auto["preprocessProfile"] == "content-roi-autocontrast-v1"


def test_cli_auth_rejection(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "private_dataset"
    dataset_dir.mkdir()
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text("{}", encoding="utf-8")
    gt_file = tmp_path / "ground_truth.json"
    gt_file.write_text("{}", encoding="utf-8")
    output_file = tmp_path / "output.json"

    args = parse_args(
        [
            "--dataset-root",
            str(dataset_dir),
            "--inventory",
            str(inventory_file),
            "--ground-truth",
            str(gt_file),
            "--output",
            str(output_file),
            "--warm-runs",
            "30",
        ]
    )
    with pytest.raises(SystemExit, match="pass --authorization-confirmed"):
        validate_cli_args(args)


def test_cli_warm_runs_rejection(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "private_dataset"
    dataset_dir.mkdir()
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text("{}", encoding="utf-8")
    gt_file = tmp_path / "ground_truth.json"
    gt_file.write_text("{}", encoding="utf-8")
    output_file = tmp_path / "output.json"

    args = parse_args(
        [
            "--dataset-root",
            str(dataset_dir),
            "--inventory",
            str(inventory_file),
            "--ground-truth",
            str(gt_file),
            "--output",
            str(output_file),
            "--authorization-confirmed",
            "--warm-runs",
            "29",
        ]
    )
    with pytest.raises(SystemExit, match="--warm-runs must be at least 30"):
        validate_cli_args(args)


def test_cli_private_path_rejection(tmp_path: Path) -> None:
    fake_git_root = tmp_path / "repo"
    fake_git_root.mkdir()
    (fake_git_root / ".git").mkdir()

    dataset_dir = fake_git_root / "dataset"
    dataset_dir.mkdir()
    inventory_file = fake_git_root / "inventory.json"
    inventory_file.write_text("{}", encoding="utf-8")
    gt_file = fake_git_root / "ground_truth.json"
    gt_file.write_text("{}", encoding="utf-8")
    output_file = fake_git_root / "report.json"

    args = parse_args(
        [
            "--dataset-root",
            str(dataset_dir),
            "--inventory",
            str(inventory_file),
            "--ground-truth",
            str(gt_file),
            "--output",
            str(output_file),
            "--authorization-confirmed",
            "--warm-runs",
            "30",
        ]
    )
    with pytest.raises(SystemExit, match="must stay outside Git"):
        validate_cli_args(args)


def test_cli_existing_output_overwrite_rejection(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "private_dataset"
    dataset_dir.mkdir()
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text("{}", encoding="utf-8")
    gt_file = tmp_path / "ground_truth.json"
    gt_file.write_text("{}", encoding="utf-8")
    output_file = tmp_path / "output.json"
    output_file.write_text("{}", encoding="utf-8")

    args = parse_args(
        [
            "--dataset-root",
            str(dataset_dir),
            "--inventory",
            str(inventory_file),
            "--ground-truth",
            str(gt_file),
            "--output",
            str(output_file),
            "--authorization-confirmed",
            "--warm-runs",
            "30",
        ]
    )
    with pytest.raises(SystemExit, match="pass --overwrite"):
        validate_cli_args(args)


def test_aggregate_metric_calculation_synthetic() -> None:
    synthetic_gt: dict[str, Any] = {
        "cases": [
            {
                "caseId": "ielts-001",
                "fields": [
                    {"name": "recipient_name", "value": "NGUYEN VAN A"},
                    {"name": "credential_id", "value": "21VN001234N001A"},
                    {"name": "credential_type", "value": "IELTS Academic"},
                    {"name": "overall_score", "value": "7.5"},
                    {"name": "issue_date", "value": "15/08/2023"},
                ],
            },
            {
                "caseId": "ielts-002",
                "fields": [
                    {"name": "recipient_name", "value": "TRAN THI B"},
                    {"name": "credential_id", "value": "22VN005678T002B"},
                    {"name": "credential_type", "value": "IELTS Academic"},
                    {"name": "overall_score", "value": "6.5"},
                    {"name": "issue_date", "value": "20/10/2023"},
                ],
            },
        ]
    }

    synthetic_predictions: list[dict[str, Any]] = [
        {
            "caseId": "ielts-001",
            "category": "ielts",
            "fields": {
                "recipient_name": {"value": "NGUYEN VAN A"},
                "credential_id": {"value": "21VN001234N001A"},
                "credential_type": {"value": "IELTS Academic"},
                "overall_score": {"value": "7.5"},
                "issue_date": {"value": "15/08/2023"},
            },
        },
        {
            "caseId": "ielts-002",
            "category": "ielts",
            "fields": {
                "recipient_name": {"value": "TRAN THI B"},
                "credential_id": {"value": "22VN005678T002B"},
                "credential_type": {"value": "IELTS Academic"},
                "overall_score": {"value": "6.0"},  # Mismatch
                "issue_date": {"value": None},  # Missing
            },
        },
    ]

    metrics = calculate_ielts_aggregate_metrics(synthetic_predictions, synthetic_gt)

    assert metrics["evaluatedFieldCount"] == 10
    assert metrics["fieldExactMatchCount"] == 8
    assert metrics["fieldExactMatchRate"] == 0.8
    assert metrics["fieldAcceptedMatchCount"] == 8
    assert metrics["fieldAcceptedMatchRate"] == 0.8
    assert metrics["fieldPresenceCount"] == 9
    assert metrics["fieldPresenceRate"] == 0.9

    by_field = metrics["byField"]
    assert set(by_field) == {
        "recipient_name",
        "credential_id",
        "credential_type",
        "overall_score",
        "issue_date",
    }
    assert by_field["recipient_name"]["exactMatchCount"] == 2
    assert by_field["overall_score"]["exactMatchCount"] == 1
    assert by_field["overall_score"]["presenceCount"] == 2
    assert by_field["issue_date"]["exactMatchCount"] == 1
    assert by_field["issue_date"]["presenceCount"] == 1

    # Privacy verification: no raw values, filenames, or case IDs
    metrics_str = str(metrics)
    assert "NGUYEN VAN A" not in metrics_str
    assert "21VN001234N001A" not in metrics_str
    assert "ielts-001" not in metrics_str
    assert "ielts-002" not in metrics_str


def test_aggregate_metrics_with_field_scope() -> None:
    synthetic_gt: dict[str, Any] = {
        "cases": [
            {
                "caseId": "ielts-001",
                "fields": [
                    {"name": "recipient_name", "value": "NGUYEN VAN A"},
                    {"name": "credential_id", "value": "21VN001234N001A"},
                    {"name": "credential_type", "value": "IELTS Academic"},
                    {"name": "overall_score", "value": "7.5"},
                    {"name": "issue_date", "value": "15/08/2023"},
                ],
            }
        ]
    }

    synthetic_predictions: list[dict[str, Any]] = [
        {
            "caseId": "ielts-001",
            "category": "ielts",
            "fields": {
                "recipient_name": {"value": "NGUYEN VAN A"},
                "credential_id": {"value": "21VN001234N001A"},
                "credential_type": {"value": "IELTS Academic"},
                "overall_score": {"value": "7.5"},
                "issue_date": {"value": "15/08/2023"},
            },
        }
    ]

    # Restrict scope to only 3 fields
    field_scope = {"ielts-001": ("recipient_name", "credential_id", "overall_score")}

    metrics = calculate_ielts_aggregate_metrics(
        synthetic_predictions,
        synthetic_gt,
        field_scope=field_scope,
    )

    assert metrics["evaluatedFieldCount"] == 3
    assert metrics["fieldExactMatchCount"] == 3
    assert metrics["fieldAcceptedMatchCount"] == 3
    assert metrics["fieldPresenceCount"] == 3


def test_report_schema_and_privacy_structure() -> None:
    assert REPORT_SCHEMA_VERSION == "data31-ielts-crop-benchmark/1.0.0"
