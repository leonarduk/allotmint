#!/usr/bin/env bash
# Start allotmint-pro's MCP server (the tools behind the chat drawer) in the
# foreground, for when you want it in its own terminal rather than started in
# the background by run-local-api.sh (which then finds the port in use and
# leaves it alone). Ctrl+C stops it.
#
# Usage: bash scripts/bash/run-mcp-server.sh [--restart] [port]
#   port defaults to $MCP_SERVER_PORT, else 8001. Needs an allotmint-pro
#   checkout at $ALLOTMINT_PRO_DIR, else the sibling ../allotmint-pro.
#   Point the backend at it with MCP_SERVER_URL=http://localhost:<port>/mcp.
#   --restart first stops the MCP server already on the port (only that
#   server; anything else holding the port is left alone). Run it from a new
#   shell to pick up environment variables set since the old server started.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=scripts/bash/lib/load_env.sh
source "$SCRIPT_DIR/lib/load_env.sh"
# shellcheck source=scripts/bash/lib/start_mcp_server.sh
source "$SCRIPT_DIR/lib/start_mcp_server.sh"

# The server imports `backend`, which reads the same env as the backend.
load_allotmint_env "$REPO_ROOT"

RESTART=0
if [[ "${1:-}" == "--restart" ]]; then
  RESTART=1
  shift
fi

PORT="${1:-${MCP_SERVER_PORT:-8001}}"
if ! valid_port "$PORT"; then
  echo "Invalid port '$PORT' (from the argument or MCP_SERVER_PORT; expected 1-65535)." >&2
  echo "Usage: $0 [--restart] [port]" >&2
  exit 2
fi

if ! PRO_DIR=$(mcp_pro_dir "$REPO_ROOT"); then
  echo "allotmint-pro not found at ${ALLOTMINT_PRO_DIR:-$REPO_ROOT/../allotmint-pro}; clone it there or set ALLOTMINT_PRO_DIR." >&2
  exit 1
fi

if [[ "$RESTART" == "1" ]] && port_in_use "$PORT"; then
  # Stops only the allotmint-pro MCP server and waits for the port to free.
  "$(command -v python3 || command -v python)" -m backend.utils.mcp_server_process stop --port "$PORT"
fi

if port_in_use "$PORT"; then
  echo "Port $PORT is already in use (an MCP server may already be running); pass --restart to replace it, or another port." >&2
  exit 1
fi

echo "Starting the MCP server at http://localhost:$PORT/mcp (allotmint-pro: $PRO_DIR)" >&2
run_mcp_server "$REPO_ROOT" "$PRO_DIR" "$PORT"
