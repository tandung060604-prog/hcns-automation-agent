#!/usr/bin/env python3
"""Cross-platform launcher for the HCNS OCR dashboard.

Starts the local OCR/IDP API (default http://127.0.0.1:8765) and the
Next.js dashboard UI (default http://localhost:3000), then keeps both alive
until interrupted. Pure Python stdlib; works on Windows, macOS and Linux.

Usage:
    python run_local.py --data-root <path-to-private-data>
    python run_local.py --data-root <path> --setup          # also install deps
    python run_local.py --data-root <path> --full           # install OCR extras too
    python run_local.py --data-root <path> --no-ui          # API server only
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
API_SCRIPT = REPO_ROOT / "apps" / "ocr_lab" / "api" / "serve_dashboard_api.py"
WEB_ROOT = REPO_ROOT / "apps" / "ocr_lab" / "web"
VENV_DIR = REPO_ROOT / ".venv"

API_HOST = "127.0.0.1"
API_PORT = 8765
UI_PORT = 3000
STOP_EVENT = threading.Event()


def log(message: str) -> None:
    print(f"[launcher] {message}", flush=True)


def progress_line(prefix: str, line: str) -> None:
    sys.stdout.write(f"[{prefix}] {line.rstrip()}\n")
    sys.stdout.flush()


def is_windows() -> bool:
    return os.name == "nt"


def venv_python() -> Path:
    sub_dir = "Scripts" if is_windows() else "bin"
    name = "python.exe" if is_windows() else "python"
    return VENV_DIR / sub_dir / name


def npm_command() -> str:
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def ensure_node() -> None:
    if not shutil.which("npm"):
        raise SystemExit("Node.js/npm is required for the dashboard UI but not found.")


def resolve_python(python: str | None) -> Path:
    if python:
        requested = Path(python)
        if not requested.is_file():
            raise SystemExit(f"Python executable not found: {requested}")
        return requested
    candidate = venv_python()
    if candidate.is_file():
        return candidate
    return Path(sys.executable)


def run_checked(argv: Sequence[str], cwd: Path | None = None) -> None:
    log("Running: " + " ".join(str(part) for part in argv))
    result = subprocess.run(list(argv), cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(
            f"Command failed with exit code {result.returncode}: {' '.join(map(str, argv))}"
        )


def run_setup(apply_ocr_extras: bool) -> None:
    ensure_node()
    if not VENV_DIR.exists():
        log(f"Creating Python venv at {VENV_DIR} ...")
        run_checked([sys.executable, "-m", "venv", str(VENV_DIR)])
    py = venv_python()
    if not py.is_file():
        raise SystemExit(f"Venv python missing: {py}")
    run_checked([str(py), "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    extras = "dev,paddle,easyocr" if apply_ocr_extras else "dev"
    run_checked([str(py), "-m", "pip", "install", "-e", f".[{extras}]"])
    run_checked([npm_command(), "ci"], cwd=WEB_ROOT)


def spawn(
    prefix: str,
    argv: Sequence[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    log(f"Starting [{prefix}]: " + " ".join(str(part) for part in argv))
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    creationflags = 0
    if is_windows():
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        list(argv),
        cwd=cwd or REPO_ROOT,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=not is_windows(),
        creationflags=creationflags,
    )
    threading.Thread(target=drain, args=(prefix, proc), daemon=True).start()
    return proc


def drain(prefix: str, proc: subprocess.Popen) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        progress_line(prefix, line)


def terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if is_windows():
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
            )
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"Could not stop process {proc.pid}: {exc}")


def wait_http(host: str, port: int, timeout: float, label: str, path: str = "/health") -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if STOP_EVENT.is_set():
            return False
        try:
            with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=1):
                log(f"{label} is healthy on http://{host}:{port}{path}")
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((API_HOST, port))
            return False
        except OSError:
            return True


def watch_both(api: subprocess.Popen | None, ui: subprocess.Popen | None) -> None:
    while not STOP_EVENT.is_set():
        for proc in (api, ui):
            if proc is not None and proc.poll() is not None:
                log(f"A server exited with code {proc.returncode}; stopping the session...")
                STOP_EVENT.set()
                return
        STOP_EVENT.wait(1)


def install_stop_handlers() -> None:
    if is_windows():
        return

    def _request_stop(signum: int, frame: object) -> None:
        log(f"Received signal {signum}; stopping servers...")
        STOP_EVENT.set()

    signal.signal(signal.SIGTERM, _request_stop)


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data"),
        help="Local private data root for sessions/evidence (required by the API).",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Python interpreter to run the API server. Defaults to .venv then "
        "the current interpreter.",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Create .venv, install Python deps (.[dev]) and run npm ci for the UI.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="With --setup, also install paddleocr/easyocr heavy OCR dependencies.",
    )
    parser.add_argument("--no-ui", action="store_true", help="Only start the OCR API server.")
    parser.add_argument(
        "--api-timeout",
        type=int,
        default=60,
        help="Seconds to wait for API health.",
    )
    parser.add_argument("--ui-timeout", type=int, default=90, help="Seconds to wait for UI health.")
    args = parser.parse_args(argv)

    data_root = args.data_root.resolve()
    data_root.mkdir(parents=True, exist_ok=True)

    if args.setup or args.full:
        run_setup(apply_ocr_extras=args.full)

    py = resolve_python(args.python)
    if not API_SCRIPT.is_file():
        raise SystemExit(f"API script not found: {API_SCRIPT}")
    install_stop_handlers()

    if port_in_use(API_PORT):
        log(f"Port {API_PORT} is already in use; assuming an OCR API is already running.")
        api_proc: subprocess.Popen | None = None
    else:
        api_env = os.environ.copy()
        api_env["PYTHONPATH"] = (
            str(REPO_ROOT / "src") + os.pathsep + api_env.get("PYTHONPATH", "")
        )
        api_proc = spawn(
            "api",
            [
                str(py),
                "-u",
                str(API_SCRIPT),
                "--data-root",
                str(data_root),
                "--host",
                API_HOST,
                "--port",
                str(API_PORT),
            ],
            env=api_env,
        )
        if not wait_http(API_HOST, API_PORT, float(args.api_timeout), "OCR API"):
            log(f"OCR API did not become healthy within {args.api_timeout}s on port {API_PORT}.")
            terminate(api_proc)
            return 1

    ui_proc: subprocess.Popen | None = None
    if not args.no_ui:
        if not WEB_ROOT.is_dir():
            log(f"Web UI directory not found: {WEB_ROOT}")
        else:
            if not (WEB_ROOT / "node_modules").is_dir():
                ensure_node()
                run_checked([npm_command(), "ci"], cwd=WEB_ROOT)
            ui_proc = spawn("ui", [npm_command(), "run", "dev"], cwd=WEB_ROOT)
            if not wait_http("127.0.0.1", UI_PORT, float(args.ui_timeout), "UI", path="/"):
                log(f"UI did not become healthy within {args.ui_timeout}s; check the log above.")

    log("Dashboard: http://localhost:3000   OCR API: http://127.0.0.1:8765")
    log("Press Ctrl+C to stop both servers.")

    threading.Thread(target=watch_both, args=(api_proc, ui_proc), daemon=True).start()
    try:
        while not STOP_EVENT.is_set():
            STOP_EVENT.wait(0.5)
    except KeyboardInterrupt:
        log("Stopping...")
    finally:
        STOP_EVENT.set()
        for proc in (api_proc, ui_proc):
            if proc is not None:
                terminate(proc)
    log("Both servers stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))