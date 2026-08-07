#!/usr/bin/env bash
# Run the HCNS Camunda 7 External Task worker against a local Camunda engine.
# The worker keeps polling the engine until interrupted (Ctrl+C).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export CAMUNDA_REST_URL="${CAMUNDA_REST_URL:-http://localhost:8080/engine-rest}"
export CAMUNDA_WORKER_ID="${CAMUNDA_WORKER_ID:-hcns-agent-worker-$(hostname)}"
export HCNS_CAMUNDA_PRIVATE_ROOT="${HCNS_CAMUNDA_PRIVATE_ROOT:-$ROOT/.private/camunda}"
export HCNS_TEMPLATE_OCR_BACKEND="${HCNS_TEMPLATE_OCR_BACKEND:-easyocr}"

mkdir -p "$HCNS_CAMUNDA_PRIVATE_ROOT"

echo "Camunda worker starting:"
echo "  CAMUNDA_REST_URL=$CAMUNDA_REST_URL"
echo "  CAMUNDA_WORKER_ID=$CAMUNDA_WORKER_ID"
echo "  HCNS_CAMUNDA_PRIVATE_ROOT=$HCNS_CAMUNDA_PRIVATE_ROOT"
echo "  HCNS_TEMPLATE_OCR_BACKEND=$HCNS_TEMPLATE_OCR_BACKEND"

exec "$PYTHON" -m hcns_agent.camunda_worker_cli
