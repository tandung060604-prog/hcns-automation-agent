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
import subprocess
import sys
import threading
import time
import tracemalloc
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
MEMORY_METRICS = ("peakPythonMemoryBytes", "peakRssBytes")


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
    parser.add_argument("--pdf-dpi", type=int, default=150)
    parser.add_argument("--easyocr-canvas-size", type=int, default=1280)
    parser.add_argument("--easyocr-mag-ratio", type=float, default=1.3)
    parser.add_argument(
        "--easyocr-preprocess-profile",
        choices=("none", "content-roi-autocontrast-v1"),
        default="none",
    )
    parser.add_argument("--authorization-confirmed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dashboard-url")
    parser.add_argument("--camunda-session-id")
    parser.add_argument("--camunda-warm-runs", type=int, default=0)
    parser.add_argument("--allow-local-shadow-processes", action="store_true")
    parser.add_argument(
        "--isolate-pdf-scan-runs",
        action="store_true",
        help="Run each PDF scan sample in a fresh child process to bound OCR memory.",
    )
    parser.add_argument("--single-run-source", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--single-run-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--single-run-count", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--prime-single-run", action="store_true", help=argparse.SUPPRESS)
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

    if args.single_run_source is not None:
        return _run_single_sample(args)

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
        if source_format is SourceFormat.PDF_SCAN and args.isolate_pdf_scan_runs:
            report, isolated_failures = _run_isolated_pdf_scan(
                source_path=source_path,
                dataset_root=root,
                work_root=work_root,
                args=args,
            )
            class_reports[source_format.value] = report
            for code, count in isolated_failures.items():
                failures[code] = failures.get(code, 0) + count
            continue
        content = source_path.read_bytes()
        service = build_local_template_processing_service(
            ocr_backend=args.ocr_backend,
            pdf_dpi=args.pdf_dpi,
            easyocr_canvas_size=args.easyocr_canvas_size,
            easyocr_mag_ratio=args.easyocr_mag_ratio,
            easyocr_preprocess_profile=args.easyocr_preprocess_profile,
        )
        cold_root = work_root / source_format.value / "cold"
        cold = _load_record(cold_root) if args.resume else None
        cold_memory = _load_memory_record(cold_root) if args.resume else None
        service_is_warm = False
        try:
            if cold is None:
                cold, cold_memory = _run_once(
                    service,
                    source_path.suffix,
                    content,
                    cold_root,
                )
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
        warm_memory: list[dict[str, int | None]] = []
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
                existing_memory = _load_memory_record(run_root)
                if existing_memory is not None:
                    warm_memory.append(existing_memory)
                continue
            try:
                if not service_is_warm:
                    _prime_service(service, source_path.suffix, content)
                    service_is_warm = True
                stage_record, memory_record = _run_once(
                    service,
                    source_path.suffix,
                    content,
                    run_root,
                )
                warm.append(stage_record)
                warm_memory.append(memory_record)
            except Exception as error:  # noqa: BLE001 - report safe aggregate and continue
                code = _failure_code(error)
                failures[code] = failures.get(code, 0) + 1
            if (run_index + 1) % 5 == 0 or run_index + 1 == args.warm_runs:
                print(f"{source_format.value}: warm {run_index + 1}/{args.warm_runs}", flush=True)
        class_reports[source_format.value] = {
            "status": "COMPLETE" if len(warm) == args.warm_runs else "INCOMPLETE",
            "cold": cold,
            "warm": _summarize(warm),
            "memory": {
                "cold": cold_memory,
                "warm": _summarize_memory(warm_memory),
                "measurement": (
                    "tracemalloc peak Python heap; sampled process RSS peak when "
                    "psutil is available"
                ),
            },
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
            "pdfDpi": args.pdf_dpi,
            "easyocrCanvasSize": args.easyocr_canvas_size,
            "easyocrMagRatio": args.easyocr_mag_ratio,
            "easyocrPreprocessProfile": args.easyocr_preprocess_profile,
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
                if not args.isolate_pdf_scan_runs
                else "measured call after a private child primes EasyOCR; each PDF scan "
                "sample runs in a fresh process to bound model memory"
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


def _run_isolated_pdf_scan(
    *,
    source_path: Path,
    dataset_root: Path,
    work_root: Path,
    args: argparse.Namespace,
) -> tuple[dict[str, object], dict[str, int]]:
    cold: dict[str, float] | None = None
    cold_memory: dict[str, int | None] | None = None
    warm: list[dict[str, float]] = []
    warm_memory: list[dict[str, int | None]] = []
    failures: dict[str, int] = {}
    cold_records, cold_failures = _run_single_child(
        source_path=source_path,
        dataset_root=dataset_root,
        run_root=work_root / SourceFormat.PDF_SCAN.value / "cold",
        args=args,
        count=1,
        prime=False,
    )
    for code, count in cold_failures.items():
        failures[code] = failures.get(code, 0) + count
    if cold_records:
        cold, cold_memory = cold_records[0]
    print("PDF_SCAN isolated cold", flush=True)

    batch_size = 5
    for batch_index, start in enumerate(range(0, args.warm_runs, batch_size), start=1):
        count = min(batch_size, args.warm_runs - start)
        batch_records, batch_failures = _run_single_child(
            source_path=source_path,
            dataset_root=dataset_root,
            run_root=(
                work_root
                / SourceFormat.PDF_SCAN.value
                / "warm"
                / f"batch-{batch_index:03d}"
            ),
            args=args,
            count=count,
            prime=True,
        )
        for code, count in batch_failures.items():
            failures[code] = failures.get(code, 0) + count
        for stage_record, memory_record in batch_records:
            warm.append(stage_record)
            warm_memory.append(memory_record)
        print(
            f"PDF_SCAN isolated warm {len(warm)}/{args.warm_runs}",
            flush=True,
        )

    complete = cold is not None and len(warm) == args.warm_runs
    return (
        {
            "status": "COMPLETE" if complete else "INCOMPLETE",
            "cold": cold,
            "warm": _summarize(warm),
            "memory": {
                "cold": cold_memory,
                "warm": _summarize_memory(warm_memory),
                "measurement": (
                    "tracemalloc peak Python heap; sampled process RSS peak when "
                    "psutil is available"
                ),
            },
            "isolation": (
                "fresh child process per batch of at most five PDF scan samples; "
                "each child loads EasyOCR before measuring samples"
            ),
            "successfulWarmRuns": len(warm),
            "requestedWarmRuns": args.warm_runs,
        },
        failures,
    )


def _run_single_child(
    *,
    source_path: Path,
    dataset_root: Path,
    run_root: Path,
    args: argparse.Namespace,
    count: int,
    prime: bool,
) -> tuple[list[tuple[dict[str, float], dict[str, int | None]]], dict[str, int]]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--dataset-root",
        str(dataset_root),
        "--work-root",
        str(run_root.parent),
        "--output",
        str(run_root.parent / "worker-report.json"),
        "--dataset-id",
        str(args.dataset_id),
        "--warm-runs",
        str(args.warm_runs),
        "--ocr-backend",
        str(args.ocr_backend),
        "--pdf-dpi",
        str(args.pdf_dpi),
        "--easyocr-canvas-size",
        str(args.easyocr_canvas_size),
        "--easyocr-mag-ratio",
        str(args.easyocr_mag_ratio),
        "--easyocr-preprocess-profile",
        str(args.easyocr_preprocess_profile),
        "--authorization-confirmed",
        "--overwrite",
        "--single-run-source",
        str(source_path),
        "--single-run-root",
        str(run_root),
        "--single-run-count",
        str(count),
    ]
    if prime:
        command.append("--prime-single-run")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [], {"ISOLATED_RUN_FAILED": count}
    if completed.returncode != 0:
        failure_paths = [run_root / "failure.json", *run_root.glob("run-*/failure.json")]
        for failure_path in failure_paths:
            if failure_path.is_file():
                try:
                    failure = json.loads(failure_path.read_text(encoding="utf-8"))
                    code = failure.get("failureCode")
                    if isinstance(code, str) and code:
                        return [], {code: count}
                except (OSError, json.JSONDecodeError):
                    pass
        return [], {"ISOLATED_RUN_FAILED": count}
    records: list[tuple[dict[str, float], dict[str, int | None]]] = []
    roots = (
        [run_root]
        if count == 1
        else [
            run_root / f"run-{index:03d}"
            for index in range(1, count + 1)
        ]
    )
    for sample_root in roots:
        stage_record = _load_record(sample_root)
        memory_record = _load_memory_record(sample_root)
        if stage_record is None or memory_record is None:
            return records, {"ISOLATED_RUN_INCOMPLETE": count - len(records)}
        records.append((stage_record, memory_record))
    return records, {}


