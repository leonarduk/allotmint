#!/usr/bin/env bash
set -euo pipefail

# ensure script runs from repository root so log files are written consistently
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Load Telegram credentials if available
if [[ -f .env ]]; then
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
fi

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "Warning: TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID not set; Telegram logging will be disabled." >&2
fi

# load shared config
CONFIG_FILE="config.yaml"
APP_ENV=$(awk -F': ' '/^app_env:/ {print $2}' "$CONFIG_FILE" | tr -d '"')
UVICORN_HOST=$(awk -F': ' '/^uvicorn_host:/ {print $2}' "$CONFIG_FILE" | tr -d '"')
UVICORN_HOST=${UVICORN_HOST:-0.0.0.0}
UVICORN_PORT=$(awk -F': ' '/^uvicorn_port:/ {print $2}' "$CONFIG_FILE" | tr -d '"')
RELOAD=$(awk -F': ' '/^reload:/ {print $2}' "$CONFIG_FILE" | tr -d '"')
LOG_CONFIG=$(awk -F': ' '/^log_config:/ {print $2}' "$CONFIG_FILE" | tr -d '"')

export ALLOTMINT_ENV="$APP_ENV"

if [[ -n "${DATA_BUCKET:-}" ]]; then
  echo "Syncing data from s3://$DATA_BUCKET/" >&2
  aws s3 sync "s3://$DATA_BUCKET/" data/
else
  echo "DATA_BUCKET not set; skipping data sync" >&2
fi

CMD=(uvicorn backend.local_api.main:app --reload-dir backend --port "$UVICORN_PORT" --host "$UVICORN_HOST" --log-config "$LOG_CONFIG")
if [[ "$RELOAD" == "true" ]]; then
  CMD+=(--reload)
fi
"${CMD[@]}"
