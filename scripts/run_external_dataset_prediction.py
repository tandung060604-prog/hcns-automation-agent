#!/usr/bin/env python3
"""Create DATA-12/DATA-13 predictions, then evaluate exactly once."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "ocr_lab" / "api"
for path in (ROOT, API):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from external_dataset_prediction import (  # noqa: E402
    build_aggregate_report,
    build_prediction_artifact,
    resolve_prediction_paths,
)


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _paddle() -> object:
    from paddleocr import PaddleOCR

    return PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
        device="cpu",
        enable_mkldnn=False,
        cpu_threads=4,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path)
    parser.add_argument("--prediction", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--evaluation-marker", type=Path)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--scope-policy", choices=("data12", "data13"), default="data12")
    parser.add_argument("command", choices=("predict", "evaluate"))
    return parser.parse_args()


def main() -> int:
    options = args()
    root = options.dataset_root.expanduser().resolve()
    prediction, report, marker = resolve_prediction_paths(
        root,
        prediction_path=options.prediction,
        report_path=options.report,
        evaluation_marker_path=options.evaluation_marker,
        version=options.scope_policy,
    )
    if options.command == "predict":
        if prediction.exists():
            raise SystemExit("Prediction artifact exists; remove it only with explicit recovery")
        work_root = (
            options.work_root or root.parent / f"{root.name}-{options.scope_policy}-work"
        ).resolve()
        artifact = build_prediction_artifact(
            root,
            options.inventory.expanduser().resolve(),
            work_root,
            ocr_engine=_paddle(),
            scope_policy=options.scope_policy,
        )
        _write(prediction, artifact)
        print(
            f"{options.scope_policy.upper()} prediction artifact ready: "
            f"documents={artifact['documentCount']}"
        )
        return 0
    if report.exists() or marker.exists():
        raise SystemExit("Evaluate-once artifact already exists")
    if not prediction.is_file() or not options.ground_truth:
        raise SystemExit("Prediction artifact and --ground-truth are required for evaluate")
    ground_truth = json.loads(
        options.ground_truth.expanduser().resolve().read_text(encoding="utf-8")
    )
    prediction_payload = json.loads(prediction.read_text(encoding="utf-8"))
    aggregate = build_aggregate_report(prediction_payload, ground_truth)
    _write(report, aggregate)
    _write(
        marker,
        {
            "schemaVersion": f"external-dataset-{options.scope_policy}-evaluate-once/1.0.0",
            "evaluationRan": True,
            "evaluatedAt": aggregate["evaluatedAt"],
            "datasetId": aggregate["datasetId"],
            "predictionSha256": __import__("hashlib").sha256(prediction.read_bytes()).hexdigest(),
            "aggregateReportSha256": __import__("hashlib").sha256(report.read_bytes()).hexdigest(),
            "promotionAllowed": False,
        },
    )
    print(
        f"{options.scope_policy.upper()} aggregate evaluated once: "
        f"field_exact={aggregate['metrics']['fieldExactMatchCount']}"
        f"/{aggregate['fieldCount']} decision={aggregate['decision']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
