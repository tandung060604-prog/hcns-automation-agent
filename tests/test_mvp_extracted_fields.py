from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "ocr_lab" / "api"
sys.path.insert(0, str(API_ROOT))

from serve_dashboard_api import extracted_fields_from_template_result  # noqa: E402


def test_extracted_fields_prefer_data_and_drop_hidden() -> None:
    result = {
        "data": {
            "employeeName": "Nguyễn Văn An",
            "leaveDays": 2,
            "missingFields": ["reason"],
            "confidence": 0.9,
        },
        "structuredFields": {"employeeName": "WRONG"},
    }

    fields = extracted_fields_from_template_result(result)

    assert fields == {"employeeName": "Nguyễn Văn An", "leaveDays": 2}


def test_extracted_fields_fallback_to_structured_fields() -> None:
    result = {"structuredFields": {"employeeName": "Fallback", "department": "HCNS"}}
    assert extracted_fields_from_template_result(result) == {
        "employeeName": "Fallback",
        "department": "HCNS",
    }
