#!/usr/bin/env python3
"""Create a non-promotional DATA-25 policy audit from consumed DATA-24 artifacts."""

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

from external_dataset_prediction import MATCHING_POLICY_V2, build_aggregate_report  # noqa: E402


class PolicyAuditError(ValueError):
    """Raised when a frozen DATA-24 artifact cannot be audited safely."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PolicyAuditError(f"Invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise PolicyAuditError(f"{path} must contain an object")
    return value


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _write_create_only(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise PolicyAuditError(f"policy audit artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def audit_policy(
    prediction_path: Path,
    ground_truth_path: Path,
    evaluate_once_report_path: Path,
    evaluate_once_marker_path: Path,
    output_path: Path,
    marker_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rescore frozen artifacts without rerunning prediction or evaluate-once."""

    if output_path.exists() or marker_path.exists():
        raise PolicyAuditError("policy audit output or marker already exists")
    source_marker = _read(evaluate_once_marker_path)
    _read(evaluate_once_report_path)
    if source_marker.get("evaluationKind") != "heldout-evaluate-once":
        raise PolicyAuditError("source marker is not DATA-24 evaluate-once")
    if source_marker.get("evaluateOnceArtifactTouched") is not True:
        raise PolicyAuditError("DATA-24 source was not consumed")
    if source_marker.get("promotionAllowed") is not False:
        raise PolicyAuditError("DATA-24 source must remain non-promotional")
    if _sha256(prediction_path) != source_marker.get("predictionSha256"):
        raise PolicyAuditError("prediction hash does not match DATA-24 marker")
    if _sha256(ground_truth_path) != source_marker.get("groundTruthSha256"):
        raise PolicyAuditError("GroundTruth hash does not match DATA-24 marker")
    if _sha256(evaluate_once_report_path) != source_marker.get("reportSha256"):
        raise PolicyAuditError("DATA-24 report hash does not match marker")

    prediction = _read(prediction_path)
    ground_truth = _read(ground_truth_path)
    report = build_aggregate_report(
        prediction,
        ground_truth,
        policy_version=MATCHING_POLICY_V2,
    )
    report.update(
        {
            "schemaVersion": "external-dataset-policy-v2-audit/1.0.0",
            "evaluationKind": "posthoc-policy-audit",
            "decision": "HOLD",
            "promotionAllowed": False,
            "heldoutConsumed": True,
            "evaluateOnceArtifactTouched": False,
            "sourceEvaluateOnceReportSha256": _sha256(evaluate_once_report_path),
            "sourceEvaluateOnceMarkerSha256": _sha256(evaluate_once_marker_path),
            "containsRawFieldValues": False,
        }
    )
    marker = {
        "schemaVersion": "data25-policy-v2-audit/1.0.0",
        "evaluationKind": "posthoc-policy-audit",
        "decision": "HOLD",
        "reportSha256": None,
        "sourceEvaluateOnceReportSha256": _sha256(evaluate_once_report_path),
        "sourceEvaluateOnceMarkerSha256": _sha256(evaluate_once_marker_path),
        "predictionSha256": _sha256(prediction_path),
        "groundTruthSha256": _sha256(ground_truth_path),
        "heldoutConsumed": True,
        "evaluateOnceArtifactTouched": False,
        "promotionAllowed": False,
        "containsRawFieldValues": False,
    }
    _write_create_only(output_path, report)
    marker["reportSha256"] = _sha256(output_path)
    _write_create_only(marker_path, marker)
    return report, marker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prediction", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--evaluate-once-report", type=Path, required=True)
    parser.add_argument("--evaluate-once-marker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    args = parser.parse_args()
    try:
        report, _ = audit_policy(
            args.prediction,
            args.ground_truth,
            args.evaluate_once_report,
            args.evaluate_once_marker,
            args.output,
            args.marker,
        )
    except PolicyAuditError as error:
        raise SystemExit(f"DATA-25 policy audit HOLD: {error}") from error
    metrics = report["metrics"]
    print(
        "DATA-25 posthoc policy audit HOLD: "
        f"canonical={metrics['fieldExactMatchCount']}/{report['fieldCount']} "
        f"accepted={metrics['fieldAcceptedMatchCount']}/{report['fieldCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
