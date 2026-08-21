from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from apps.ocr_lab.api.external_dataset_review import (
    FIELD_SPECS,
    load_coverage_document,
    load_coverage_summary,
    save_coverage_decision,
)


def build_data31_fixture(root: Path) -> tuple[Path, Path]:
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir()
    inventory_cases: list[dict[str, object]] = []
    ground_truth_cases: list[dict[str, object]] = []
    for index, category in enumerate(FIELD_SPECS, start=1):
        case_id = f"{category}-{index:03d}"
        relative = f"{category}/{case_id}.txt"
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"source for {category}", encoding="utf-8")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        inventory_cases.append(
            {
                "caseId": case_id,
                "category": category,
                "documentType": category.upper(),
                "sourceFormat": "PLAIN_TEXT",
                "pageCount": 1,
                "sourceRelativePath": relative,
                "sourceSha256": f"sha256:{digest}",
            }
        )
        ground_truth_cases.append(
            {
                "caseId": case_id,
                "documentType": category.upper(),
                "fields": [
                    {
                        "name": name,
                        "value": "baseline"
                        if name == FIELD_SPECS[category][0]
                        else None,
                        "reviewStatus": "CONFIRMED",
                        "sensitive": False,
                    }
                    for name in FIELD_SPECS[category]
                ],
                "pageCount": 1,
                "sourceRelativePath": relative,
                "sourceSha256": f"sha256:{digest}",
            }
        )
    inventory = root / "inventory.json"
    ground_truth = root / "ground-truth.json"
    inventory.write_text(
        json.dumps({"cases": inventory_cases, "dataset": {"datasetId": "DATA-31"}}),
        encoding="utf-8",
    )
    ground_truth.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0.0",
                "dataset": {
                    "datasetId": "DATA-31",
                    "version": "test",
                    "groundTruthStatus": "SEALED",
                },
                "cases": ground_truth_cases,
            }
        ),
        encoding="utf-8",
    )
    return inventory, ground_truth


def test_data31_coverage_exposes_only_missing_slots_and_ielts_semantics(
    tmp_path: Path,
) -> None:
    root = Path(Path.cwd().anchor) / "tmp" / f"codex-data31-coverage-{tmp_path.name}"
    inventory, ground_truth = build_data31_fixture(root)

    summary = load_coverage_summary(
        root,
        inventory_path=inventory,
        ground_truth_path=ground_truth,
    )

    assert summary["datasetId"] == "DATA-31"
    assert summary["missingFieldCount"] == 26
    assert summary["decidedFieldCount"] == 0
    assert summary["groundTruthIsImmutable"] is True
    assert "value" not in json.dumps(summary)
    assert "overall_score" in summary["ieltsSemantics"]

    detail = load_coverage_document(
        root,
        "ielts-003",
        inventory_path=inventory,
        ground_truth_path=ground_truth,
    )
    assert detail["fields"]
    assert detail["ieltsSemantics"]["issue_date"]


def test_data31_coverage_saves_overlay_without_rewriting_sealed_ground_truth(
    tmp_path: Path,
) -> None:
    root = Path(Path.cwd().anchor) / "tmp" / f"codex-data31-coverage-{tmp_path.name}"
    inventory, ground_truth = build_data31_fixture(root)
    before = ground_truth.read_bytes()
    missing = [
        name
        for name in FIELD_SPECS["contract"]
        if name != FIELD_SPECS["contract"][0]
    ]
    payload = {
        "reviewer": "local_user",
        "fields": {
            name: {
                "value": None if name == missing[0] else f"GT {name}",
                "disposition": "OUT_OF_SCOPE" if name == missing[0] else "GROUND_TRUTH",
            }
            for name in missing
        },
    }

    result = save_coverage_decision(
        root,
        "contract-002",
        payload,
        inventory_path=inventory,
        ground_truth_path=ground_truth,
    )

    assert result["saved"] is True
    assert result["outOfScopeCount"] == 1
    assert ground_truth.read_bytes() == before
    decision = root / "coverage-decision.json"
    assert decision.is_file()
    assert json.loads(decision.read_text(encoding="utf-8"))["cases"]["contract-002"]["fields"]


def test_data31_coverage_decision_cannot_escape_private_root(tmp_path: Path) -> None:
    root = Path(Path.cwd().anchor) / "tmp" / f"codex-data31-coverage-{tmp_path.name}"
    inventory, ground_truth = build_data31_fixture(root)
    with pytest.raises(PermissionError, match="private root"):
        load_coverage_summary(
            root,
            inventory_path=inventory,
            ground_truth_path=ground_truth,
            decision_path=root.parent / "outside.json",
        )
