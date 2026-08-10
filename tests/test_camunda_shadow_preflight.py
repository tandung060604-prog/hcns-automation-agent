from __future__ import annotations

from unittest import TestCase

from hcns_agent.adapters.camunda7.shadow_preflight import (
    ShadowPreflightCaseReport,
    ShadowPreflightReport,
    build_local_shadow_gateway,
)


def _case(*, completed: bool = True, duration_seconds: float = 2.0) -> ShadowPreflightCaseReport:
    return ShadowPreflightCaseReport(
        case_id="M5-SYNTHETIC",
        document_type="LEAVE_REQUEST",
        reached_user_review=True,
        completed=completed,
        duration_seconds=duration_seconds,
        auto_continue_observed=False,
        hris_simulated=True,
        notification_simulated=True,
    )


class ShadowPreflightReportTests(TestCase):
    def test_report_passes_only_the_full_synthetic_review_first_gate(self) -> None:
        report = ShadowPreflightReport(
            deployment_completed=True,
            cases=(_case(), _case()),
            auto_continue_count=0,
            raw_exposure_count=0,
            duplicate_result_artifacts=0,
            unreconciled_cases=0,
            real_side_effect_count=0,
        )

        self.assertTrue(report.passed)
        self.assertEqual("M5-CAM-001B", report.as_dict()["milestone"])

    def test_report_holds_when_a_case_is_slow_or_unreconciled(self) -> None:
        report = ShadowPreflightReport(
            deployment_completed=True,
            cases=(_case(duration_seconds=60.0), _case(completed=False)),
            auto_continue_count=0,
            raw_exposure_count=0,
            duplicate_result_artifacts=0,
            unreconciled_cases=1,
            real_side_effect_count=0,
        )

        self.assertFalse(report.passed)

    def test_preflight_gateway_rejects_non_local_camunda_urls(self) -> None:
        with self.assertRaises(ValueError):
            build_local_shadow_gateway(
                base_url="https://camunda.example.invalid/engine-rest",
                worker_id="synthetic-worker",
            )
