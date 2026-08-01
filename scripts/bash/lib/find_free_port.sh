#!/usr/bin/env bash
# Shared helper for local dev scripts: find the first free TCP port at or
# after a starting port. Used to let multiple local backend/frontend
# instances run concurrently without clashing (see #5760).

# Returns 0 (true) if something is already listening on 127.0.0.1:$1.
# Uses fd 6 (not 3) and confines it to a subshell: bats-core reserves fd 3
# for its own internal signaling, and closing it from the test process
# (rather than a subshell) corrupts the harness for later tests.
port_in_use() {
  local port="$1"
  (exec 6<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null
}

# Prints the first free port at or after $1 (max 100 attempts), falling
# back to the starting port if none is found.
find_free_port() {
  local port="$1"
  local max_tries="${2:-100}"
  local tries=0
  while port_in_use "$port" && [[ $tries -lt $max_tries ]]; do
    port=$((port + 1))
    tries=$((tries + 1))
  done
  echo "$port"
}
