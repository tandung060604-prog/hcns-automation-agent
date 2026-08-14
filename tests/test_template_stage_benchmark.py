import json
from pathlib import Path

from scripts.benchmark_template_stages import (
    STAGES,
    TIMING_SCHEMA_VERSION,
    _failure_code,
    _load_record,
    _summarize,
)


def test_stage_summary_reports_nearest_rank_p50_and_p95() -> None:
    records = [
        {stage: float(index) for stage in STAGES}
        for index in range(1, 31)
    ]

    summary = _summarize(records)

    assert set(summary) == set(STAGES)
    assert summary["ocr"] == {"p50": 15.0, "p95": 29.0}


def test_resume_record_contains_only_stage_timings(tmp_path: Path) -> None:
    run_root = tmp_path / "run-001"
    run_root.mkdir()
    record = {stage: float(index) for index, stage in enumerate(STAGES, start=1)}
    (run_root / "performance.json").write_text(
        json.dumps(
            {"schemaVersion": TIMING_SCHEMA_VERSION, "timingsMs": record}
        ),
        encoding="utf-8",
    )

    assert _load_record(run_root) == record
    assert _load_record(tmp_path / "missing") is None


def test_failure_code_does_not_expose_exception_message() -> None:
    class SafeFailure(RuntimeError):
        code = "OCR_PROCESSING_FAILED"

    assert _failure_code(SafeFailure("private value")) == "OCR_PROCESSING_FAILED"
