"""Benchmark DATA-31 IELTS crop accuracy and stage timings across EasyOCR profiles.

Aggregate-only diagnostics for IELTS cases in DATA-31.
The report never contains source paths, filenames, OCR text, field values,
case IDs, document UUIDs, or private Ground Truth.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "src", ROOT / "apps" / "ocr_lab" / "api"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from external_dataset_prediction import (  # noqa: E402
    FIELD_SPECS,
    MATCHING_POLICY_V2,
    _field_match,
    _norm,
)

from hcns_agent.adapters.external_dataset import count_source_format_and_pages  # noqa: E402
from hcns_agent.application.external_dataset import (  # noqa: E402
    read_inventory,
    validate_inventory,
)
from hcns_agent.ports.document_parser import DocumentSource  # noqa: E402
from hcns_agent.templates.service import (  # noqa: E402
    build_local_template_processing_service,
)
from hcns_agent.templates.structured_hr import (  # noqa: E402
    STRUCTURED_HR_PARSER_ID,
    STRUCTURED_HR_PARSER_VERSION,
)
from scripts.benchmark_template_stages import (  # noqa: E402
    _elapsed_ms,
    _failure_code,
    _MemoryProbe,
    _package_version,
    _require_private_path,
    _summarize_memory,
    _timings,
    percentile,
)
from scripts.run_data31_schema_replay import (  # noqa: E402
    MEDIA_TYPES,
    build_data31_coverage_scope,
)

REPORT_SCHEMA_VERSION = "data31-ielts-crop-benchmark/1.0.0"

PROFILE_CONFIGS: dict[str, dict[str, Any]] = {
    "baseline": {
        "canvasSize": 1280,
        "magRatio": 1.3,
        "preprocessProfile": "none",
    },
    "hires": {
        "canvasSize": 2560,
        "magRatio": 1.3,
        "preprocessProfile": "none",
    },
    "hires-autocontrast": {
        "canvasSize": 2560,
        "magRatio": 1.3,
        "preprocessProfile": "content-roi-autocontrast-v1",
    },
}

_PROCESSING_STAGES = ("intake", "ocr", "template", "total")


def _summarize_processing(records: Sequence[Mapping[str, float]]) -> dict[str, object]:
    return {
        stage: {
            "p50": percentile([record[stage] for record in records], 0.50),
            "p95": percentile([record[stage] for record in records], 0.95),
        }
        for stage in _PROCESSING_STAGES
    }


def parse_args(args: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--coverage-decision", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profile",
        choices=("baseline", "hires", "hires-autocontrast", "all"),
        default="baseline",
    )
    parser.add_argument("--warm-runs", type=int, default=30)
    parser.add_argument("--authorization-confirmed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--device", default="cpu")
    return parser.parse_args(args)


def validate_cli_args(args: argparse.Namespace) -> None:
    if not args.authorization_confirmed:
        raise SystemExit("Benchmark rejected: pass --authorization-confirmed")
    if args.warm_runs < 30:
        raise SystemExit("Benchmark rejected: --warm-runs must be at least 30")

    root = args.dataset_root.expanduser().resolve(strict=True)
    inventory_path = args.inventory.expanduser().resolve(strict=True)
    ground_truth_path = args.ground_truth.expanduser().resolve(strict=True)
    output = args.output.expanduser().resolve()

    if output.exists() and not args.overwrite:
        raise SystemExit(f"Benchmark report exists; pass --overwrite: {output.name}")

    _require_private_path(root)
    _require_private_path(inventory_path)
    _require_private_path(ground_truth_path)
    _require_private_path(output)

    if args.coverage_decision is not None:
        cov_path = args.coverage_decision.expanduser().resolve(strict=True)
        _require_private_path(cov_path)


def calculate_ielts_aggregate_metrics(
    predictions: Sequence[Mapping[str, Any]],
    ground_truth: Mapping[str, Any],
    *,
    field_scope: Mapping[str, tuple[str, ...]] | None = None,
    policy_version: str = MATCHING_POLICY_V2,
) -> dict[str, Any]:
    truth_cases = {str(item["caseId"]): item for item in ground_truth.get("cases", [])}
    ielts_fields = FIELD_SPECS["ielts"]

    stats: dict[str, dict[str, int]] = {
        name: {
            "evaluatedCount": 0,
            "exactMatchCount": 0,
            "acceptedMatchCount": 0,
            "presenceCount": 0,
        }
        for name in ielts_fields
    }

    total_evaluated = 0
    total_exact = 0
    total_accepted = 0
    total_present = 0

    for doc in predictions:
        case_id = str(doc["caseId"])
        truth_case = truth_cases.get(case_id)
        if truth_case is None:
            continue
        truth_fields = {
            str(item["name"]): item.get("value")
            for item in truth_case.get("fields", [])
        }
        doc_fields = doc.get("fields", {})

        active_fields = (
            field_scope.get(case_id, ielts_fields)
            if field_scope is not None
            else ielts_fields
        )

        for name in active_fields:
            if name not in ielts_fields:
                continue
            truth_val = truth_fields.get(name)
            pred_field = doc_fields.get(name)
            pred_val = pred_field.get("value") if isinstance(pred_field, Mapping) else None

            match = _field_match(
                "ielts",
                name,
                truth_val,
                pred_val,
                policy_version=policy_version,
            )
            is_exact = bool(match.get("exact"))
            is_accepted = bool(match.get("match"))
            is_present = bool(_norm(pred_val))

            stats[name]["evaluatedCount"] += 1
            stats[name]["exactMatchCount"] += int(is_exact)
            stats[name]["acceptedMatchCount"] += int(is_accepted)
            stats[name]["presenceCount"] += int(is_present)

            total_evaluated += 1
            total_exact += int(is_exact)
            total_accepted += int(is_accepted)
            total_present += int(is_present)

    by_field = {
        name: {
            "evaluatedCount": data["evaluatedCount"],
            "exactMatchCount": data["exactMatchCount"],
            "exactMatchRate": round(
                data["exactMatchCount"] / max(1, data["evaluatedCount"]), 6
            ),
            "acceptedMatchCount": data["acceptedMatchCount"],
            "acceptedMatchRate": round(
                data["acceptedMatchCount"] / max(1, data["evaluatedCount"]), 6
            ),
            "presenceCount": data["presenceCount"],
            "presenceRate": round(data["presenceCount"] / max(1, data["evaluatedCount"]), 6),
        }
        for name, data in stats.items()
    }

    return {
        "evaluatedFieldCount": total_evaluated,
        "fieldExactMatchCount": total_exact,
        "fieldExactMatchRate": round(total_exact / max(1, total_evaluated), 6),
        "fieldAcceptedMatchCount": total_accepted,
        "fieldAcceptedMatchRate": round(total_accepted / max(1, total_evaluated), 6),
        "fieldPresenceCount": total_present,
        "fieldPresenceRate": round(total_present / max(1, total_evaluated), 6),
        "byField": by_field,
    }


def run_ielts_benchmark_for_profile(
    profile_name: str,
    config: Mapping[str, Any],
    dataset_root: Path,
    ielts_cases: Sequence[Mapping[str, Any]],
    evaluation_ground_truth: Mapping[str, Any],
    *,
    field_scope: Mapping[str, tuple[str, ...]] | None = None,
    warm_runs: int = 30,
    device: str = "cpu",
) -> dict[str, Any]:
    service = build_local_template_processing_service(
        device=device,
        ocr_backend="easyocr",
        easyocr_canvas_size=int(config["canvasSize"]),
        easyocr_mag_ratio=float(config["magRatio"]),
        easyocr_preprocess_profile=str(config["preprocessProfile"]),
    )

    cold_timings: list[dict[str, float]] = []
    cold_memory_records: list[dict[str, int | None]] = []
    predictions: list[dict[str, Any]] = []
    failures: dict[str, int] = {}

    # Cold pass
    for case in ielts_cases:
        source_path = (dataset_root / Path(str(case["sourceRelativePath"]))).resolve(strict=True)
        content = source_path.read_bytes()
        media_type = MEDIA_TYPES.get(source_path.suffix.casefold(), "application/pdf")
        doc_source = DocumentSource(
            document_id=f"ielts-bench-{case['caseId']}",
            filename=source_path.name,
            content=content,
            declared_media_type=media_type,
            source_reference=str(case["caseId"]),
        )
        try:
            with _MemoryProbe() as probe:
                started = time.perf_counter()
                result = service.process(doc_source)
                total_duration = _elapsed_ms(started)
            cold_memory_records.append(probe.result())
            stage_timings = _timings(result.processing)
            stage_timings["total"] = total_duration
            cold_timings.append(stage_timings)

            public_result = result.public_dict()
            fields = {
                name: {"value": public_result["data"].get(name)}
                for name in FIELD_SPECS["ielts"]
            }
            predictions.append(
                {
                    "caseId": case["caseId"],
                    "category": "ielts",
                    "fields": fields,
                }
            )
        except Exception as error:  # noqa: BLE001
            code = _failure_code(error)
            failures[code] = failures.get(code, 0) + 1

    # Warm runs
    warm_timings: list[dict[str, float]] = []
    warm_memory_records: list[dict[str, int | None]] = []

    # Ponytail: warm runs use one real, deterministic member of the IELTS
    # input class. Reprocessing all four PDFs 30 times measures a batch, not
    # the requested per-class warm distribution, and multiplies OCR cost.
    warm_case = sorted(ielts_cases, key=lambda case: str(case["caseId"]))[0]
    source_path = (dataset_root / Path(str(warm_case["sourceRelativePath"]))).resolve(
        strict=True
    )
    content = source_path.read_bytes()
    media_type = MEDIA_TYPES.get(source_path.suffix.casefold(), "application/pdf")
    for run_idx in range(warm_runs):
        doc_source = DocumentSource(
            document_id=f"ielts-bench-warm-{run_idx}",
            filename=source_path.name,
            content=content,
            declared_media_type=media_type,
            source_reference="ielts-warm-representative",
        )
        try:
            with _MemoryProbe() as probe:
                started = time.perf_counter()
                result = service.process(doc_source)
                total_duration = _elapsed_ms(started)
            warm_memory_records.append(probe.result())
            stage_timings = _timings(result.processing)
            stage_timings["total"] = total_duration
            warm_timings.append(stage_timings)
        except Exception as error:  # noqa: BLE001
            code = _failure_code(error)
            failures[code] = failures.get(code, 0) + 1

    accuracy = calculate_ielts_aggregate_metrics(
        predictions,
        evaluation_ground_truth,
        field_scope=field_scope,
        policy_version=MATCHING_POLICY_V2,
    )

    return {
        "config": dict(config),
        "accuracy": accuracy,
        "performance": {
            "coldMs": _summarize_processing(cold_timings) if cold_timings else {},
            "warmMs": _summarize_processing(warm_timings) if warm_timings else {},
            "successfulWarmRuns": len(warm_timings),
            "requestedWarmRuns": warm_runs,
            "warmInputClass": "ielts",
            "warmRepresentativeCount": 1,
        },
        "memory": {
            "cold": _summarize_memory(cold_memory_records) if cold_memory_records else {},
            "warm": _summarize_memory(warm_memory_records) if warm_memory_records else {},
        },
        "failureCodeCounts": dict(sorted(failures.items())),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    validate_cli_args(args)

    dataset_root = args.dataset_root.expanduser().resolve(strict=True)
    inventory_path = args.inventory.expanduser().resolve(strict=True)
    ground_truth_path = args.ground_truth.expanduser().resolve(strict=True)
    output = args.output.expanduser().resolve()

    inventory = read_inventory(inventory_path)
    validate_inventory(
        dataset_root,
        inventory,
        page_counter=count_source_format_and_pages,
    )

    if inventory["dataset"]["datasetId"] != "DATA-31":
        raise SystemExit(
            "This benchmark runner only accepts DATA-31, got "
            f"{inventory['dataset']['datasetId']}"
        )

    ielts_cases = [c for c in inventory["cases"] if c.get("category") == "ielts"]
    if len(ielts_cases) != 4:
        raise SystemExit(f"Expected 4 IELTS cases in DATA-31, found {len(ielts_cases)}")

    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    coverage_decision = None
    if args.coverage_decision is not None:
        coverage_decision = json.loads(args.coverage_decision.read_text(encoding="utf-8"))

    evaluation_ground_truth, field_scope, _coverage = build_data31_coverage_scope(
        inventory,
        ground_truth,
        coverage_decision,
    )

    target_profiles = (
        ("baseline", "hires", "hires-autocontrast")
        if args.profile == "all"
        else (args.profile,)
    )

    profile_results: dict[str, Any] = {}
    for profile_name in target_profiles:
        cfg = PROFILE_CONFIGS[profile_name]
        profile_results[profile_name] = run_ielts_benchmark_for_profile(
            profile_name=profile_name,
            config=cfg,
            dataset_root=dataset_root,
            ielts_cases=ielts_cases,
            evaluation_ground_truth=evaluation_ground_truth,
            field_scope=field_scope,
            warm_runs=args.warm_runs,
            device=args.device,
        )

    report = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "id": inventory["dataset"]["datasetId"],
            "contentDigest": inventory["dataset"]["contentDigest"],
            "documentCount": len(ielts_cases),
            "category": "ielts",
        },
        "runtime": {
            "parserId": STRUCTURED_HR_PARSER_ID,
            "parserVersion": STRUCTURED_HR_PARSER_VERSION,
            "ocrBackend": "easyocr",
            "easyocrVersion": _package_version("easyocr"),
            "python": platform.python_version(),
            "machine": platform.machine(),
        },
        "activeProfiles": list(target_profiles),
        "profiles": profile_results,
        "matchingPolicy": {
            "version": MATCHING_POLICY_V2,
        },
        "privacy": {
            "aggregateOnly": True,
            "containsRawFieldValues": False,
            "containsRawOcrText": False,
            "containsSourcePaths": False,
            "containsCaseIds": False,
            "containsFilenames": False,
            "containsProcessIds": False,
            "containsPrivateGroundTruth": False,
            "groundTruthUsedForScoringOnly": True,
            "promotionAllowed": False,
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    all_warm_complete = all(
        res["performance"]["successfulWarmRuns"] == args.warm_runs
        for res in profile_results.values()
    )
    no_failures = all(not res["failureCodeCounts"] for res in profile_results.values())
    complete = all_warm_complete and no_failures
    print(
        f"DATA-31 IELTS crop benchmark complete={complete} profiles={list(target_profiles)}",
        flush=True,
    )
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
