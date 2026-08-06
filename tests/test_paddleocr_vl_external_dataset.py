from pathlib import Path

from scripts.run_paddleocr_vl_external_dataset import (
    MODEL_NAME,
    RUNTIME_MODEL_NAME,
    VLM_MAX_NEW_TOKENS,
    VLM_MAX_PIXELS,
    _benchmark_report,
    _markdown_canonical,
    _percentile,
    _scan_records,
    _tree_manifest,
)


def test_data21_model_pin_uses_registered_runtime_alias() -> None:
    assert MODEL_NAME == "PaddleOCR-VL-1.6"
    assert RUNTIME_MODEL_NAME == "PaddleOCR-VL-1.6-0.9B"
    assert VLM_MAX_PIXELS == 500_000
    assert VLM_MAX_NEW_TOKENS == 1_024


def test_data21_selects_only_fixed_scan_formats() -> None:
    records = _scan_records(
        {
            "cases": [
                {"caseId": "native", "sourceFormat": "DOCX"},
                {"caseId": "scan", "sourceFormat": "PDF_SCAN"},
                {"caseId": "image", "sourceFormat": "IMAGE"},
            ]
        }
    )

    assert [record["caseId"] for record in records] == ["scan", "image"]


def test_data21_markdown_adapter_preserves_page_order_without_geometry() -> None:
    canonical = _markdown_canonical(["# Synthetic\nName: Example", "Page two"])

    assert canonical["plainText"] == "# Synthetic\nName: Example\n\nPage two"
    assert len(canonical["pages"]) == 2
    assert [block["text"] for block in canonical["pages"][0]["blocks"]] == [
        "# Synthetic",
        "Name: Example",
    ]
    assert [block["text"] for block in canonical["pages"][1]["blocks"]] == ["Page two"]
    assert all(
        block["evidence"]["bbox"] is None
        for page in canonical["pages"]
        for block in page["blocks"]
    )


def test_data21_report_is_aggregate_only_and_manual_review_only(tmp_path: Path) -> None:
    report = _benchmark_report(
        dataset={"datasetId": "synthetic", "contentDigest": "sha256:test"},
        model_manifest={"modelName": "PaddleOCR-VL-1.6"},
        requested=2,
        processed=2,
        failed=0,
        page_count=2,
        latencies=[10.0, 20.0],
        peak_python_bytes=123,
        peak_rss_bytes=None,
        failures={},
        status="BENCHMARK_DONE_FALLBACK_DISABLED",
    )

    assert report["system"]["latencyP50Ms"] == 10.0
    assert report["system"]["latencyP95Ms"] == 20.0
    assert report["quality"]["strictFieldExactMatchRate"] is None
    assert report["safety"]["scanAlwaysManualReview"] is True
    assert report["safety"]["fallbackEnabled"] is False
    assert report["safety"]["promotionAllowed"] is False
    assert report["containsRawFieldValues"] is False


def test_data21_tree_manifest_and_percentile_are_deterministic(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    first = _tree_manifest(tmp_path)
    second = _tree_manifest(tmp_path)

    assert first == second
    assert first["fileCount"] == 2
    assert first["byteCount"] == 2
    assert _percentile([10.0, 20.0, 30.0], 0.50) == 20.0
