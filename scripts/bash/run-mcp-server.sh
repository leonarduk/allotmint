#!/usr/bin/env bash
# Start allotmint-pro's MCP server (the tools behind the chat drawer) in the
# foreground, for when you want it in its own terminal rather than started in
# the background by run-local-api.sh (which then finds the port in use and
# leaves it alone). Ctrl+C stops it.
#
# Usage: bash scripts/bash/run-mcp-server.sh [port]
#   port defaults to $MCP_SERVER_PORT, else 8001. Needs an allotmint-pro
#   checkout at $ALLOTMINT_PRO_DIR, else the sibling ../allotmint-pro.
#   Point the backend at it with MCP_SERVER_URL=http://localhost:<port>/mcp.
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

PORT="${1:-${MCP_SERVER_PORT:-8001}}"
if [[ ! "$PORT" =~ ^[0-9]+$ ]]; then
  echo "Usage: $0 [port]" >&2
  exit 2
fi

if ! PRO_DIR=$(mcp_pro_dir "$REPO_ROOT"); then
  echo "allotmint-pro not found at ${ALLOTMINT_PRO_DIR:-$REPO_ROOT/../allotmint-pro}; clone it there or set ALLOTMINT_PRO_DIR." >&2
  exit 1
fi

if port_in_use "$PORT"; then
  echo "Port $PORT is already in use (an MCP server may already be running); pass another port or stop it first." >&2
  exit 1
fi

echo "Starting the MCP server at http://localhost:$PORT/mcp (allotmint-pro: $PRO_DIR)" >&2
run_mcp_server "$REPO_ROOT" "$PRO_DIR" "$PORT"
