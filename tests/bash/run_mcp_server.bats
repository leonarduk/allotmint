#!/usr/bin/env bats
# Tests for scripts/bash/run-mcp-server.sh, the standalone foreground MCP
# server launcher. `uvicorn` is stubbed on PATH, so nothing real starts.

SCRIPT="$BATS_TEST_DIRNAME/../../scripts/bash/run-mcp-server.sh"
REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

setup() {
  PRO="$BATS_TEST_TMPDIR/allotmint-pro"
  mkdir -p "$PRO/allotmint_pro/mcp_server" "$BATS_TEST_TMPDIR/bin"
  cat >"$BATS_TEST_TMPDIR/bin/uvicorn" <<'STUB'
#!/usr/bin/env bash
echo "PYTHONPATH=$PYTHONPATH"
echo "ARGS=$*"
echo "FROM_ENV_FILE=${FROM_ENV_FILE:-}"
STUB
  chmod +x "$BATS_TEST_TMPDIR/bin/uvicorn"
  printf 'FROM_ENV_FILE=loaded\n' >"$BATS_TEST_TMPDIR/shared.env"
  export PATH="$BATS_TEST_TMPDIR/bin:$PATH"
  export ALLOTMINT_PRO_DIR="$PRO"
  export ALLOTMINT_ENV_FILE="$BATS_TEST_TMPDIR/shared.env"
  unset MCP_SERVER_PORT PYTHONPATH
}

@test "runs the MCP server in the foreground on the default port" {
  # The launcher refuses a port something already listens on, and this test
  # needs the real default (8001) - which a developer's own running MCP
  # server holds. Skip rather than fail on such a machine; a clean CI runner
  # always has it free.
  # shellcheck source=scripts/bash/lib/find_free_port.sh
  source "$REPO_ROOT/scripts/bash/lib/find_free_port.sh"
  if port_in_use 8001; then
    skip "port 8001 is already in use on this machine"
  fi

  run bash "$SCRIPT"

  [ "$status" -eq 0 ]
  [[ "$output" == *"PYTHONPATH=$REPO_ROOT:$PRO"* ]]
  [[ "$output" == *"ARGS=allotmint_pro.mcp_server.app:app --host 127.0.0.1 --port 8001"* ]]
}

@test "takes the port from the argument, then MCP_SERVER_PORT" {
  run bash "$SCRIPT" 59311
  [[ "$output" == *"--port 59311"* ]]

  MCP_SERVER_PORT=59312 run bash "$SCRIPT"
  [[ "$output" == *"--port 59312"* ]]
}

@test "loads the shared env file like the backend scripts" {
  [ ! -f "$REPO_ROOT/.env" ] || skip "a repo-local .env takes precedence"
  run bash "$SCRIPT" 59313

  [[ "$output" == *"FROM_ENV_FILE=loaded"* ]]
}

@test "fails clearly without an allotmint-pro checkout" {
  ALLOTMINT_PRO_DIR="$BATS_TEST_TMPDIR/missing" run bash "$SCRIPT"

  [ "$status" -eq 1 ]
  [[ "$output" == *"allotmint-pro not found at $BATS_TEST_TMPDIR/missing"* ]]
  [[ "$output" != *"ARGS="* ]]
}

@test "rejects a non-numeric or out-of-range port argument" {
  for bad in abc 0 65536 99999; do
    run bash "$SCRIPT" "$bad"
    [ "$status" -eq 2 ]
    [[ "$output" == *"Invalid port '$bad'"* ]]
    [[ "$output" == *"Usage:"* ]]
    [[ "$output" != *"ARGS="* ]]
  done
}

@test "rejects an invalid MCP_SERVER_PORT" {
  MCP_SERVER_PORT=eighty run bash "$SCRIPT"

  [ "$status" -eq 2 ]
  [[ "$output" == *"Invalid port 'eighty'"* ]]
}

@test "takes MCP_SERVER_PORT from the shared env file" {
  [ ! -f "$REPO_ROOT/.env" ] || skip "a repo-local .env takes precedence"
  printf 'MCP_SERVER_PORT=59315\n' >>"$ALLOTMINT_ENV_FILE"
  run bash "$SCRIPT"

  [[ "$output" == *"--port 59315"* ]]
}

@test "refuses a port that is already in use" {
  command -v python3 >/dev/null || skip "python3 not available"
  python3 -m http.server 59314 --bind 127.0.0.1 >/dev/null 2>&1 &
  local server_pid=$!
  source "$BATS_TEST_DIRNAME/../../scripts/bash/lib/find_free_port.sh"
  for _ in $(seq 1 20); do
    port_in_use 59314 && break
    sleep 0.1
  done

  run bash "$SCRIPT" 59314
  kill "$server_pid"

  [ "$status" -eq 1 ]
  [[ "$output" == *"Port 59314 is already in use"* ]]
  [[ "$output" != *"ARGS="* ]]
}
