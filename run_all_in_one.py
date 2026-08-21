#!/usr/bin/env python3
"""All-in-one launcher: local API (engine + OCR), VinHRIS web UI, Camunda worker.

One command starts the full stack and shuts everything down on Ctrl+C:

    python run_all_in_one.py --data-root "$HOME/private-data"

Components (script names default to their source of truth from README):
  1. Local API       apps/ocr_lab/api/serve_dashboard_api.py   -> 127.0.0.1:8765
  2. Web dashboard   apps/ocr_lab/web via `npm run dev`        -> localhost:3000
  3. Camunda worker  `hcns-agent-camunda-worker` (external-task worker)
  4. Camunda engine  optional auto-start via Docker (--with-camunda)

The API process hosts the OCR runtime (PaddleOCR / EasyOCR selected via
HCNS_TEMPLATE_OCR_BACKEND), so OCR needs no extra process.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
WEB_ROOT = REPO_ROOT / "apps" / "ocr_lab" / "web"
LOG_ROOT = REPO_ROOT / "tmp"
API_HEALTH_PATH = "/health"
CAMUNDA_REST = "http://127.0.0.1:8080/engine-rest"
CAMUNDA_IMAGE = "camunda/camunda-bpm-platform:run-latest"

ProcessHandle = subprocess.Popen[bytes]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Private data root (default: $HOME/private-data).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="API bind host (loopback only).")
    parser.add_argument("--port-api", type=int, default=8765)
    parser.add_argument("--port-web", type=int, default=3000)
    parser.add_argument(
        "--ocr-backend",
        choices=("easyocr", "paddle", "auto"),
        default="auto",
        help="OCR backend for template extraction (HCNS_TEMPLATE_OCR_BACKEND).",
    )
    parser.add_argument(
        "--no-worker",
        action="store_true",
        help="Skip the Camunda external-task worker.",
    )
    parser.add_argument(
        "--with-camunda",
        action="store_true",
        help="Auto-start the Camunda 7 engine via Docker if port 8080 is not reachable.",
    )
    parser.add_argument(
        "--camunda-rest-url",
        default=CAMUNDA_REST,
        help="Camunda REST base URL.",
    )
    parser.add_argument(
        "--camunda-worker-id",
        default="hcns-local-shadow",
        help="Camunda external-task worker id.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="HCNS_LOG_LEVEL for the API process.",
    )
    return parser.parse_args()


def log(message: str) -> None:
    print(f"[run-all-in-one] {message}", flush=True)


def http_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return 200 <= response.status < 500
    except (urllib.error.URLError, OSError):
        return False


def wait_for_ready(name: str, url: str, attempts: int, interval: float = 1.0) -> bool:
    for _ in range(attempts):
        if http_ready(url):
            return True
        time.sleep(interval)
    log(f"{name} not ready after {attempts * interval:.0f}s: {url}")
    return False


def start_process(command: list[str], log_name: str, env: dict[str, str]) -> ProcessHandle:
    log_path = LOG_ROOT / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stream = log_path.open("ab")
    log(f"Starting {command[0]} (logs: {log_path})")
    return subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=stream,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


def start_camunda_engine(port: int) -> ProcessHandle | None:
    if http_ready(f"http://127.0.0.1:{port}/camunda"):
        log("Camunda already running on 8080; skipping Docker start.")
        return None
    if not shutil.which("docker"):
        log("docker not found; cannot auto-start Camunda. Start it manually.")
        return None
    existing = subprocess.run(
        ["docker", "ps", "-q", "--filter", "name=hcns-camunda"], capture_output=True
    )
    stdout = existing.stdout.decode().strip()
    if stdout:
        log("Docker container 'hcns-camunda' already exists; starting it.")
        subprocess.run(["docker", "start", "hcns-camunda"], check=False)
        return None
    log(f"Pulling and starting {CAMUNDA_IMAGE} as 'hcns-camunda' (first run takes a while)...")
    return subprocess.Popen(
        [
            "docker",
            "run",
            "--name",
            "hcns-camunda",
            "--rm",
            "-p",
            f"{port}:8080",
            CAMUNDA_IMAGE,
        ],
        stdout=(LOG_ROOT / "camunda.log").open("ab"),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


def main() -> int:
    args = parse_args()
    LOG_ROOT.mkdir(parents=True, exist_ok=True)

    if not (REPO_ROOT / ".venv").is_dir() or not VENV_PYTHON.is_file():
        log("Missing .venv. Run: python3 -m venv .venv && .venv/bin/pip install -e '.[api,easyocr]'")
        return 1
    if not (WEB_ROOT / "node_modules").is_dir():
        log(f"Missing node_modules in {WEB_ROOT}. Run: npm ci")
        return 1

    data_root = args.data_root or Path(os.environ.get("HCNS_DATA_ROOT") or Path.home() / "private-data")
    data_root = data_root.expanduser().resolve()
    data_root.mkdir(parents=True, exist_ok=True)

    if args.ocr_backend == "auto":
        ocr_backend = os.environ.get("HCNS_TEMPLATE_OCR_BACKEND", "easyocr")
    else:
        ocr_backend = args.ocr_backend

    base_env = dict(os.environ)
    base_env.update(
        {
            "HCNS_LOG_LEVEL": args.log_level,
            "HCNS_TEMPLATE_OCR_BACKEND": ocr_backend,
            "HCNS_ENV": "development",
            "PYTHONUNBUFFERED": "1",
        }
    )

    processes: list[ProcessHandle] = []
    camunda_engine: ProcessHandle | None = None

    def shutdown(signum: int, _frame: object) -> None:
        log(f"Received signal {signum}; shutting down all processes...")
        for handle in processes:
            handle.terminate()
        if camunda_engine is not None:
            camunda_engine.terminate()
        for handle in [camunda_engine, *processes]:
            if handle is None:
                continue
            try:
                handle.wait(timeout=15)
            except subprocess.TimeoutExpired:
                handle.kill()
        log("All processes stopped.")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    camunda_url = args.camunda_rest_url.rstrip("/")
    if args.with_camunda:
        camunda_engine = start_camunda_engine(8080)
        wait_for_ready("Camunda engine", f"{camunda_url}/health/engine", 60, interval=5.0)

    api_host = str(args.host)
    api_url = f"http://{api_host}:{args.port_api}"

    processes.append(
        start_process(
            [
                str(VENV_PYTHON),
                "-u",
                str(REPO_ROOT / "apps" / "ocr_lab" / "api" / "serve_dashboard_api.py"),
                "--data-root",
                str(data_root),
                "--host",
                api_host,
                "--port",
                str(args.port_api),
            ],
            "api.log",
            base_env,
        )
    )
    api_ready = wait_for_ready("Local API", f"{api_url}{API_HEALTH_PATH}", 60, interval=1.0)
    if not api_ready:
        log("API failed to become ready. Check tmp/api.log.")
        shutdown(signal.SIGTERM, None)
        return 1

    web_env = dict(base_env)
    web_env.pop("PYTHONUNBUFFERED", None)
    processes.append(
        start_process(
            ["npm", "run", "dev"],
            "web.log",
            web_env,
        )
    )
    web_url = f"http://localhost:{args.port_web}"
    web_ready = wait_for_ready("Web dashboard", web_url, 90, interval=1.0)
    if not web_ready:
        log("Web dashboard failed to become ready. Check tmp/web.log.")

    worker_started = False
    if not args.no_worker:
        worker_env = dict(base_env)
        worker_env.update(
            {
                "CAMUNDA_REST_URL": camunda_url,
                "CAMUNDA_WORKER_ID": args.camunda_worker_id,
                "HCNS_CAMUNDA_PRIVATE_ROOT": str(data_root),
            }
        )
        try:
            processes.append(
                start_process(
                    [str(VENV_PYTHON), "-m", "hcns_agent.camunda_worker_cli"],
                    "worker.log",
                    worker_env,
                )
            )
            worker_started = True
        except OSError as exc:
            log(f"Worker failed to start: {exc}")
    else:
        log("Camunda worker skipped (--no-worker).")

    log("=" * 60)
    log("All services launched:")
    log(f"  VinHRIS Dashboard : http://localhost:{args.port_web}/workspace")
    log(f"  Local API         : {api_url}")
    log(f"  Camunda Tasklist  : {camunda_url.removesuffix('/engine-rest')}/camunda")
    log(f"  Private data root : {data_root}")
    log(f"  OCR backend       : {ocr_backend}")
    log(f"  Camunda worker    : {'running' if worker_started else 'skipped/disabled'}")
    log(f"  Logs              : {LOG_ROOT}/api.log, {LOG_ROOT}/web.log, {LOG_ROOT}/worker.log")
    log("Press Ctrl+C to stop everything.")

    while True:
        live = [handle.poll() is None for handle in processes]
        if not all(live):
            log("One or more processes exited unexpectedly; shutting down.")
            shutdown(signal.SIGTERM, None)
            return 2
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())