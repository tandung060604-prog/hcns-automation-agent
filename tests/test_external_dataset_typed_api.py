from __future__ import annotations

import hashlib
import http.client
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from external_dataset_review import FIELD_SPECS  # noqa: E402
from external_dataset_typed import (  # noqa: E402
    TypedDatasetError,
    build_typed_export,
    load_typed_document,
    load_typed_summary,
    resolve_typed_paths,
)

from scripts.run_external_dataset_aggregate_pilot import (  # noqa: E402
    build_aggregate_report,
)


def build_bundle(tmp_path: Path) -> tuple[Path, object]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    projection_path = tmp_path / "synthetic-typed-canonical.json"
    approval_path = tmp_path / "synthetic-typed-canonical-APPROVED.json"
    report_path = tmp_path / "synthetic-data09-aggregate-pilot.json"
    fields = []
    for index, name in enumerate(FIELD_SPECS["contract"]):
        fields.append(
            {
                "name": name,
                "reviewStatus": "CONFIRMED",
                "sourceValue": f"Synthetic source {name}",
                "dataType": "string",
                "normalizedValue": f"Synthetic normalized {name}",
                "normalizationStatus": "NORMALIZED",
            }
        )
        if index == 10:
            fields[-1].update(
                dataType="number",
                normalizedValue=40,
                unit="hours_per_week",
            )
        if index == 11:
            fields[-1].update(
                dataType="integer",
                normalizedValue=12500000,
                unit="VND",
                currency="VND",
            )
    projection = {
        "schemaVersion": "1.0.0",
        "dataset": {
            "datasetId": "synthetic-external",
            "version": "v1",
            "contentDigest": "sha256:" + "a" * 64,
            "groundTruthSha256": "sha256:" + "b" * 64,
            "groundTruthStatus": "SEALED",
        },
        "sourcePolicy": {
            "localOnly": True,
            "sourceValuesPreserved": True,
            "predictionsOpened": False,
            "predictionBlind": True,
        },
        "documents": [
            {
                "caseId": "contract-001",
                "category": "contract",
                "documentType": "EMPLOYMENT_CONTRACT",
                "sourceFormat": "DOCX",
                "pageCount": 1,
                "scopeStatus": "ACTIVE",
                "fields": fields,
            }
        ],
    }
    projection_path.write_text(json.dumps(projection, sort_keys=True), encoding="utf-8")
    report = build_aggregate_report(projection)
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    marker = {
        "schemaVersion": "external-dataset-typed-approval/1.0.0",
        "dataset": projection["dataset"],
        "typedProjectionSha256": _sha256(projection_path),
        "aggregateReportSha256": _sha256(report_path),
        "approvalStatus": "APPROVED",
        "approvedBy": "SYNTHETIC_REVIEWER",
        "approvedAt": "2026-08-03T00:00:00+00:00",
        "predictionsOpened": False,
        "promotionAllowed": False,
    }
    approval_path.write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
    return tmp_path, resolve_typed_paths(
        tmp_path,
        projection_path=projection_path,
        approval_path=approval_path,
        aggregate_report_path=report_path,
    )


def test_summary_and_export_are_read_only_and_omit_source_values(tmp_path: Path) -> None:
    _, paths = build_bundle(tmp_path)
    summary = load_typed_summary(paths)
    assert summary["approval"]["status"] == "APPROVED"
    assert summary["scope"]["activeFieldCount"] == 14
    assert "sourceValue" not in json.dumps(summary)

    detail = load_typed_document(paths, "contract-001")
    assert detail["policy"]["containsRawFieldValues"] is False
    assert "sourceValue" not in json.dumps(detail)
    detail_with_source = load_typed_document(paths, "contract-001", include_source_value=True)
    assert detail_with_source["policy"]["containsRawFieldValues"] is True
    assert "Synthetic source" in json.dumps(detail_with_source)

    json_body, _, _ = build_typed_export(paths, "json")
    csv_body, _, _ = build_typed_export(paths, "csv")
    assert b"sourceValue" not in json_body
    assert b"sourceValue" not in csv_body
    assert b"normalizedValue" in json_body


def test_reader_fails_closed_when_projection_drifts(tmp_path: Path) -> None:
    _, paths = build_bundle(tmp_path)
    projection = json.loads(paths.projection.read_text(encoding="utf-8"))
    projection["documents"][0]["fields"][0]["normalizedValue"] = "tampered"
    paths.projection.write_text(json.dumps(projection), encoding="utf-8")
    with pytest.raises(TypedDatasetError, match="SHA-256 drifted"):
        load_typed_summary(paths)


def test_http_api_exposes_get_only_typed_routes(tmp_path: Path) -> None:
    data_root, paths = build_bundle(tmp_path / "bundle")
    data_root.mkdir(exist_ok=True)
    from serve_dashboard_api import DashboardHandler, UserOCRService  # noqa: PLC0415

    DashboardHandler.data_root = data_root
    DashboardHandler.cccd_heldout_root = None
    DashboardHandler.external_dataset_root = data_root
    DashboardHandler.external_dataset_inventory = None
    DashboardHandler.external_dataset_ground_truth = None
    DashboardHandler.external_dataset_typed_projection = paths.projection
    DashboardHandler.external_dataset_typed_approval = paths.approval
    DashboardHandler.external_dataset_typed_report = paths.aggregate_report
    DashboardHandler.native_indexes = {}
    DashboardHandler.user_ocr = UserOCRService(data_root)
    DashboardHandler.template_processor = None  # type: ignore[assignment]
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        connection.request("GET", "/external-dataset/typed/summary")
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["scope"]["activeFieldCount"] == 14
        assert "sourceValue" not in json.dumps(payload)

        connection.request("GET", "/external-dataset/typed/export?format=csv")
        response = connection.getresponse()
        body = response.read()
        assert response.status == 200
        assert b"sourceValue" not in body

        connection.request("POST", "/external-dataset/typed/export?format=json", body=b"{}")
        response = connection.getresponse()
        response.read()
        assert response.status == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
