#!/usr/bin/env python3
"""Run one private development aggregate without touching evaluate-once artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "ocr_lab" / "api"
for path in (ROOT, API):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from external_dataset_prediction import build_aggregate_report, build_gate_report  # noqa: E402


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--prediction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    parser.add_argument("--baseline-prediction", type=Path)
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--gate-output", type=Path)
    parser.add_argument("--gate-marker", type=Path)
    parser.add_argument("--fallback-candidate", action="store_true")
    args = parser.parse_args()

    if args.output.exists() or args.marker.exists():
        raise SystemExit("Development aggregate output already exists; choose a new private path")
    gate_args = (args.baseline_prediction, args.baseline_report, args.gate_output, args.gate_marker)
    gate_mode = any(value is not None for value in gate_args)
    if gate_mode and not all(value is not None for value in gate_args):
        raise SystemExit(
            "DATA-20 gate mode requires --baseline-prediction, --baseline-report, "
            "--gate-output and --gate-marker together"
        )
    if args.fallback_candidate and not gate_mode:
        raise SystemExit("--fallback-candidate requires DATA-20 gate mode")
    if args.gate_output is not None and (
        args.gate_output.exists() or args.gate_marker.exists()
    ):
        raise SystemExit("DATA-20 gate output already exists; choose new private paths")
    ground_truth = _read(args.ground_truth)
    seal = _read(args.seal)
    prediction = _read(args.prediction)
    baseline_prediction = _read(args.baseline_prediction) if args.baseline_prediction else None
    baseline_report = _read(args.baseline_report) if args.baseline_report else None
    dataset = ground_truth.get("dataset", {})
    review = ground_truth.get("review", {})
    if dataset.get("groundTruthStatus") != "SEALED" or review.get("status") != "CONFIRMED":
        raise SystemExit("GroundTruth must be SEALED and CONFIRMED")
    if seal.get("predictionsOpened") is not False:
        raise SystemExit("Seal metadata says predictions were opened")
    gt_sha256 = _sha256(args.ground_truth)
    if seal.get("groundTruthSha256") != gt_sha256:
        raise SystemExit("Seal metadata does not match GroundTruth")
    if prediction.get("datasetId") != dataset.get("datasetId"):
        raise SystemExit("Prediction datasetId does not match GroundTruth")
    if (
        baseline_prediction is not None
        and baseline_prediction.get("datasetId") != dataset.get("datasetId")
    ):
        raise SystemExit("Baseline prediction datasetId does not match GroundTruth")
    if baseline_report is not None and baseline_report.get("datasetId") != dataset.get("datasetId"):
        raise SystemExit("Baseline report datasetId does not match GroundTruth")

    report = build_aggregate_report(
        prediction, ground_truth, baseline_prediction=baseline_prediction
    )
    report.update(
        {
            "evaluationKind": "development-aggregate-comparison",
            "groundTruth": {
                "status": "SEALED",
                "reviewStatus": "CONFIRMED",
                "sha256": gt_sha256,
                "fieldCount": sum(
                    len(case.get("fields", [])) for case in ground_truth.get("cases", [])
                ),
            },
            "prediction": {
                "sha256": _sha256(args.prediction),
                "predictionsOpened": False,
            },
        }
    )
    _write(args.output, report)
    _write(
        args.marker,
        {
            "schemaVersion": "external-dataset-development-aggregate/1.0.0",
            "evaluationKind": "development-aggregate-comparison",
            "evaluatedAt": report["evaluatedAt"],
            "datasetId": report["datasetId"],
            "groundTruthSha256": gt_sha256,
            "predictionSha256": _sha256(args.prediction),
            "aggregateReportSha256": _sha256(args.output),
            "predictionsOpened": False,
            "evaluateOnceArtifactTouched": False,
            "promotionAllowed": False,
        },
    )
    if args.gate_output is not None and args.gate_marker is not None:
        baseline_gate_report = (
            build_aggregate_report(baseline_prediction, ground_truth)
            if baseline_prediction is not None
            else baseline_report
        )
        gate = build_gate_report(
            report, baseline_gate_report, fallback_candidate=args.fallback_candidate
        )
        gate.update(
            {
                "candidateAggregateReportSha256": _sha256(args.output),
                "baselineReportSha256": _sha256(args.baseline_report),
            }
        )
        _write(args.gate_output, gate)
        _write(
            args.gate_marker,
            {
                "schemaVersion": "external-dataset-data20-gate/1.0.0",
                "evaluationKind": "development-gate-harness",
                "evaluatedAt": gate["evaluatedAt"],
                "datasetId": gate["datasetId"],
                "candidateAggregateReportSha256": _sha256(args.output),
                "baselineReportSha256": _sha256(args.baseline_report),
                "gateReportSha256": _sha256(args.gate_output),
                "evaluateOnceArtifactTouched": False,
                "promotionAllowed": False,
                "decision": gate["decision"],
            },
        )
        print(f"DATA-20 gate: {gate['decision']}")
    metrics = report["metrics"]
    print(
        "Development aggregate ready: "
        f"strict={metrics['fieldExactMatchCount']}/{report['fieldCount']} "
        f"semantic={metrics['fieldSemanticMatchCount']}/{report['fieldCount']} "
        f"accepted={metrics['fieldAcceptedMatchCount']}/{report['fieldCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
