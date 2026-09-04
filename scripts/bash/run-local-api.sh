#!/usr/bin/env bash
set -euo pipefail

# ensure script runs from repository root so log files are written consistently
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# ensure data directory exists
if [[ ! -d data || -z "$(ls -A data 2>/dev/null)" ]]; then
  echo "Data directory missing; syncing..." >&2
  "$SCRIPT_DIR/sync_data.sh"
fi

# Load Telegram credentials if available. A repo-local .env still wins if
# present (backward compat), otherwise fall back to one shared file outside
# every repo/worktree so credentials never need copying around (see
# ALLOTMINT_ENV_FILE in docs/CONTRIBUTOR_RUNBOOK.md).
SHARED_ENV_FILE="${ALLOTMINT_ENV_FILE:-$HOME/workspace/GitHub/allotmint/.env.shared}"
if [[ -f .env ]]; then
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
elif [[ -f "$SHARED_ENV_FILE" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$SHARED_ENV_FILE"
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

# shellcheck source=scripts/bash/lib/find_free_port.sh
source "$SCRIPT_DIR/lib/find_free_port.sh"

# Pick a free port starting from the configured one so multiple local
# instances (e.g. separate worktrees/clones) can run side by side without
# clashing (see #5760). Explicitly setting UVICORN_PORT in the environment
# is treated as a hard requirement and is not shifted.
if [[ -z "${UVICORN_PORT_FIXED:-}" ]]; then
  RESOLVED_PORT=$(find_free_port "$UVICORN_PORT")
  if [[ "$RESOLVED_PORT" != "$UVICORN_PORT" ]]; then
    echo "Port $UVICORN_PORT is in use; using $RESOLVED_PORT instead" >&2
  fi
  UVICORN_PORT="$RESOLVED_PORT"
fi

# Write via a temp file + rename so a concurrent reader (vite.config.ts)
# never observes a partially written port number.
PORT_FILE_DIR="$REPO_ROOT/.local/ports"
mkdir -p "$PORT_FILE_DIR"
PORT_FILE="$PORT_FILE_DIR/backend.port"
TMP_PORT_FILE="$(mktemp "${PORT_FILE_DIR}/.backend.port.XXXXXX")"
echo "$UVICORN_PORT" > "$TMP_PORT_FILE"
mv -f "$TMP_PORT_FILE" "$PORT_FILE"
echo "Backend will listen on http://localhost:$UVICORN_PORT (port recorded in .local/ports/backend.port)" >&2

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
