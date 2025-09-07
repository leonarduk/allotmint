#!/usr/bin/env bash
set -euo pipefail

# ensure script runs from repository root so log files are written consistently
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ensure data directory exists
if [[ ! -d data || -z "$(ls -A data 2>/dev/null)" ]]; then
  echo "Data directory missing; syncing..." >&2
  scripts/sync_data.sh
fi

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

CMD=(uvicorn backend.local_api.main:app --reload-dir backend --port "$UVICORN_PORT" --host "$UVICORN_HOST" --log-config "$LOG_CONFIG")
if [[ "$RELOAD" == "true" ]]; then
  CMD+=(--reload)
fi
"${CMD[@]}"
