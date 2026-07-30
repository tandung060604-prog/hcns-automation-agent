from __future__ import annotations

import json
from pathlib import Path

from scripts.serve_phase16_ground_truth import HTML, ReviewStore


def write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_phase16_review_resumes_and_never_loads_predictions(
    tmp_path: Path,
) -> None:
    assert "Loại/Nội dung văn bản" in HTML
    assert "không tự động là ngày bắt đầu hay ngày hiệu lực" in HTML

    source = tmp_path / "source" / "01_cv" / "sample.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic-image-fixture")
    fields = {
        name: {"status": "PENDING_REVIEW", "value": ""}
        for name in ("fullName", "headline", "email", "phoneNumber", "address")
    }
    queue = {
        "schemaVersion": "phase16-heldout-ground-truth-queue/1.0.0",
        "datasetId": "fixture",
        "datasetDigest": "sha256:fixture",
        "containsRealPII": True,
        "predictionsVisibleDuringReview": False,
        "groundTruthStatus": "PENDING_REVIEW",
        "documents": [
            {
                "documentId": "H16-C-001",
                "documentFamily": "CV",
                "sourcePath": "source/01_cv/sample.jpg",
                "sourceSha256": "fixture",
                "status": "PENDING_REVIEW",
                "fields": fields,
            }
        ],
    }
    write_json(tmp_path / "ground_truth" / "review_queue_private.json", queue)
    write_json(
        tmp_path / "predictions" / "HIDDEN_PREDICTIONS_STATUS.json",
        {
            "status": "BLINDED_PREDICTIONS_READY",
            "predictionsHiddenDuringReview": True,
            "datasetDigest": "sha256:fixture",
        },
    )
    write_json(
        tmp_path / "reports" / "PHASE16_HELDOUT_RESULTS.json",
        {
            "schemaVersion": "phase16-heldout-evaluation/1.0.0",
            "containsRealPII": False,
            "documentCount": 1,
            "overall": {"fieldExactMatchRate": 0.5},
            "byFamily": {},
            "sensitiveFieldFalseAcceptanceCount": 0,
            "decision": {"controlledPilot": "NOT_PROMOTED"},
            "evaluationRunCount": 1,
            "thresholdRetuned": False,
            "predictionsWereHidden": True,
        },
    )

    store = ReviewStore(tmp_path)
    document = store.document("H16-C-001")
    assert document["predictionsVisibleDuringReview"] is False
    assert "predictions" not in document
    assert store.state()["pending"] == 1
    assert store.results()["decision"]["controlledPilot"] == "NOT_PROMOTED"
    assert "predictions" not in store.results()

    result = store.update(
        {
            "documentId": "H16-C-001",
            "fields": {
                "fullName": "Nguyễn Văn Mẫu",
                "headline": "Chuyên viên",
                "email": "sample@example.com",
                "phoneNumber": "",
                "address": "",
            },
            "skipped": ["phoneNumber", "address"],
        }
    )

    assert result == {"total": 1, "confirmed": 1, "pending": 0}
    reloaded = ReviewStore(tmp_path)
    assert reloaded.state()["pending"] == 0
    saved = reloaded.read_json(reloaded.queue_path)
    assert saved["documents"][0]["fields"]["phoneNumber"]["status"] == "SKIPPED"


def test_pending_timesheet_uses_table_review_and_validates_rectangular_rows(
    tmp_path: Path,
) -> None:
    assert "Bảng nhân viên và chấm công" in HTML
    source = (
        tmp_path
        / "source"
        / "05_employee_form_table"
        / "bang-cham-cong-synthetic.jpg"
    )
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic-xlsx-fixture")
    legacy_fields = {
        name: {"status": "PENDING_REVIEW", "value": ""}
        for name in (
            "formNumber",
            "employeeName",
            "employeeId",
            "dateOfBirth",
            "gender",
            "department",
            "jobTitle",
            "email",
            "phoneNumber",
            "address",
            "organization",
            "joinDate",
        )
    }
    queue = {
        "schemaVersion": "phase16-heldout-ground-truth-queue/1.0.0",
        "datasetId": "fixture",
        "datasetDigest": "sha256:fixture",
        "containsRealPII": False,
        "predictionsVisibleDuringReview": False,
        "groundTruthStatus": "PENDING_REVIEW",
        "documents": [
            {
                "documentId": "H16-EFT-001",
                "documentFamily": "EMPLOYEE_FORM_TABLE",
                "sourcePath": (
                    "source/05_employee_form_table/"
                    "bang-cham-cong-synthetic.jpg"
                ),
                "sourceSha256": "fixture",
                "status": "PENDING_REVIEW",
                "fields": legacy_fields,
            }
        ],
    }
    write_json(tmp_path / "ground_truth" / "review_queue_private.json", queue)
    write_json(
        tmp_path / "predictions" / "HIDDEN_PREDICTIONS_STATUS.json",
        {
            "status": "BLINDED_PREDICTIONS_READY",
            "predictionsHiddenDuringReview": True,
            "datasetDigest": "sha256:fixture",
        },
    )

    store = ReviewStore(tmp_path)
    document = store.document("H16-EFT-001")
    assert document["reviewProfile"] == "TIMESHEET"
    assert set(document["fields"]) == {
        "documentTitle",
        "timesheetPeriod",
        "organization",
        "department",
        "attendanceLegend",
    }
    result = store.update(
        {
            "documentId": "H16-EFT-001",
            "fields": {
                "documentTitle": "Báº¢NG CHáº¤M CÃ”NG",
                "timesheetPeriod": "08/2099",
                "organization": "CÃ”NG TY SYNTHETIC",
                "department": "PHÃ’NG THá»¬ NGHIá»†M",
                "attendanceLegend": "X=Äi lÃ m",
            },
            "skipped": [],
            "tableRows": [
                ["SYN-001", "NhÃ¢n viÃªn máº«u A", "PhÃ²ng A", "X"],
                ["SYN-002", "NhÃ¢n viÃªn máº«u B", "PhÃ²ng B", "P"],
            ],
        }
    )
    assert result["confirmed"] == 1
    saved = store.read_json(store.queue_path)["documents"][0]
    assert saved["tables"]["attendance"]["status"] == "CONFIRMED"
    assert len(saved["tables"]["attendance"]["rows"]) == 2
