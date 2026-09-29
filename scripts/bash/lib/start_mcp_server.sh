#!/usr/bin/env bash
# Shared helper for scripts/bash/run-local-api.sh: start allotmint-pro's MCP
# server in the background so the chat drawer (POST /chat) works locally
# without a second terminal. See "Running the chat (MCP) agent locally" in
# docs/CONTRIBUTOR_RUNBOOK.md.
#
# Behaviour, in order:
#   - START_MCP_SERVER=0            -> do nothing.
#   - MCP_SERVER_URL set, not plain-HTTP localhost -> do nothing (a remote
#     server, or an https:// one this plain-HTTP server can't serve).
#   - no allotmint-pro checkout     -> warn and do nothing; chat stays off.
#     Looked up at $ALLOTMINT_PRO_DIR, else the sibling ../allotmint-pro.
#   - port already listening        -> assume the server is already running.
#   - otherwise start it, logging to logs/mcp-server.log.
# MCP_SERVER_URL defaults to http://localhost:${MCP_SERVER_PORT:-8001}/mcp
# and is exported so the backend started afterwards picks it up. On start,
# MCP_SERVER_PID holds the background process for the caller to stop.

# shellcheck source=scripts/bash/lib/find_free_port.sh
source "$(dirname "${BASH_SOURCE[0]}")/find_free_port.sh"

# True if $1 is a TCP port number (1-65535).
valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && ((10#$1 >= 1 && 10#$1 <= 65535))
}

# Prints the allotmint-pro checkout for repo root $1 ($ALLOTMINT_PRO_DIR, else
# the sibling ../allotmint-pro); returns 1 if it has no MCP server package.
mcp_pro_dir() {
  local pro_dir="${ALLOTMINT_PRO_DIR:-$1/../allotmint-pro}"
  [[ -d "$pro_dir/allotmint_pro/mcp_server" ]] || return 1
  echo "$pro_dir"
}

# Runs the MCP server in the foreground on 127.0.0.1:$3, importing `backend`
# from repo root $1 and `allotmint_pro` from checkout $2. Shared by
# start_local_mcp_server (which backgrounds it) and run-mcp-server.sh.
run_mcp_server() {
  local repo_root="$1" pro_dir="$2" port="$3"
  PYTHONPATH="$repo_root:$pro_dir${PYTHONPATH:+:$PYTHONPATH}" \
    uvicorn allotmint_pro.mcp_server.app:app --host 127.0.0.1 --port "$port"
}

start_local_mcp_server() {
  local repo_root="$1"
  MCP_SERVER_PID=""

  if [[ "${START_MCP_SERVER:-1}" == "0" ]]; then
    return 0
  fi

  local url="${MCP_SERVER_URL:-}"
  local port="${MCP_SERVER_PORT:-8001}"
  if [[ -n "$url" ]]; then
    if [[ ! "$url" =~ ^http://(localhost|127\.0\.0\.1)(:([0-9]+))?(/|$) ]]; then
      return 0
    fi
    port="${BASH_REMATCH[3]:-80}"
  else
    url="http://localhost:$port/mcp"
  fi
  if ! valid_port "$port"; then
    echo "Invalid MCP server port '$port' (from MCP_SERVER_PORT or MCP_SERVER_URL; expected 1-65535); chat's MCP server not started." >&2
    return 0
  fi

  local pro_dir
  if ! pro_dir=$(mcp_pro_dir "$repo_root"); then
    echo "allotmint-pro not found at ${ALLOTMINT_PRO_DIR:-$repo_root/../allotmint-pro}; chat's MCP server not started (set ALLOTMINT_PRO_DIR, or START_MCP_SERVER=0 to silence)." >&2
    return 0
  fi

  export MCP_SERVER_URL="$url"
  if port_in_use "$port"; then
    echo "Port $port already in use; assuming the MCP server is running at $MCP_SERVER_URL" >&2
    return 0
  fi

  mkdir -p "$repo_root/logs"
  run_mcp_server "$repo_root" "$pro_dir" "$port" >>"$repo_root/logs/mcp-server.log" 2>&1 &
  MCP_SERVER_PID=$!
  echo "MCP server starting at $MCP_SERVER_URL (pid $MCP_SERVER_PID, log: logs/mcp-server.log)" >&2
}
