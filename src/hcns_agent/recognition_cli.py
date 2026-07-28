"""CLI for Vietnamese OCR recognition-only evaluation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from hcns_agent.adapters.recognition_json import (
    RecognitionJsonError,
    load_recognition_characters,
    load_recognition_ground_truth,
    load_recognition_submission,
    write_charset_audit,
    write_recognition_report,
)
from hcns_agent.application.recognition_benchmark import (
    RecognitionBenchmarkError,
    VietnameseRecognitionBenchmark,
    audit_vietnamese_charset,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            recognition_report = VietnameseRecognitionBenchmark().evaluate(
                load_recognition_ground_truth(args.ground_truth),
                load_recognition_submission(args.predictions),
                confidence_threshold=args.confidence_threshold,
            )
            write_recognition_report(
                args.output,
                recognition_report,
                overwrite=args.overwrite,
            )
            return 0
        if args.command == "audit-charset":
            characters = load_recognition_characters(args.dictionary)
            audit_report = audit_vietnamese_charset(
                characters,
                model_identifier=args.model_identifier,
            )
            write_charset_audit(args.output, audit_report, overwrite=args.overwrite)
            return 0
    except (OSError, RecognitionJsonError, RecognitionBenchmarkError, ValueError) as exc:
        parser.error(str(exc))
    parser.error("A recognition command is required")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hcns-agent-recognition",
        description="Evaluate Vietnamese line recognition without emitting raw text.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    evaluate = commands.add_parser(
        "evaluate",
        help="Generate aggregate CER/WER/diacritic metrics",
    )
    _path_argument(evaluate, "--ground-truth", "Private line Ground Truth JSON")
    _path_argument(evaluate, "--predictions", "Private recognizer prediction JSON")
    _path_argument(evaluate, "--output", "Aggregate report JSON")
    evaluate.add_argument("--confidence-threshold", type=float, default=0.95)
    evaluate.add_argument("--overwrite", action="store_true")

    audit = commands.add_parser(
        "audit-charset",
        help="Check whether a recognition dictionary can emit Vietnamese characters",
    )
    _path_argument(
        audit,
        "--dictionary",
        "UTF-8 dictionary or Paddle inference.yml",
    )
    _path_argument(audit, "--output", "Aggregate charset audit JSON")
    audit.add_argument("--model-identifier", required=True)
    audit.add_argument("--overwrite", action="store_true")
    return parser


def _path_argument(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    parser.add_argument(name, type=Path, required=True, help=help_text)


if __name__ == "__main__":
    raise SystemExit(main())
