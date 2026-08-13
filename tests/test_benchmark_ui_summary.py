from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from serve_dashboard_api import build_local_benchmark_summary  # noqa: E402


class _SyntheticUserOcr:
    def list_template_sessions(self) -> list[dict[str, object]]:
        return []


def test_benchmark_summary_uses_aggregate_evidence_without_exposing_values(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "aggregate.json"
    manifest_path = tmp_path / "manifest.json"
    report_path.write_text(
        json.dumps(
            {
                "schemaVersion": "external-dataset-data12-aggregate/1.0.0",
                "datasetId": "synthetic-v2",
                "decision": "PASS",
                "promotionAllowed": False,
                "containsRawFieldValues": False,
                "groundTruthUsedForScoringOnly": True,
                "byCategory": {
                    "cv": {"fields": 10, "exactRate": 0.9, "presenceRate": 1.0},
                    "contract": {"fields": 14, "exactRate": 1.0, "presenceRate": 1.0},
                    "ielts": {"fields": 5, "exactRate": 1.0, "presenceRate": 1.0},
                },
            }
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "dataset": {"datasetId": "synthetic-v2"},
                "cases": [
                    {"category": "cv"},
                    {"category": "contract"},
                    {"category": "ielts"},
                ],
            }
        ),
        encoding="utf-8",
    )

    class _Handler:
        user_ocr = _SyntheticUserOcr()
        benchmark_report = report_path
        benchmark_manifest = manifest_path
        external_dataset_inventory = None
        cccd_heldout_root = None

    payload = build_local_benchmark_summary(_Handler)
    rows = {row["key"]: row for row in payload["rows"]}
    assert list(rows) == ["cv", "contract", "ielts", "cccd-front", "leave", "overtime"]
    assert rows["cv"]["exactMatchRate"] == 0.9
    assert rows["leave"]["benchmarkDocumentCount"] == 15
    assert rows["leave"]["benchmarkSampleCount"] == 7
    assert rows["overtime"]["benchmarkDocumentCount"] == 15
    assert rows["overtime"]["benchmarkSampleCount"] == 7
    assert rows["cv"]["source"].startswith("DATA-29")
    assert payload["evidence"]["displayOnly"] is True
    assert payload["evidence"]["decision"] == "HOLD"
    assert payload["evidence"]["promotionAllowed"] is False
    assert payload["evidence"]["containsRawFieldValues"] is False
    assert payload["developmentAggregate"] == {
        "label": "DATA-29",
        "scope": "DEVELOPMENT_AGGREGATE",
        "fieldCount": 29,
        "exactFieldCount": 28,
        "acceptedFieldCount": 28,
        "matchingPolicyVersion": None,
        "decision": "HOLD",
        "promotionAllowed": False,
        "displayOnly": True,
    }
    serialized = json.dumps(payload)
    assert "Candidate Synthetic" not in serialized
