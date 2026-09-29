#!/usr/bin/env bats
# Unit tests for scripts/bash/lib/start_mcp_server.sh, used by
# scripts/bash/run-local-api.sh to start allotmint-pro's MCP server for the
# local chat drawer. `uvicorn` is stubbed on PATH, so nothing real starts.

LIB="$BATS_TEST_DIRNAME/../../scripts/bash/lib/start_mcp_server.sh"

setup() {
  source "$LIB"
  REPO="$BATS_TEST_TMPDIR/allotmint"
  PRO="$BATS_TEST_TMPDIR/allotmint-pro"
  mkdir -p "$REPO" "$PRO/allotmint_pro/mcp_server" "$BATS_TEST_TMPDIR/bin"
  cat >"$BATS_TEST_TMPDIR/bin/uvicorn" <<EOF
#!/usr/bin/env bash
echo "\$PYTHONPATH \$*" >"$BATS_TEST_TMPDIR/uvicorn.args"
EOF
  chmod +x "$BATS_TEST_TMPDIR/bin/uvicorn"
  PATH="$BATS_TEST_TMPDIR/bin:$PATH"
  unset MCP_SERVER_URL MCP_SERVER_PORT START_MCP_SERVER ALLOTMINT_PRO_DIR
}

wait_for_stub() {
  for _ in $(seq 1 20); do
    [[ -f "$BATS_TEST_TMPDIR/uvicorn.args" ]] && return 0
    sleep 0.1
  done
  return 1
}

@test "starts the sibling allotmint-pro MCP server and exports its URL" {
  MCP_SERVER_PORT=59301
  start_local_mcp_server "$REPO" 2>/dev/null

  [ "$MCP_SERVER_URL" = "http://localhost:59301/mcp" ]
  [ -n "$MCP_SERVER_PID" ]
  wait_for_stub
  run cat "$BATS_TEST_TMPDIR/uvicorn.args"
  [[ "$output" == "$REPO:$REPO/../allotmint-pro allotmint_pro.mcp_server.app:app --host 127.0.0.1 --port 59301" ]]
}

@test "uses the port from a localhost MCP_SERVER_URL" {
  export MCP_SERVER_URL="http://127.0.0.1:59302/mcp"
  start_local_mcp_server "$REPO" 2>/dev/null

  wait_for_stub
  run cat "$BATS_TEST_TMPDIR/uvicorn.args"
  [[ "$output" == *"--port 59302" ]]
}

@test "does nothing for a remote MCP_SERVER_URL" {
  export MCP_SERVER_URL="https://abc.lambda-url.eu-west-2.on.aws/mcp"
  start_local_mcp_server "$REPO"

  [ -z "$MCP_SERVER_PID" ]
  [ "$MCP_SERVER_URL" = "https://abc.lambda-url.eu-west-2.on.aws/mcp" ]
}

@test "does nothing for an https localhost MCP_SERVER_URL" {
  # The auto-started server is plain HTTP; serving it behind an https:// URL
  # would fail every chat turn's TLS handshake.
  export MCP_SERVER_URL="https://localhost:59304/mcp"
  start_local_mcp_server "$REPO"

  [ -z "$MCP_SERVER_PID" ]
  [ ! -f "$BATS_TEST_TMPDIR/uvicorn.args" ]
}

@test "does nothing when START_MCP_SERVER=0" {
  START_MCP_SERVER=0
  start_local_mcp_server "$REPO"

  [ -z "$MCP_SERVER_PID" ]
  [ -z "${MCP_SERVER_URL:-}" ]
}

@test "warns and leaves chat unconfigured without an allotmint-pro checkout" {
  ALLOTMINT_PRO_DIR="$BATS_TEST_TMPDIR/missing"
  run start_local_mcp_server "$REPO"

  [ "$status" -eq 0 ]
  [[ "$output" == *"allotmint-pro not found"* ]]
  [ ! -f "$BATS_TEST_TMPDIR/uvicorn.args" ]
}

@test "reuses a server already listening on the port" {
  command -v python3 >/dev/null || skip "python3 not available"
  python3 -m http.server 59303 --bind 127.0.0.1 >/dev/null 2>&1 &
  local server_pid=$!
  for _ in $(seq 1 20); do
    port_in_use 59303 && break
    sleep 0.1
  done

  MCP_SERVER_PORT=59303
  start_local_mcp_server "$REPO" 2>/dev/null
  kill "$server_pid"

  [ -z "$MCP_SERVER_PID" ]
  [ "$MCP_SERVER_URL" = "http://localhost:59303/mcp" ]
  [ ! -f "$BATS_TEST_TMPDIR/uvicorn.args" ]
}