def _run_single_sample(args: argparse.Namespace) -> int:
    if args.single_run_root is None:
        raise SystemExit("Single-run benchmark requires --single-run-root")
    source = args.single_run_source.resolve(strict=True)
    run_root = args.single_run_root.resolve()
    _require_private_path(source)
    _require_private_path(run_root)
    count = int(args.single_run_count)
    if count <= 0:
        raise SystemExit("Single-run benchmark count must be positive")
    if run_root.exists():
        raise SystemExit("Single-run benchmark root already exists")
    content = source.read_bytes()
    service = build_local_template_processing_service(
        ocr_backend=args.ocr_backend,
        pdf_dpi=args.pdf_dpi,
        easyocr_canvas_size=args.easyocr_canvas_size,
        easyocr_mag_ratio=args.easyocr_mag_ratio,
        easyocr_preprocess_profile=args.easyocr_preprocess_profile,
    )
    try:
        if args.prime_single_run:
            _prime_service(service, source.suffix, content)
        for index in range(count):
            sample_root = (
                run_root
                if count == 1
                else run_root / f"run-{index + 1:03d}"
            )
            _run_once(service, source.suffix, content, sample_root)
    except Exception as error:  # noqa: BLE001 - safe child failure artifact
        failure_root = sample_root if "sample_root" in locals() else run_root
        failure_root.mkdir(parents=True, exist_ok=True)
        (failure_root / "failure.json").write_text(
            json.dumps({"failureCode": _failure_code(error)}) + "\n",
            encoding="utf-8",
        )
        return 1
    return 0


