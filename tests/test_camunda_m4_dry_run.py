from __future__ import annotations

from pathlib import Path

from hcns_agent.adapters.camunda7.dry_run import run_m4_dry_run


def test_m4_cam_006_dry_run_matrix_passes_ten_synthetic_scenarios(
    tmp_path: Path,
) -> None:
    report = run_m4_dry_run(tmp_path)

    assert report.passed
    assert report.passed_count == 10
    assert report.total_count == 10
    assert [scenario.scenario_id for scenario in report.scenarios] == [
        f"CAM-006-{index:02d}" for index in range(1, 11)
    ]
    assert report.false_auto_continue == 0
    assert report.duplicate_result_artifacts == 0
    assert report.technical_retries == 1
    assert report.real_side_effects_enabled is False
    assert report.contains_raw_field_values is False
