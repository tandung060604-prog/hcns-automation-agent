#!/usr/bin/env python3
"""Deploy VinHRIS stack publicly via free Cloudflare quick tunnels.

No account, no port forwarding needed. Each service gets a random
https://*.trycloudflare.com URL. Ctrl+C tears everything down.

Usage:
    python deploy_public.py [--data-root PATH] [--ocr-backend easyocr|paddle]
"""

from __future__ import annotations

import argparse
import os
import re
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
TUNNEL_IMAGE = "cloudflare/cloudflared"
URL_RE = re.compile(r"https://[\w.-]+\.trycloudflare\.com")
API_HEALTH = "/health"

ProcessHandle = subprocess.Popen[bytes]


def log(message: str) -> None:
    print(f"[deploy-public] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--ocr-backend", choices=("easyocr", "paddle"), default="easyocr")
    parser.add_argument("--port-api", type=int, default=8765)
    parser.add_argument("--port-web", type=int, default=3000)
    parser.add_argument("--no-worker", action="store_true")
    return parser.parse_args()


def http_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return 200 <= response.status < 500
    except (urllib.error.URLError, OSError):
        return False


def start_process(
    command: list[str],
    log_name: str,
    env: dict[str, str],
    cwd: Path | None = None,
) -> ProcessHandle:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    stream = (LOG_ROOT / log_name).open("ab")
    log(f"Starting {' '.join(command[:2])} (logs: {LOG_ROOT / log_name})")
    return subprocess.Popen(
        command,
        cwd=str(cwd or REPO_ROOT),
        env=env,
        stdout=stream,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


def free_port(port: int) -> None:
    result = subprocess.run(
        ["fuser", "-k", f"{port}/tcp"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        log(f"Freed stale process on port {port}")
    time.sleep(2)


def start_tunnel(name: str, local_url: str) -> ProcessHandle:
    log_path = LOG_ROOT / f"tunnel_{name}.log"
    stream = log_path.open("wb")
    subprocess.run(["docker", "rm", "-f", f"hcns-tunnel-{name}"], capture_output=True)
    log(f"Starting Cloudflare tunnel '{name}' -> {local_url}")
    return subprocess.Popen(
        [
            "docker",
            "run",
            "--rm",
            "--name",
            f"hcns-tunnel-{name}-{int(time.time())}",
            "--network",
            "host",
            TUNNEL_IMAGE,
            "tunnel",
            "--no-autoupdate",
            "--url",
            local_url,
        ],
        stdout=stream,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


def wait_for_tunnel_url(name: str, attempts: int = 60, interval: float = 1.0) -> str | None:
    log_path = LOG_ROOT / f"tunnel_{name}.log"
    for _ in range(attempts):
        if log_path.is_file():
            try:
                content = log_path.read_text(encoding="utf-8", errors="replace")
                match = URL_RE.search(content)
                if match:
                    return match.group(0).rstrip("/")
            except OSError:
                pass
        time.sleep(interval)
    return None


def shutdown(
    processes: list[ProcessHandle],
    tunnels: list[ProcessHandle],
    _signum: int = signal.SIGTERM,
    _frame: object = None,
) -> None:
    log("Shutting down tunnels and processes...")
    for handle in [*tunnels, *processes]:
        try:
            handle.terminate()
        except OSError:
            pass
    time.sleep(2)
    for handle in [*tunnels, *processes]:
        try:
            handle.wait(timeout=10)
        except subprocess.TimeoutExpired:
            handle.kill()


def main() -> int:
    args = parse_args()
    data_root = args.data_root or Path(os.environ.get("HCNS_DATA_ROOT") or Path.home() / "private-data")
    data_root = data_root.expanduser().resolve()
    data_root.mkdir(parents=True, exist_ok=True)

    if not VENV_PYTHON.is_file():
        log("Missing .venv; run install first.")
        return 1
    if not (WEB_ROOT / "node_modules").is_dir():
        log(f"Missing node_modules in {WEB_ROOT}; run npm ci.")
        return 1
    if not shutil.which("docker"):
        log("docker not found; Cloudflare tunnel requires Docker.")
        return 1
    image_check = subprocess.run(["docker", "image", "inspect", TUNNEL_IMAGE], capture_output=True)
    if image_check.returncode != 0:
        log("Pulling cloudflare/cloudflared image (one time)...")
        pull = subprocess.run(["docker", "pull", TUNNEL_IMAGE], capture_output=True, text=True)
        if pull.returncode != 0:
            log(f"docker pull failed: {pull.stderr[-500:]}")
            return 1

    processes: list[ProcessHandle] = []
    tunnels: list[ProcessHandle] = []
    signal.signal(signal.SIGINT, lambda s, f: shutdown(processes, tunnels, s, f))
    signal.signal(signal.SIGTERM, lambda s, f: shutdown(processes, tunnels, s, f))

    base_env = dict(os.environ)
    base_env.update(
        {
            "HCNS_ENV": "development",
            "HCNS_LOG_LEVEL": "INFO",
            "HCNS_TEMPLATE_OCR_BACKEND": args.ocr_backend,
            "HCNS_API_ALLOWED_HOSTS": "*.trycloudflare.com",
            "HCNS_API_CORS_ORIGINS": "https://*.trycloudflare.com",
            "PYTHONUNBUFFERED": "1",
        }
    )

    api_url = f"http://127.0.0.1:{args.port_api}"

    free_port(args.port_api)
    free_port(args.port_web)
    camunda_already_running = http_ready("http://127.0.0.1:8080/camunda")

    log("Starting API tunnel (get public URL first)...")
    tunnels.append(start_tunnel("api", api_url))
    api_tunnel_url = wait_for_tunnel_url("api")
    if api_tunnel_url is None:
        log("API tunnel URL not detected; see tmp/tunnel_api.log")
        shutdown(processes, tunnels)
        return 1
    log(f"API public URL: {api_tunnel_url}")

    processes.append(
        start_process(
            [
                str(VENV_PYTHON),
                "-u",
                str(REPO_ROOT / "apps" / "ocr_lab" / "api" / "serve_dashboard_api.py"),
                "--data-root",
                str(data_root),
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port_api),
            ],
            "api.log",
            base_env,
        )
    )
    if not http_ready(f"{api_url}{API_HEALTH}"):
        log("API not ready yet; waiting up to 60s...")
        deadline = time.time() + 60
        while time.time() < deadline:
            if http_ready(f"{api_url}{API_HEALTH}"):
                break
            time.sleep(1)
    if not http_ready(f"{api_url}{API_HEALTH}"):
        log("API failed to start; check tmp/api.log")
        shutdown(processes, tunnels)
        return 1

    camunda_local = "http://127.0.0.1:8080"
    camunda_tunnel_url: str | None = None
    if http_ready(f"{camunda_local}/camunda"):
        log("Camunda detected; opening tunnel for it...")
        tunnels.append(start_tunnel("camunda", camunda_local))
        camunda_tunnel_url = wait_for_tunnel_url("camunda")
        log(f"Camunda public URL: {camunda_tunnel_url or 'not detected'}")

    web_env = dict(base_env)
    web_env["VITE_API_BASE"] = api_tunnel_url
    if camunda_tunnel_url:
        web_env["VITE_CAMUNDA_URL"] = camunda_tunnel_url
    processes.append(start_process(["npm", "run", "dev"], "web.log", web_env, cwd=WEB_ROOT))
    web_url = f"http://localhost:{args.port_web}"
    deadline = time.time() + 90
    while time.time() < deadline and not http_ready(web_url):
        time.sleep(1)
    log(f"Web ready: {http_ready(web_url)}")

    tunnels.append(start_tunnel("web", web_url))
    web_tunnel_url = wait_for_tunnel_url("web", attempts=90)
    if web_tunnel_url is None:
        log("Web tunnel URL not detected; see tmp/tunnel_web.log")
        shutdown(processes, tunnels)
        return 1
    log(f"Web public URL: {web_tunnel_url}")

    if not args.no_worker:
        worker_env = dict(base_env)
        worker_env.update(
            {
                "CAMUNDA_REST_URL": f"{camunda_local}/engine-rest",
                "CAMUNDA_WORKER_ID": "hcns-local-shadow",
                "HCNS_CAMUNDA_PRIVATE_ROOT": str(data_root),
            }
        )
        processes.append(
            start_process([str(VENV_PYTHON), "-m", "hcns_agent.camunda_worker_cli"], "worker.log", worker_env)
        )

    log("=" * 64)
    log("Deploy sẵn sàng — mở từ máy khác:")
    log(f"  VinHRIS Dashboard : {web_tunnel_url}/workspace")
    log(f"  Local API         : {api_tunnel_url}")
    if camunda_tunnel_url:
        log(f"  Camunda Tasklist  : {camunda_tunnel_url}/camunda")
    log(f"  Demo accounts     : admin/admin123, hr/hr123, user/user123")
    log("  Mọi URL đều HTTPS miễn phí qua Cloudflare.")
    log("  Nhấn Ctrl+C để tắt toàn bộ.")

    while True:
        live = [handle.poll() is None for handle in processes] + [
            handle.poll() is None for handle in tunnels
        ]
        if not all(live):
            log("Một tiến trình đã thoát; dừng toàn bộ.")
            shutdown(processes, tunnels)
            return 2
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