def _run_once(
    service: TemplateProcessingService,
    suffix: str,
    content: bytes,
    run_root: Path,
) -> tuple[dict[str, float], dict[str, int | None]]:
    document_id = str(uuid.uuid4())
    total_started = time.perf_counter()
    with _MemoryProbe() as memory_probe:
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
    memory = memory_probe.result()
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
    (run_root / "memory.json").write_text(
        json.dumps(memory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return record, memory


def _prime_service(
    service: TemplateProcessingService,
    suffix: str,
    content: bytes,
) -> None:
    warm_up = getattr(service, "warm_up_ocr", None)
    if callable(warm_up):
        warm_up()
        return
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


def _load_memory_record(run_root: Path) -> dict[str, int | None] | None:
    path = run_root / "memory.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit("Stored benchmark memory is unreadable") from error
    record: dict[str, int | None] = {}
    for metric in MEMORY_METRICS:
        value = payload.get(metric)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise SystemExit("Stored benchmark memory is invalid")
        record[metric] = value
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


def _summarize_memory(
    records: Sequence[Mapping[str, int | None]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for metric in MEMORY_METRICS:
        values = [
            float(value)
            for record in records
            if (value := record.get(metric)) is not None
        ]
        result[metric] = {
            "p50": percentile(values, 0.50) if values else None,
            "p95": percentile(values, 0.95) if values else None,
            "samples": len(values),
        }
    return result


class _MemoryProbe:
    """Capture aggregate-only memory telemetry around one local run."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._peak_rss: int | None = None
        self._peak_python = 0
        self._was_tracing = False

    def __enter__(self) -> _MemoryProbe:
        self._was_tracing = tracemalloc.is_tracing()
        if not self._was_tracing:
            tracemalloc.start()
        self._peak_rss = _rss_bytes()
        if self._peak_rss is not None:
            self._thread = threading.Thread(
                target=self._sample_rss,
                name="hcns-benchmark-memory",
                daemon=True,
            )
            self._thread.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        _current, self._peak_python = tracemalloc.get_traced_memory()
        if not self._was_tracing:
            tracemalloc.stop()
        current_rss = _rss_bytes()
        if current_rss is not None:
            self._peak_rss = max(self._peak_rss or 0, current_rss)

    def result(self) -> dict[str, int | None]:
        return {
            "peakPythonMemoryBytes": int(self._peak_python),
            "peakRssBytes": self._peak_rss,
        }

    def _sample_rss(self) -> None:
        while not self._stop.wait(0.05):
            current = _rss_bytes()
            if current is not None:
                self._peak_rss = max(self._peak_rss or 0, current)


def _rss_bytes() -> int | None:
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return None


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
