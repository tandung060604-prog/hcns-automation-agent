"""Command-line interface for offline benchmark evaluation and promotion."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from hcns_agent.adapters.benchmark_json import (
    BenchmarkJsonError,
    load_ground_truth,
    load_submission,
    write_comparison,
    write_report,
    write_submission,
)
from hcns_agent.adapters.benchmark_runtime import (
    LocalSourcePageCounter,
    PaddleBenchmarkBackend,
)
from hcns_agent.adapters.mineru import MineruBenchmarkBackend
from hcns_agent.adapters.paddleocr import PaddleOcrEngine
from hcns_agent.application.benchmark import (
    BenchmarkHarness,
    BenchmarkInputError,
    PromotionGate,
)
from hcns_agent.application.benchmark_runner import BenchmarkRunner
from hcns_agent.bootstrap import build_default_pipeline, build_default_understanding
from hcns_agent.domain.evaluation import (
    PromotionEvidence,
    PromotionPolicy,
    PromotionStatus,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            return _evaluate(args)
        if args.command == "compare":
            return _compare(args)
        if args.command == "run":
            return _run(args)
    except (BenchmarkJsonError, BenchmarkInputError, ValueError) as exc:
        parser.error(str(exc))
    parser.error("A benchmark command is required")
    return 2


def _evaluate(args: argparse.Namespace) -> int:
    manifest, ground_truth = load_ground_truth(args.ground_truth)
    submission = load_submission(args.predictions)
    report = BenchmarkHarness().evaluate(manifest, ground_truth, submission)
    write_report(args.output, report)
    return 0


def _compare(args: argparse.Namespace) -> int:
    manifest, ground_truth = load_ground_truth(args.ground_truth)
    harness = BenchmarkHarness()
    baseline = harness.evaluate(manifest, ground_truth, load_submission(args.baseline))
    challenger = harness.evaluate(manifest, ground_truth, load_submission(args.challenger))
    policy = PromotionPolicy(
        minimum_field_exact_match_improvement=args.minimum_field_improvement,
        maximum_latency_p95_ms=args.maximum_latency_p95_ms,
        maximum_review_rate_increase=args.maximum_review_rate_increase,
        maximum_failure_rate=args.maximum_failure_rate,
        minimum_benchmark_pages=args.minimum_benchmark_pages,
        minimum_ocr_cases=args.minimum_ocr_cases,
    )
    evidence = PromotionEvidence(
        contract_tests_passed=args.contract_tests_passed,
        privacy_approved=args.privacy_approved,
        license_approved=args.license_approved,
        model_provenance_approved=args.model_provenance_approved,
    )
    decision = PromotionGate(policy).evaluate(
        manifest,
        baseline,
        challenger,
        evidence,
        as_of=args.as_of,
    )
    write_comparison(args.output, baseline, challenger, decision)
    return 0 if decision.status is PromotionStatus.PROMOTE else 2


def _run(args: argparse.Namespace) -> int:
    manifest, ground_truth = load_ground_truth(args.ground_truth)
    backend: PaddleBenchmarkBackend | MineruBenchmarkBackend
    if args.backend == "paddle":
        backend = PaddleBenchmarkBackend(
            build_default_pipeline(PaddleOcrEngine.from_default(device=args.device)),
            device=args.device,
        )
    else:
        backend = MineruBenchmarkBackend(
            build_default_understanding(),
            timeout_seconds=args.timeout_seconds,
            device=args.device,
        )
    submission = BenchmarkRunner(LocalSourcePageCounter()).run(
        manifest,
        ground_truth,
        backend,
        private_root=args.private_root,
        output_directory=args.work_root,
    )
    write_submission(args.output, submission)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hcns-agent-benchmark",
        description="Evaluate authorized Ground Truth without emitting raw field values.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser("evaluate", help="Generate an aggregate benchmark report")
    _path_argument(evaluate, "--ground-truth", "Versioned Ground Truth JSON")
    _path_argument(evaluate, "--predictions", "Backend prediction JSON")
    _path_argument(evaluate, "--output", "Aggregate report JSON")

    compare = subparsers.add_parser("compare", help="Compare baseline and challenger")
    _path_argument(compare, "--ground-truth", "Versioned Ground Truth JSON")
    _path_argument(compare, "--baseline", "Baseline prediction JSON")
    _path_argument(compare, "--challenger", "Challenger prediction JSON")
    _path_argument(compare, "--output", "Aggregate comparison JSON")
    compare.add_argument("--minimum-field-improvement", type=float, default=0.01)
    compare.add_argument("--maximum-latency-p95-ms", type=float, default=5_000.0)
    compare.add_argument("--maximum-review-rate-increase", type=float, default=0.02)
    compare.add_argument("--maximum-failure-rate", type=float, default=0.01)
    compare.add_argument("--minimum-benchmark-pages", type=int, default=30)
    compare.add_argument("--minimum-ocr-cases", type=int, default=1)
    compare.add_argument("--as-of", type=_iso_date)
    compare.add_argument("--contract-tests-passed", action="store_true")
    compare.add_argument("--privacy-approved", action="store_true")
    compare.add_argument("--license-approved", action="store_true")
    compare.add_argument("--model-provenance-approved", action="store_true")

    run = subparsers.add_parser(
        "run",
        help="Run one local backend on an authorized 30-50 page corpus",
    )
    _path_argument(run, "--ground-truth", "Versioned Ground Truth JSON")
    _path_argument(run, "--private-root", "Controlled data root containing source files")
    _path_argument(run, "--work-root", "Private directory for backend intermediate output")
    _path_argument(run, "--output", "Private prediction JSON")
    run.add_argument("--backend", choices=("paddle", "mineru"), required=True)
    run.add_argument("--device", default="cpu")
    run.add_argument("--timeout-seconds", type=int, default=900)
    return parser


def _path_argument(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    parser.add_argument(name, type=Path, required=True, help=help_text)


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected an ISO date (YYYY-MM-DD)") from exc


if __name__ == "__main__":
    raise SystemExit(main())
