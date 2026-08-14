#!/usr/bin/env bash
# Linux launcher for the VinHRIS OCR Lab dashboard + local API.
# Usage: bash scripts/start_dashboard_linux.sh [DATA_ROOT]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
DATA_ROOT="${1:-$HOME/private-data}"
PORT_API=8765
PORT_WEB=3000

if [ ! -x "$PYTHON" ]; then
  echo "venv not found. Run:"
  echo "  python3 -m venv $REPO_ROOT/.venv"
  echo "  $REPO_ROOT/.venv/bin/pip install -e \"$REPO_ROOT[api,dev,paddle]\""
  exit 1
fi

mkdir -p "$DATA_ROOT"

# --- API ---
if curl -sf "http://127.0.0.1:$PORT_API/health" >/dev/null 2>&1; then
  echo "API already running on port $PORT_API"
else
  echo "Starting local API on port $PORT_API ..."
  cd "$REPO_ROOT"
  HCNS_TEMPLATE_OCR_BACKEND=paddle setsid nohup \
    "$PYTHON" -u apps/ocr_lab/api/serve_dashboard_api.py \
      --data-root "$DATA_ROOT" --host 127.0.0.1 --port "$PORT_API" \
      > "$REPO_ROOT/tmp/api.log" 2>&1 < /dev/null &
  for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:$PORT_API/health" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  curl -sf "http://127.0.0.1:$PORT_API/health" >/dev/null 2>&1 \
    || { echo "API failed to start; see $REPO_ROOT/tmp/api.log"; exit 1; }
fi

# --- Web ---
if curl -sf "http://localhost:$PORT_WEB" >/dev/null 2>&1; then
  echo "Dashboard already running on port $PORT_WEB"
else
  echo "Starting dashboard on port $PORT_WEB ..."
  cd "$REPO_ROOT/apps/ocr_lab/web"
  setsid nohup npm run dev > "$REPO_ROOT/tmp/web.log" 2>&1 < /dev/null &
  for _ in $(seq 1 60); do
    if curl -sf "http://localhost:$PORT_WEB" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  curl -sf "http://localhost:$PORT_WEB" >/dev/null 2>&1 \
    || { echo "Dashboard failed to start; see $REPO_ROOT/tmp/web.log"; exit 1; }
fi

echo ""
echo "VinHRIS Dashboard: http://localhost:$PORT_WEB"
echo "Local API:         http://127.0.0.1:$PORT_API"
echo "Logs:              $REPO_ROOT/tmp/web.log, $REPO_ROOT/tmp/api.log"
