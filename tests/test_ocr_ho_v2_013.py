from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from phase11_8_shadow_uat import (  # noqa: E402
    load_shadow_document,
    load_shadow_summary,
)
from test_phase11_8_shadow_uat import SESSION_ID, build_root  # noqa: E402


def test_promotion_review_prefers_v11_9_artifacts_without_ground_truth(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    session = root / "user_uploads-sessions" / SESSION_ID
    (session / "phase11_9_v2").mkdir()
    shutil.copyfile(
        session / "phase11_8_v2" / "field_consensus.json",
        session / "phase11_9_v2" / "field_consensus.json",
    )
    report = {
        "candidateVersion": "11.9.1",
        "policyId": "phase11.9-v2-deterministic-address-roi",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "targetFields": ["placeOfOrigin", "placeOfResidence"],
        "protectedFields": ["identityNumber", "fullName"],
        "metrics": {},
        "promotionGate": {
            "status": "DEVELOPMENT_PASS",
            "productionPromotionAllowed": False,
            "schemaErrorCount": 0,
            "manualReviewFieldCount": 8,
        },
    }
    report_path = (
        root
        / "output"
        / "phase11"
        / "reports"
        / "CCCD_OCR_HO_V2_011_DEVELOPMENT_COMPARISON.json"
    )
    report_path.write_text(
        json.dumps(report), encoding="utf-8"
    )

    summary = load_shadow_summary(root)
    assert summary["schemaVersion"] == "ocr-ho-v2-013-promotion-review/1.0.0"
    assert summary["candidateVersion"] == "11.9.1"
    assert summary["groundTruthLoaded"] is False

    detail = load_shadow_document(root, SESSION_ID)
    assert detail["candidateVersion"] == "11.9.1"
    assert detail["candidateReference"] == "phase11_9_v2/field_consensus.json"
    assert "groundTruth" not in detail
