"""Benchmark Template-first stages with authorized local documents.

The aggregate report never contains source paths, filenames, OCR text, field
values, document UUIDs, or Camunda process IDs. Per-run artifacts stay under the
explicit private work root and must never be committed.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from hcns_agent.adapters.external_dataset import count_source_format_and_pages
from hcns_agent.application.ocr_metrics import percentile
from hcns_agent.domain.documents import SourceFormat
from hcns_agent.ports.document_parser import DocumentSource
from hcns_agent.templates.service import (
    STAGE_TIMING_SCHEMA_VERSION,
    TemplateProcessingService,
    build_local_template_processing_service,
)

TIMING_SCHEMA_VERSION = STAGE_TIMING_SCHEMA_VERSION
INPUT_CLASSES = (
    SourceFormat.DOCX,
    SourceFormat.PDF_TEXT,
    SourceFormat.PDF_SCAN,
    SourceFormat.IMAGE,
)
STAGES = ("intake", "ocr", "template", "persistence", "total")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-id", default="DATA-29")
    parser.add_argument("--warm-runs", type=int, default=30)
    parser.add_argument(
        "--input-class",
        action="append",
        choices=tuple(item.value for item in INPUT_CLASSES),
        dest="input_classes",
    )
    parser.add_argument("--ocr-backend", choices=("easyocr", "paddle"), default="easyocr")
    parser.add_argument("--authorization-confirmed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dashboard-url")
    parser.add_argument("--camunda-session-id")
    parser.add_argument("--camunda-warm-runs", type=int, default=0)
    parser.add_argument("--allow-local-shadow-processes", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.authorization_confirmed:
        raise SystemExit("Benchmark rejected: pass --authorization-confirmed")
    if args.warm_runs < 30:
        raise SystemExit("Benchmark rejected: --warm-runs must be at least 30")
    root = args.dataset_root.resolve(strict=True)
    work_root = args.work_root.resolve()
    output = args.output.resolve()
    _require_private_path(root)
    _require_private_path(work_root)
    _require_private_path(output)
    if output.exists() and not (args.overwrite or args.resume):
        raise SystemExit("Benchmark report exists; pass --overwrite")
    work_root.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    input_classes = (
        tuple(SourceFormat(item) for item in args.input_classes)
        if args.input_classes
        else INPUT_CLASSES
    )
    selected = _select_inputs(root, input_classes)
    class_reports: dict[str, object] = {}
    failures: dict[str, int] = {}
    for source_format in input_classes:
        source_path = selected[source_format]
        content = source_path.read_bytes()
        service = build_local_template_processing_service(ocr_backend=args.ocr_backend)
        cold_root = work_root / source_format.value / "cold"
        cold = _load_record(cold_root) if args.resume else None
        service_is_warm = False
        try:
            if cold is None:
                cold = _run_once(service, source_path.suffix, content, cold_root)
                service_is_warm = True
        except Exception as error:  # noqa: BLE001 - aggregate failure without raw data
            code = _failure_code(error)
            failures[code] = failures.get(code, 0) + 1
            class_reports[source_format.value] = {
                "status": "FAILED_COLD",
                "cold": None,
                "warm": _summarize(()),
                "successfulWarmRuns": 0,
                "requestedWarmRuns": args.warm_runs,
                "failureCode": code,
            }
            continue
        warm: list[dict[str, float]] = []
        for run_index in range(args.warm_runs):
            run_root = (
                work_root
                / source_format.value
                / "warm"
                / f"run-{run_index + 1:03d}"
            )
            existing = _load_record(run_root) if args.resume else None
            if existing is not None:
                warm.append(existing)
                continue
            try:
                if not service_is_warm:
                    _prime_service(service, source_path.suffix, content)
                    service_is_warm = True
                warm.append(
                    _run_once(
                        service,
                        source_path.suffix,
                        content,
                        run_root,
                    )
                )
            except Exception as error:  # noqa: BLE001 - report safe aggregate and continue
                code = _failure_code(error)
                failures[code] = failures.get(code, 0) + 1
            if (run_index + 1) % 5 == 0 or run_index + 1 == args.warm_runs:
                print(f"{source_format.value}: warm {run_index + 1}/{args.warm_runs}", flush=True)
        class_reports[source_format.value] = {
            "status": "COMPLETE" if len(warm) == args.warm_runs else "INCOMPLETE",
            "cold": cold,
            "warm": _summarize(warm),
            "successfulWarmRuns": len(warm),
            "requestedWarmRuns": args.warm_runs,
        }

    camunda = _camunda_report(args, work_root)
    report = {
        "schemaVersion": TIMING_SCHEMA_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "id": args.dataset_id,
            "authorizedLocalDocuments": True,
            "selectedDocumentCount": len(input_classes),
            "groundTruthRead": False,
        },
        "runtime": {
            "profile": "template-first",
            "ocrBackend": args.ocr_backend,
            "python": platform.python_version(),
            "machine": platform.machine(),
            "easyocrVersion": _package_version("easyocr"),
        },
        "policy": {
            "aggregateOnly": True,
            "containsRawFieldValues": False,
            "containsRawOcrText": False,
            "containsSourcePaths": False,
            "containsDocumentOrProcessIds": False,
            "promotionAllowed": False,
        },
        "measurement": {
            "coldRunsPerInputClass": 1,
            "warmRunsPerInputClass": args.warm_runs,
            "coldDefinition": "first measured call on a new service; lazy model load included",
            "warmDefinition": (
                "measured call after the backend is initialized in the same process; "
                "resume primes a new process before measuring remaining runs"
            ),
            "inputClasses": [item.value for item in input_classes],
            "stageDefinitions": {
                "intake": (
                    "format detection, safety, native parse or scan rasterization; "
                    "excludes OCR"
                ),
                "ocr": "recognizer call including lazy model initialization on cold runs",
                "template": "template detection, field parser, validation and Camunda projection",
                "persistence": "private source and result serialization/write",
                "total": "Template-first service plus private persistence",
                "camunda": "dashboard handoff through process start and Submit completion",
            },
        },
        "inputClassResults": class_reports,
        "camunda": camunda,
        "failureCodeCounts": dict(sorted(failures.items())),
    }
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    complete = not failures and all(
        cast(dict[str, object], value).get("successfulWarmRuns") == args.warm_runs
        for value in class_reports.values()
    )
    print(f"Aggregate-only report written: classes={len(input_classes)} complete={complete}")
    return 0 if complete else 1


def _select_inputs(
    root: Path,
    input_classes: Sequence[SourceFormat] = INPUT_CLASSES,
) -> dict[SourceFormat, Path]:
    selected: dict[SourceFormat, Path] = {}
    suffixes = {".docx", ".pdf", ".png", ".jpg", ".jpeg"}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or path.suffix.casefold() not in suffixes:
            continue
        source_format, _ = count_source_format_and_pages(path, path.read_bytes())
        if source_format in input_classes:
            selected.setdefault(source_format, path)
        if len(selected) == len(set(input_classes)):
            break
    missing = [item.value for item in input_classes if item not in selected]
    if missing:
        raise SystemExit(f"Dataset is missing required input classes: {', '.join(missing)}")
    return selected


def _run_once(
    service: TemplateProcessingService,
    suffix: str,
    content: bytes,
    run_root: Path,
) -> dict[str, float]:
    document_id = str(uuid.uuid4())
    total_started = time.perf_counter()
    result = service.process(
        DocumentSource(
            document_id=document_id,
            filename=f"document{suffix.casefold()}",
            content=content,
            source_reference=document_id,
        ),
        result_reference=f"performance/{document_id}/result.json",
    )
    payload = result.public_dict()
    timings = _timings(result.processing)
    persistence_started = time.perf_counter()
    (run_root / "input").mkdir(parents=True, exist_ok=False)
    (run_root / "input" / f"document{suffix.casefold()}").write_bytes(content)
    (run_root / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    persistence = _elapsed_ms(persistence_started)
    record = {
        "intake": timings["intake"],
        "ocr": timings["ocr"],
        "template": timings["template"],
        "persistence": persistence,
        "total": _elapsed_ms(total_started),
    }
    (run_root / "performance.json").write_text(
        json.dumps(
            {"schemaVersion": TIMING_SCHEMA_VERSION, "timingsMs": record},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return record


def _prime_service(
    service: TemplateProcessingService,
    suffix: str,
    content: bytes,
) -> None:
    document_id = str(uuid.uuid4())
    service.process(
        DocumentSource(
            document_id=document_id,
            filename=f"document{suffix.casefold()}",
            content=content,
            source_reference=document_id,
        ),
        result_reference=f"performance/{document_id}/result.json",
    )


def _load_record(run_root: Path) -> dict[str, float] | None:
    path = run_root / "performance.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("Stored benchmark timing is unreadable") from error
    if payload.get("schemaVersion") != TIMING_SCHEMA_VERSION:
        raise SystemExit("Stored benchmark timing uses another schema")
    timings = payload.get("timingsMs")
    if not isinstance(timings, Mapping):
        raise SystemExit("Stored benchmark timing is invalid")
    record: dict[str, float] = {}
    for stage in STAGES:
        value = timings.get(stage)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SystemExit("Stored benchmark timing is invalid")
        record[stage] = round(max(0.0, float(value)), 3)
    return record


def _timings(value: object) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise RuntimeError("Template processing metadata is unavailable")
    raw = value.get("timingsMs")
    if not isinstance(raw, Mapping):
        raise RuntimeError("Template stage timings are unavailable")
    result: dict[str, float] = {}
    for name in ("intake", "ocr", "template"):
        stage_value = raw.get(name)
        if isinstance(stage_value, bool) or not isinstance(stage_value, (int, float)):
            raise RuntimeError("Template stage timing is invalid")
        result[name] = round(max(0.0, float(stage_value)), 3)
    return result


def _summarize(records: Sequence[Mapping[str, float]]) -> dict[str, object]:
    return {
        stage: {
            "p50": percentile([record[stage] for record in records], 0.50),
            "p95": percentile([record[stage] for record in records], 0.95),
        }
        for stage in STAGES
    }


def _camunda_report(args: argparse.Namespace, work_root: Path) -> dict[str, object]:
    requested = int(args.camunda_warm_runs)
    if requested == 0:
        return {"status": "NOT_MEASURED", "reason": "no local shadow run requested"}
    if requested < 30:
        raise SystemExit("Camunda benchmark rejected: use at least 30 warm runs")
    if not (
        args.allow_local_shadow_processes
        and args.dashboard_url
        and args.camunda_session_id
    ):
        raise SystemExit(
            "Camunda benchmark requires dashboard URL, session UUID and "
            "--allow-local-shadow-processes"
        )
    uuid.UUID(args.camunda_session_id)
    dashboard_url = str(args.dashboard_url).rstrip("/")
    if urlsplit(dashboard_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Camunda benchmark accepts only a loopback dashboard URL")
    endpoint = f"{dashboard_url}/api/camunda/start"
    samples: list[float] = []
    cold_duration = 0.0
    process_ids: list[str] = []
    for run_index in range(requested + 1):
        body = json.dumps({"documentId": args.camunda_session_id}).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:  # nosec B310: explicit local URL
            payload = json.loads(response.read().decode("utf-8"))
        performance = payload.get("performance", {})
        timings = performance.get("timingsMs", {})
        duration = timings.get("camunda")
        process_id = payload.get("processInstanceId")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            raise RuntimeError("Camunda timing metadata is unavailable")
        if not isinstance(process_id, str):
            raise RuntimeError("Camunda process id is unavailable")
        process_ids.append(process_id)
        if run_index:
            samples.append(float(duration))
        else:
            cold_duration = float(duration)
        progress = "cold" if run_index == 0 else f"warm {run_index}/{requested}"
        print(f"Camunda: {progress}", flush=True)
    (work_root / "camunda-process-ids.json").write_text(
        json.dumps({"processInstanceIds": process_ids}, indent=2),
        encoding="utf-8",
    )
    return {
        "status": "MEASURED_LOCAL_SHADOW",
        "cold": {"camunda": round(cold_duration, 3)},
        "warm": {
            "camunda": {
                "p50": percentile(samples, 0.50),
                "p95": percentile(samples, 0.95),
            }
        },
        "createdProcessCount": len(process_ids),
        "processIdsStoredInPrivateWorkRoot": True,
    }


def _require_private_path(path: Path) -> None:
    if any((candidate / ".git").exists() for candidate in (path, *path.parents)):
        raise SystemExit("Benchmark work and report paths must stay outside Git")


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _package_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _failure_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    value = getattr(code, "value", code)
    if isinstance(value, str) and value and value.replace("_", "").isalnum():
        return value.upper()
    return type(error).__name__.upper()


if __name__ == "__main__":
    raise SystemExit(main())
