#!/usr/bin/env python3
"""Deploy VinHRIS stack publicly via free Cloudflare quick tunnels.

No account, no port forwarding needed. Each service gets a random
https://*.trycloudflare.com URL. Ctrl+C tears everything down.

Usage:
    python deploy_public.py [--data-root PATH] [--ocr-backend easyocr|paddle]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
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
    parser.add_argument(
        "--ocr-backend",
        choices=("easyocr", "paddle", "auto"),
        default="auto",
        help="Template OCR backend (auto = EasyOCR if installed, else Paddle).",
    )
    parser.add_argument("--port-api", type=int, default=8765)
    parser.add_argument("--port-web", type=int, default=3000)
    parser.add_argument("--no-worker", action="store_true")
    parser.add_argument(
        "--no-ocr-warmup",
        action="store_true",
        help="Skip loading OCR models at deploy time (not recommended for public demo).",
    )
    return parser.parse_args()


def resolve_deploy_ocr_backend(requested: str) -> str:
    """Mirror template auto-selection so deploy env matches the API process."""
    selected = (requested or "auto").casefold().strip()
    easyocr_ok = (
        subprocess.run(
            [
                str(VENV_PYTHON),
                "-c",
                "import importlib.util; raise SystemExit(0 if "
                "importlib.util.find_spec('easyocr') else 1)",
            ],
            capture_output=True,
        ).returncode
        == 0
    )
    paddle_ok = (
        subprocess.run(
            [
                str(VENV_PYTHON),
                "-c",
                "import importlib.util; raise SystemExit(0 if "
                "importlib.util.find_spec('paddleocr') else 1)",
            ],
            capture_output=True,
        ).returncode
        == 0
    )
    if selected in {"", "auto"}:
        if easyocr_ok:
            return "easyocr"
        if paddle_ok:
            return "paddle"
        return "easyocr"
    if selected == "easyocr" and not easyocr_ok and paddle_ok:
        return "paddle"
    if selected == "paddle" and not paddle_ok and easyocr_ok:
        return "easyocr"
    return selected


def wait_for_ocr_ready(api_url: str, attempts: int = 90, interval: float = 2.0) -> bool:
    """POST/GET OCR warmup until models are loaded or attempts exhausted."""
    warmup_url = f"{api_url.rstrip('/')}/api/ocr/warmup"
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(warmup_url, timeout=120) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
                if payload.get("backendAvailable") and payload.get("templateOcrModelLoaded"):
                    log(
                        f"OCR ready backend={payload.get('templateOcrBackend')} "
                        f"profile={payload.get('templateOcrProfile')} (attempt {attempt})"
                    )
                    return True
                log(
                    f"OCR warming… available={payload.get('backendAvailable')} "
                    f"loaded={payload.get('templateOcrModelLoaded')} (attempt {attempt}/{attempts})"
                )
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            log(f"OCR warmup probe failed ({attempt}/{attempts}): {exc}")
        time.sleep(interval)
    return False


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
    # Confirm the port is actually free; vinext/workerd orphans can survive a
    # soft kill and keep serving an old VITE_API_BASE (broken public API).
    still = subprocess.run(
        ["fuser", f"{port}/tcp"],
        capture_output=True,
        text=True,
    )
    if still.returncode == 0 and still.stdout.strip():
        log(f"Port {port} still busy after fuser -k; force-killing PIDs {still.stdout.strip()}")
        for pid in still.stdout.split():
            if pid.isdigit():
                subprocess.run(["kill", "-9", pid], capture_output=True)
        time.sleep(1)


def kill_stale_web_dev_servers() -> None:
    """Kill orphaned vinext/vite processes for this repo (reparented to systemd)."""
    marker = str(WEB_ROOT)
    result = subprocess.run(["pgrep", "-af", "vinext|vite"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if marker not in line and "hcns-ocr-lab-web" not in line:
            continue
        pid = line.split(None, 1)[0]
        if not pid.isdigit():
            continue
        log(f"Killing stale web dev server pid={pid}")
        subprocess.run(["kill", "-9", pid], capture_output=True)
    time.sleep(1)


def start_tunnel(name: str, local_url: str) -> ProcessHandle:
    log_path = LOG_ROOT / f"tunnel_{name}.log"
    stream = log_path.open("wb")
    subprocess.run(["docker", "rm", "-f", f"hcns-tunnel-{name}"], capture_output=True)
    # Prefer HTTP/2 over TCP: many office/ISP networks block QUIC/UDP :7844,
    # which leaves a trycloudflare.com hostname with Error 1033 (no connector).
    log(f"Starting Cloudflare tunnel '{name}' -> {local_url} (protocol=http2)")
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
            "--protocol",
            "http2",
            "--url",
            local_url,
        ],
        stdout=stream,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


def wait_for_tunnel_url(name: str, attempts: int = 90, interval: float = 1.0) -> str | None:
    """Wait until Cloudflare assigns a URL *and* a connector registers.

    Quick tunnels print the public URL before the edge connection succeeds.
    Without a registered connector, visitors get Cloudflare Error 1033.
    """
    log_path = LOG_ROOT / f"tunnel_{name}.log"
    url: str | None = None
    for _ in range(attempts):
        if log_path.is_file():
            try:
                content = log_path.read_text(encoding="utf-8", errors="replace")
                if url is None:
                    match = URL_RE.search(content)
                    if match:
                        url = match.group(0).rstrip("/")
                if url and "Registered tunnel connection" in content:
                    return url
                if "Failed to dial" in content and "http2" not in content.lower():
                    # Keep waiting; http2 retries are expected under flaky nets.
                    pass
            except OSError:
                pass
        time.sleep(interval)
    if url is not None:
        log(
            f"Tunnel '{name}' got URL {url} but never registered a connection; "
            f"see {log_path} (likely blocked QUIC/UDP or TCP :7844)"
        )
    return None


def shutdown(
    processes: list[ProcessHandle],
    tunnels: list[ProcessHandle],
    _signum: int = signal.SIGTERM,
    _frame: object = None,
) -> None:
    log("Shutting down tunnels and processes...")
    for handle in [*tunnels, *processes]:
        with contextlib.suppress(OSError):
            handle.terminate()
    time.sleep(2)
    for handle in [*tunnels, *processes]:
        try:
            handle.wait(timeout=10)
        except subprocess.TimeoutExpired:
            handle.kill()


def main() -> int:
    args = parse_args()
    data_root = args.data_root or Path(
        os.environ.get("HCNS_DATA_ROOT") or Path.home() / "private-data"
    )
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
    optional: list[ProcessHandle] = []
    tunnels: list[ProcessHandle] = []

    def _on_signal(signum: int, frame: object) -> None:
        shutdown([*processes, *optional], tunnels, signum, frame)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    ocr_backend = resolve_deploy_ocr_backend(args.ocr_backend)
    if ocr_backend != args.ocr_backend and args.ocr_backend != "auto":
        log(
            f"Requested OCR backend '{args.ocr_backend}' is not installed; "
            f"falling back to '{ocr_backend}'."
        )
    elif args.ocr_backend == "auto":
        log(f"Auto-selected OCR backend: {ocr_backend}")

    base_env = dict(os.environ)
    base_env.update(
        {
            "HCNS_ENV": "development",
            "HCNS_LOG_LEVEL": "INFO",
            "HCNS_TEMPLATE_OCR_BACKEND": ocr_backend,
            "HCNS_TEMPLATE_OCR_WARMUP": "0" if args.no_ocr_warmup else "1",
            "HCNS_API_ALLOWED_HOSTS": "*.trycloudflare.com",
            "HCNS_API_CORS_ORIGINS": "https://*.trycloudflare.com",
            "PYTHONUNBUFFERED": "1",
        }
    )

    api_url = f"http://127.0.0.1:{args.port_api}"

    free_port(args.port_api)
    free_port(args.port_web)
    kill_stale_web_dev_servers()
    free_port(args.port_web)
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

    if not args.no_ocr_warmup:
        log(f"Warming OCR models ({ocr_backend}) — first load can take 1–3 minutes…")
        if not wait_for_ocr_ready(api_url):
            log(
                "OCR warm-up did not finish in time; dashboard vẫn chạy nhưng "
                "scan ảnh/PDF có thể chậm hoặc lỗi. Xem tmp/api.log."
            )
        else:
            log("OCR models loaded and ready for scan uploads.")
    else:
        log("Skipping OCR warm-up (--no-ocr-warmup).")

    camunda_local = "http://127.0.0.1:8080"
    if http_ready(f"{camunda_local}/camunda"):
        log("Camunda detected locally; keeping its engine and webapps private.")

    web_env = dict(base_env)
    web_env["VITE_API_BASE"] = api_tunnel_url
    processes.append(start_process(["npm", "run", "dev"], "web.log", web_env, cwd=WEB_ROOT))
    web_url = f"http://localhost:{args.port_web}"
    deadline = time.time() + 90
    while time.time() < deadline and not http_ready(web_url):
        time.sleep(1)
    if not http_ready(web_url):
        log("Web failed to start; check tmp/web.log")
        shutdown([*processes, *optional], tunnels)
        return 1
    # Ensure the listener is our new server with the current API tunnel URL,
    # not an orphan still holding :3000 with a stale VITE_API_BASE.
    probe = subprocess.run(
        ["fuser", f"{args.port_web}/tcp"],
        capture_output=True,
        text=True,
    )
    listener_pids = [p for p in probe.stdout.split() if p.isdigit()]
    for pid in listener_pids:
        try:
            environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
            env_map = {}
            for item in environ:
                if b"=" in item:
                    key, _, value = item.partition(b"=")
                    env_map[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
            baked = env_map.get("VITE_API_BASE", "")
            if baked and baked.rstrip("/") != api_tunnel_url.rstrip("/"):
                log(
                    f"Port {args.port_web} listener pid={pid} has stale VITE_API_BASE={baked!r}; "
                    f"expected {api_tunnel_url!r}"
                )
                shutdown([*processes, *optional], tunnels)
                return 1
        except OSError:
            pass
    log(f"Web ready: True (VITE_API_BASE={api_tunnel_url})")

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
        optional.append(
            start_process(
                [str(VENV_PYTHON), "-u", "-m", "hcns_agent.camunda_worker_cli"],
                "worker.log",
                worker_env,
            )
        )

    log("=" * 64)
    log("Deploy sẵn sàng — mở từ máy khác:")
    log(f"  VinHRIS Dashboard : {web_tunnel_url}/workspace")
    log(f"  Local API         : {api_tunnel_url}")
    log("  Camunda Tasklist  : local/private only (http://127.0.0.1:8080/camunda)")
    log(f"  OCR backend       : {ocr_backend} (warmed={'no' if args.no_ocr_warmup else 'yes'})")
    log("  Demo accounts     : admin/admin123, hr/hr123, user/user123")
    log("  Mọi URL đều HTTPS miễn phí qua Cloudflare.")
    log("  Nhấn Ctrl+C để tắt toàn bộ.")

    worker_warned = False
    while True:
        dead_core = [
            f"process[{idx}] exit={handle.returncode}"
            for idx, handle in enumerate(processes)
            if handle.poll() is not None
        ] + [
            f"tunnel[{idx}] exit={handle.returncode}"
            for idx, handle in enumerate(tunnels)
            if handle.poll() is not None
        ]
        if dead_core:
            log(f"Core process exited ({', '.join(dead_core)}); dừng toàn bộ.")
            shutdown([*processes, *optional], tunnels)
            return 2
        if not worker_warned:
            for idx, handle in enumerate(optional):
                code = handle.poll()
                if code is not None:
                    log(
                        f"Optional worker[{idx}] exited (code={code}); dashboard vẫn chạy. "
                        "Xem tmp/worker.log"
                    )
                    worker_warned = True
                    break
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
