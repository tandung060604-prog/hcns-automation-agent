from __future__ import annotations

from pathlib import Path

from hcns_agent.templates.service import build_local_template_processing_service

ROOT = Path(__file__).resolve().parents[1]


def test_local_ocr_policy_prefers_easyocr_and_allows_paddle_rollback(monkeypatch) -> None:
    monkeypatch.delenv("HCNS_TEMPLATE_OCR_BACKEND", raising=False)
    optimized = build_local_template_processing_service()
    assert optimized._ocr_engine.name == "easyocr/vi-greedy"

    rollback = build_local_template_processing_service(ocr_backend="paddle")
    assert rollback._ocr_engine.name == "paddleocr/pp-ocrv5-vi"


def test_dashboard_launcher_uses_selected_backend_health_contract() -> None:
    launcher = (ROOT / "apps/ocr_lab/api/start_dashboard.ps1").read_text(
        encoding="utf-8"
    )

    assert '[string]$TemplateOcrBackend = "easyocr"' in launcher
    assert "$health.userUpload.backendAvailable" in launcher
    assert "$health.userUpload.paddleOcrAvailable" not in launcher
