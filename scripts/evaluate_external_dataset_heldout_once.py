#!/usr/bin/env python3
"""Run one create-only, aggregate-only DATA-24 held-out evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "ocr_lab" / "api"
for path in (ROOT, API):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from external_dataset_prediction import build_aggregate_report  # noqa: E402

from scripts.validate_data23_heldout_lock import validate_heldout_lock  # noqa: E402


class EvaluateOnceError(ValueError):
    """Raised when the held-out evaluate-once preflight fails."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluateOnceError(f"Invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise EvaluateOnceError(f"{path} must contain an object")
    return value


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _write_create_only(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise EvaluateOnceError(f"evaluate-once artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _approval(path: Path) -> dict[str, Any]:
    value = _read(path)
    if value.get("approved") is not True:
        raise EvaluateOnceError("DATA-24 approval is not granted")
    reference = value.get("approvalReference")
    if not isinstance(reference, str) or not reference.strip():
        raise EvaluateOnceError("DATA-24 approvalReference is missing")
    return value


def _final_gates(report: dict[str, Any]) -> dict[str, bool]:
    metrics = report.get("metrics", {})
    categories = report.get("byCategory", {})
    policy = report.get("ocrPolicy", {})
    strict_by_family = {
        family: float(categories.get(family, {}).get("exactRate", 0.0)) >= 0.80
        for family in ("contract", "cv", "ielts")
    }
    return {
        "strictOverallAtLeast80": float(metrics.get("fieldExactMatchRate", 0.0)) >= 0.80,
        "strictEachFamilyAtLeast80": all(strict_by_family.values()),
        "applicableCompletenessAtLeast95": float(
            metrics.get("applicableCompletenessRate", 0.0)
        )
        >= 0.95,
        "classificationAtLeast95": float(
            report.get("classification", {}).get("accuracy", 0.0)
        )
        >= 0.95,
        "schemaErrorsZero": int(report.get("schemaErrors", 0)) == 0,
        "sensitiveFalseAcceptanceZero": int(
            metrics.get("sensitiveFalseAcceptanceCount", 0)
        )
        == 0,
        "parserCorrectRegressionZero": int(
            metrics.get("parserCorrectRegressionCount", 0)
        )
        == 0,
        "scanAlwaysManualReview": bool(policy.get("ocrAlwaysManualReview")),
        "falseAutoContinueZero": int(policy.get("falseAutoContinueCount", 0)) == 0,
        "acceptedTextReportedSeparately": "fieldAcceptedMatchRate" in metrics,
    }


def evaluate_once(
    manifest_path: Path,
    prediction_lock_path: Path,
    ground_truth_lock_path: Path,
    prediction_path: Path,
    ground_truth_path: Path,
    approval_path: Path,
    output_path: Path,
    marker_path: Path,
    *,
    fallback_candidate: bool = False,
    development_gate_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if output_path.exists() or marker_path.exists():
        raise EvaluateOnceError("evaluate-once output or marker already exists")
    lock_report = validate_heldout_lock(
        manifest_path, prediction_lock_path, ground_truth_lock_path
    )
    _approval(approval_path)
    prediction_lock = _read(prediction_lock_path)
    ground_truth_lock = _read(ground_truth_lock_path)
    if _sha256(prediction_path) != prediction_lock.get("predictionSha256"):
        raise EvaluateOnceError("prediction hash does not match DATA-23 lock")
    if _sha256(ground_truth_path) != ground_truth_lock.get("groundTruthSha256"):
        raise EvaluateOnceError("GroundTruth hash does not match DATA-23 lock")

    prediction = _read(prediction_path)
    ground_truth = _read(ground_truth_path)
    if prediction.get("datasetId") != ground_truth.get("dataset", {}).get("datasetId"):
        raise EvaluateOnceError("prediction and GroundTruth dataset IDs differ")
    report = build_aggregate_report(prediction, ground_truth)
    gates = _final_gates(report)
    fallback = {
        "candidate": fallback_candidate,
        "eligible": False,
        "developmentGate": None,
    }
    if fallback_candidate:
        if development_gate_path is None:
            raise EvaluateOnceError("fallback candidate requires --development-gate")
        development_gate = _read(development_gate_path)
        fallback["developmentGate"] = {
            "pathSha256": _sha256(development_gate_path),
            "decision": development_gate.get("decision"),
            "fallback": development_gate.get("fallback"),
        }
        fallback["eligible"] = bool(
            development_gate.get("decision") == "PASS"
            and development_gate.get("fallback", {}).get("status") == "PASS"
            and all(gates.values())
        )
    decision = "PASS" if all(gates.values()) else "HOLD"
    report.update(
        {
            "evaluationKind": "heldout-evaluate-once",
            "decision": decision,
            "promotionAllowed": False,
            "evaluateOnce": {
                "manifestSha256": lock_report["manifestSha256"],
                "predictionSha256": _sha256(prediction_path),
                "groundTruthSha256": _sha256(ground_truth_path),
                "predictionsOpened": False,
                "metricsComputed": True,
            },
            "gates": gates,
            "fallback": fallback,
            "containsRawFieldValues": False,
        }
    )
    marker = {
        "schemaVersion": "data24-heldout-evaluate-once/1.0.0",
        "evaluationKind": "heldout-evaluate-once",
        "decision": decision,
        "reportSha256": None,
        "manifestSha256": lock_report["manifestSha256"],
        "predictionSha256": _sha256(prediction_path),
        "groundTruthSha256": _sha256(ground_truth_path),
        "predictionsOpened": False,
        "evaluateOnceArtifactTouched": True,
        "promotionAllowed": False,
    }
    _write_create_only(output_path, report)
    marker["reportSha256"] = _sha256(output_path)
    _write_create_only(marker_path, marker)
    return report, marker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prediction-lock", type=Path, required=True)
    parser.add_argument("--ground-truth-lock", type=Path, required=True)
    parser.add_argument("--prediction", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    parser.add_argument("--fallback-candidate", action="store_true")
    parser.add_argument("--development-gate", type=Path)
    args = parser.parse_args()
    try:
        report, _ = evaluate_once(
            args.manifest,
            args.prediction_lock,
            args.ground_truth_lock,
            args.prediction,
            args.ground_truth,
            args.approval,
            args.output,
            args.marker,
            fallback_candidate=args.fallback_candidate,
            development_gate_path=args.development_gate,
        )
    except EvaluateOnceError as error:
        raise SystemExit(f"DATA-24 evaluate-once HOLD: {error}") from error
    print(f"DATA-24 evaluate-once {report['decision']}: output created exactly once")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
