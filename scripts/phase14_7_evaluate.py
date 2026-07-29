#!/usr/bin/env python3
"""Evaluate the sealed Phase 14.7 snapshot exactly once."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hcns_agent.application.phase14_7_evaluation import (
    PRIMARY,
    evaluate_phase14_7,
)
from hcns_agent.application.phase14_7_protocol import (
    atomic_write_json,
    sha256_file,
    verify_hidden_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument(
        "--benchmark-lock",
        type=Path,
        default=Path("config/phase14_6_benchmark_lock.json"),
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path.name}")
    return value


def percentage(value: float) -> str:
    return f"{value * 100:.2f}%"


def report_markdown(result: dict[str, Any]) -> str:
    rows = []
    for profile, metrics in result["profiles"].items():
        rows.append(
            "| "
            + " | ".join(
                (
                    profile,
                    percentage(metrics["exactMatchRate"]),
                    percentage(metrics["cer"]),
                    percentage(metrics["wer"]),
                    percentage(metrics["der"]),
                )
            )
            + " |"
        )
    selected = result["fixedPolicyReplay"]
    metrics = selected["metrics"]
    rows.append(
        "| fixed_policy_replay | "
        f"{percentage(metrics['exactMatchRate'])} | "
        f"{percentage(metrics['cer'])} | "
        f"{percentage(metrics['wer'])} | "
        f"{percentage(metrics['der'])} |"
    )
    decision = result["decision"]
    return "\n".join(
        (
            "# Phase 14.7 — CCCD held-out evaluation",
            "",
            "> Báo cáo chỉ chứa metric tổng hợp; không chứa nội dung CCCD, "
            "Ground Truth hoặc prediction theo dòng.",
            "",
            f"- Tài liệu độc lập: **{result['documentCount']}**/"
            f"{result['minimumDocumentCount']} yêu cầu",
            f"- Dòng được đánh giá: "
            f"**{result['review']['evaluatedConfirmedLineCount']}**",
            f"- Dòng bỏ qua: **{result['review']['skippedLineCount']}**",
            "- Prediction hiển thị khi review: **Không**",
            f"- Metric spec: `{result['metricSpecVersion']}`",
            "",
            "| Profile | Exact Match | CER | WER | DER |",
            "|---|---:|---:|---:|---:|",
            *rows,
            "",
            "## Fixed-policy replay",
            "",
            f"- Primary: `{PRIMARY}`",
            f"- Số lần chuyển recognizer: **{selected['switchCount']}**",
            f"- Lỗi primary được phục hồi: "
            f"**{selected['baselineErrorsRecovered']}**",
            f"- Dòng primary vốn đúng bị làm sai: "
            f"**{selected['baselineCorrectLost']}**",
            "",
            "## Quyết định",
            "",
            f"- Diagnostic quality: "
            f"`{decision['diagnosticQualitySignals']}`",
            f"- Sample gate: `{decision['heldOutSampleGate']}`",
            f"- Controlled pilot: `{decision['controlledPilot']}`",
            f"- Production: `{decision['production']}`",
            "",
        )
    )


def main() -> int:
    args = parse_args()
    root = args.dataset_root.resolve()
    queue_path = (
        root
        / "ground_truth"
        / "private_phase14_7"
        / "review_queue_private.json"
    )
    snapshot_path = (
        root / "predictions" / "phase14_7_hidden_predictions_private.json"
    )
    status_path = (
        root / "predictions" / "PHASE14_7_HIDDEN_PREDICTIONS_STATUS.json"
    )
    prediction_lock_path = (
        root / "locks" / "phase14_7_hidden_predictions.sha256"
    )
    dataset_lock_path = root / "locks" / "benchmark_lock.complete.json"
    output_path = root / "metrics" / "PHASE14_7_HELDOUT_RESULTS.json"
    report_path = root / "metrics" / "PHASE14_7_HELDOUT_RESULTS.md"
    ground_truth_lock_path = root / "locks" / "phase14_7_ground_truth.sha256"
    if (
        output_path.exists()
        or report_path.exists()
        or ground_truth_lock_path.exists()
    ):
        raise FileExistsError(
            "Phase 14.7 evaluation already exists; refusing a second run"
        )

    ground_truth = load_json(queue_path)
    snapshot = load_json(snapshot_path)
    status = load_json(status_path)
    benchmark_lock = load_json(args.benchmark_lock)
    verify_hidden_snapshot(
        queue=ground_truth,
        status=status,
        private_artifact_path=snapshot_path,
        lock_text=prediction_lock_path.read_text(encoding="ascii"),
    )
    if ground_truth.get("groundTruthStatus") != (
        "USER_CONFIRMED_HELD_OUT_GROUND_TRUTH"
    ):
        raise ValueError("Ground Truth review has not been completed")

    ground_truth_sha256 = sha256_file(queue_path)
    ground_truth_lock_path.write_text(
        f"{ground_truth_sha256}  "
        "ground_truth/private_phase14_7/review_queue_private.json\n",
        encoding="ascii",
    )
    result = evaluate_phase14_7(
        snapshot=snapshot,
        ground_truth=ground_truth,
        policy=benchmark_lock["policy"],
        minimum_document_count=int(
            benchmark_lock["heldOutProtocol"]["minimumDocumentCount"]
        ),
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        snapshot_sha256=sha256_file(snapshot_path),
        ground_truth_sha256=ground_truth_sha256,
        dataset_lock_sha256=sha256_file(dataset_lock_path),
    )
    atomic_write_json(output_path, result)
    report_path.write_text(report_markdown(result), encoding="utf-8")
    print(
        "Phase 14.7 evaluation complete: "
        f"documents={result['documentCount']}, "
        f"evaluated_lines="
        f"{result['review']['evaluatedConfirmedLineCount']}, "
        f"sample_gate={result['decision']['heldOutSampleGate']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
