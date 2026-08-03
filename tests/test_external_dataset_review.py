from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from external_dataset_review import (  # noqa: E402
    FIELD_SPECS,
    load_review_document,
    load_review_summary,
    lock_ground_truth,
    save_review,
)


def build_dataset(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = Path("C:/tmp") / f"codex-external-test-{tmp_path.name}"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir()
    cases: list[dict[str, object]] = []
    draft_cases: list[dict[str, object]] = []
    for index, category in enumerate(FIELD_SPECS, start=1):
        suffix = ".txt"
        relative = f"{category}/{category}-{index:03d}{suffix}"
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"synthetic {category}", encoding="utf-8")
        digest = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
        case_id = f"{category}-{index:03d}"
        record = {
            "caseId": case_id,
            "category": category,
            "documentType": category.upper(),
            "pageCount": 1,
            "sourceFormat": "DOCX" if category == "cv" else "PLAIN_TEXT",
            "sourceRelativePath": relative,
            "sourceSha256": f"sha256:{digest}",
        }
        cases.append(record)
        draft_cases.append(
            {
                "caseId": case_id,
                "documentType": category.upper(),
                "fields": [
                    {
                        "name": name,
                        "reviewStatus": "PENDING",
                        "sensitive": False,
                        "value": None,
                    }
                    for name in FIELD_SPECS[category]
                ],
                "pageCount": 1,
                "sourceRelativePath": relative,
                "sourceSha256": f"sha256:{digest}",
            }
        )
    inventory = root.parent / f"{root.name}-public-inventory.json"
    ground_truth = root.parent / f"{root.name}-ground-truth-draft.json"
    inventory.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    ground_truth.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0.0",
                "cases": draft_cases,
                "dataset": {
                    "datasetId": "synthetic-external",
                    "version": "test",
                    "contentDigest": "sha256:test",
                    "groundTruthStatus": "DRAFT",
                },
                "review": {
                    "status": "PENDING",
                    "predictionBlindness": True,
                    "reviewer": "UNASSIGNED",
                },
            }
        ),
        encoding="utf-8",
    )
    return root, inventory, ground_truth


def all_fields(category: str, value: str | None = "confirmed") -> dict[str, dict[str, str | None]]:
    return {name: {"value": value} for name in FIELD_SPECS[category]}


def test_summary_is_prediction_blind_and_counts_current_fields(tmp_path: Path) -> None:
    root, inventory, ground_truth = build_dataset(tmp_path)
    summary = load_review_summary(
        root,
        inventory_path=inventory,
        ground_truth_path=ground_truth,
    )
    assert summary["documentCount"] == 3
    assert summary["fieldCount"] == 29
    assert summary["reviewableDocumentCount"] == 3
    assert summary["predictionsHiddenDuringReview"] is True
    assert summary["localOnly"] is True
    assert "value" not in json.dumps(summary)
    detail = load_review_document(
        root,
        "cv-001",
        inventory_path=inventory,
        ground_truth_path=ground_truth,
    )
    assert detail["predictionsHidden"] is True
    assert "prediction" not in detail


def test_cv_text_and_pptx_are_out_of_scope_and_cannot_be_saved(tmp_path: Path) -> None:
    root, inventory, ground_truth = build_dataset(tmp_path)
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    cv_record = next(item for item in payload["cases"] if item["caseId"] == "cv-001")
    cv_record["sourceFormat"] = "PPTX"
    inventory.write_text(json.dumps(payload), encoding="utf-8")

    summary = load_review_summary(
        root,
        inventory_path=inventory,
        ground_truth_path=ground_truth,
    )
    excluded = next(item for item in summary["documents"] if item["caseId"] == "cv-001")
    assert excluded["reviewable"] is False
    assert excluded["reviewStatus"] == "OUT_OF_SCOPE"
    detail = load_review_document(
        root,
        "cv-001",
        inventory_path=inventory,
        ground_truth_path=ground_truth,
    )
    assert detail["reviewStatus"] == "OUT_OF_SCOPE"
    with pytest.raises(ValueError, match="outside the active review scope"):
        save_review(
            root,
            "cv-001",
            {"fields": all_fields("cv")},
            inventory_path=inventory,
            ground_truth_path=ground_truth,
        )


def test_source_path_escape_is_rejected(tmp_path: Path) -> None:
    root, inventory, ground_truth = build_dataset(tmp_path)
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    payload["cases"][0]["sourceRelativePath"] = "../outside.txt"
    inventory.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe"):
        load_review_summary(root, inventory_path=inventory, ground_truth_path=ground_truth)


def test_save_and_seal_require_every_field(tmp_path: Path) -> None:
    root, inventory, ground_truth = build_dataset(tmp_path)
    with pytest.raises(ValueError, match="All and only"):
        save_review(
            root,
            "cv-001",
            {"fields": {"full_name": {"value": "x"}}},
            inventory_path=inventory,
            ground_truth_path=ground_truth,
        )
    for category, index in (("cv", 1), ("contract", 2), ("ielts", 3)):
        save_review(
            root,
            f"{category}-{index:03d}",
            {"fields": all_fields(category)},
            inventory_path=inventory,
            ground_truth_path=ground_truth,
        )
    result = lock_ground_truth(
        root,
        confirm=True,
        inventory_path=inventory,
        ground_truth_path=ground_truth,
    )
    assert result["groundTruthStatus"] == "SEALED"
    assert result["predictionsOpened"] is False
