from __future__ import annotations

from pathlib import Path

from scripts.phase16_hidden_predictions import (
    build_prepared_manifest,
    policy_prediction_document,
)


def test_native_documents_skip_ocr_render_and_keep_locked_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "01_cv" / "sample.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic-native-fixture")
    from hcns_agent.application.phase16_heldout import sha256_file

    manifest = {
        "datasetId": "fixture",
        "datasetDigest": "sha256:fixture",
        "documents": [
            {
                "documentId": "H16-C-001",
                "documentFamily": "CV",
                "sourcePath": source.relative_to(tmp_path).as_posix(),
                "sourceSha256": sha256_file(source),
                "sourceFormat": "DOCX",
                "sizeBytes": source.stat().st_size,
            }
        ],
    }

    prepared = build_prepared_manifest(
        tmp_path,
        tmp_path / "predictions" / "private_work",
        manifest,
    )

    assert prepared["containsRealPII"] is True
    assert prepared["datasetKind"] == "REAL_FIVE_FAMILY_HELDOUT"
    assert prepared["documents"][0]["pagePaths"] == []
    assert prepared["documents"][0]["pageSha256"] == []


def test_policy_prediction_contract_keeps_timesheet_tables() -> None:
    result = policy_prediction_document(
        {
            "documentId": "H17-EFT-001",
            "sourceSha256": "sha256:synthetic",
        },
        {
            "documentFamily": "EMPLOYEE_FORM_TABLE",
            "documentType": "TIMESHEET",
            "status": "needs_review",
            "confidence": 0.75,
        },
        {
            "fields": {},
            "tables": [
                {
                    "tableType": "TIMESHEET_EMPLOYEES",
                    "rows": [{"values": ["SYN001", "Mẫu"]}],
                }
            ],
            "summary": {},
        },
    )

    assert result["documentType"] == "TIMESHEET"
    assert result["tables"][0]["rows"][0]["values"][0] == "SYN001"
