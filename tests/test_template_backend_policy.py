from __future__ import annotations

from hcns_agent.templates.service import build_local_template_processing_service


def test_local_ocr_policy_prefers_easyocr_and_allows_paddle_rollback(monkeypatch) -> None:
    monkeypatch.delenv("HCNS_TEMPLATE_OCR_BACKEND", raising=False)
    optimized = build_local_template_processing_service()
    assert optimized._ocr_engine.name == "easyocr/vi-greedy"

    rollback = build_local_template_processing_service(ocr_backend="paddle")
    assert rollback._ocr_engine.name == "paddleocr/pp-ocrv5-vi"
