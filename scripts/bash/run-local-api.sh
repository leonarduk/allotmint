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

# Load Telegram credentials etc. from .env / the shared env file.
# shellcheck source=scripts/bash/lib/load_env.sh
source "$SCRIPT_DIR/lib/load_env.sh"
load_allotmint_env "$REPO_ROOT"

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "Warning: TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID not set; Telegram logging will be disabled." >&2
fi

# load shared config (keys are nested under server:/paths:; defaults match
# scripts/run-backend.ps1)
# shellcheck source=scripts/bash/lib/read_config_value.sh
source "$SCRIPT_DIR/lib/read_config_value.sh"
CONFIG_FILE="config.yaml"
APP_ENV=$(read_config_value "$CONFIG_FILE" server.app_env local)
UVICORN_HOST=$(read_config_value "$CONFIG_FILE" server.uvicorn_host 0.0.0.0)
UVICORN_PORT=$(read_config_value "$CONFIG_FILE" server.uvicorn_port 6468)
RELOAD=$(read_config_value "$CONFIG_FILE" server.reload true)
LOG_CONFIG=$(read_config_value "$CONFIG_FILE" paths.log_config backend/logging.ini)

# backend/logging.ini's file handler writes logs/backend.log, and uvicorn
# loads it before any Python setup runs, so the directory must exist first.
mkdir -p logs

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

# shellcheck source=scripts/bash/lib/start_mcp_server.sh
source "$SCRIPT_DIR/lib/start_mcp_server.sh"
start_local_mcp_server "$REPO_ROOT"
if [[ -n "$MCP_SERVER_PID" ]]; then
  trap 'kill "$MCP_SERVER_PID" 2>/dev/null || true' EXIT
fi

# The backend imports allotmint-pro from the same checkout as the MCP server,
# so pro-only features (screener, risk, the strategy stress test's
# long-history proxies) work locally; BACKEND_USE_PRO=0 runs it free-only.
# (Empty when backend_pro_dir fails: it prints nothing then.)
if BACKEND_PRO_DIR=$(backend_pro_dir "$REPO_ROOT"); then
  export PYTHONPATH="$REPO_ROOT:$BACKEND_PRO_DIR${PYTHONPATH:+:$PYTHONPATH}"
  echo "Backend imports allotmint-pro from $BACKEND_PRO_DIR (BACKEND_USE_PRO=0 to run free-only)" >&2
fi

CMD=(uvicorn backend.local_api.main:app --reload-dir backend --port "$UVICORN_PORT" --host "$UVICORN_HOST" --log-config "$LOG_CONFIG")
if [[ "$RELOAD" == "true" ]]; then
  CMD+=(--reload)
  # Without watchfiles uvicorn polls every watched file (StatReload), which
  # costs a steady chunk of a core while idle (#10363).
  if ! python -c 'import watchfiles' 2>/dev/null; then
    echo "Warning: watchfiles is not installed; uvicorn --reload will poll files (StatReload) and use CPU while idle. Run: pip install -r requirements.txt" >&2
  fi
  # Reload on pro changes too, not only backend/.
  [[ -n "$BACKEND_PRO_DIR" ]] && CMD+=(--reload-dir "$BACKEND_PRO_DIR/allotmint_pro")
fi
"${CMD[@]}"
