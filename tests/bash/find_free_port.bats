#!/usr/bin/env bats
# Unit tests for scripts/bash/lib/find_free_port.sh, used by
# scripts/bash/run-local-api.sh to give each local dev instance a
# non-clashing backend port (see #5760).

LIB="$BATS_TEST_DIRNAME/../../scripts/bash/lib/find_free_port.sh"

setup() {
  source "$LIB"
}

@test "find_free_port returns the starting port when it is free" {
  # Extremely unlikely to be bound in a CI/test environment.
  run find_free_port 59123
  [ "$status" -eq 0 ]
  [ "$output" = "59123" ]
}

@test "find_free_port skips a port that is already in use" {
  command -v python3 >/dev/null || skip "python3 not available"

  # A real accepting server, not a bare listen() backlog — a socket that
  # never accept()s only tolerates one probe connection before refusing
  # the rest, which would make this test flaky rather than the code buggy.
  python3 -m http.server 59200 --bind 127.0.0.1 >/dev/null 2>&1 &
  local server_pid=$!

  for _ in $(seq 1 20); do
    port_in_use 59200 && break
    sleep 0.1
  done

  run find_free_port 59200
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true

  [ "$status" -eq 0 ]
  [ "$output" = "59201" ]
}
