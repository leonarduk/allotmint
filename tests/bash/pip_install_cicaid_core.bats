#!/usr/bin/env bats
# Unit tests for .github/scripts/pip_install_cicaid_core.sh, covering the
# CICAID_CORE_TOKEN validation and the git-credential configure/cleanup wrapping
# introduced to fix the cicaid-devtools 404 (#6754). Raised by the DeepSeek
# review on PR #6755: the original workflow steps had no pre-flight check for a
# missing/empty token (confusing auth failure instead) and left the token
# sitting in ~/.gitconfig for the rest of the job.

SCRIPT="$BATS_TEST_DIRNAME/../../.github/scripts/pip_install_cicaid_core.sh"

setup() {
  # Isolate git's global config to a scratch HOME so tests never touch the
  # real developer/CI ~/.gitconfig and leftover state can't leak between tests.
  FAKE_HOME="$(mktemp -d)"
  HOME="$FAKE_HOME"
  export HOME
}

teardown() {
  rm -rf "$FAKE_HOME"
}

config_key() {
  echo "url.https://x-access-token:${1}@github.com/leonarduk/cicaid-core.insteadOf"
}

@test "fails with a clear error when CICAID_CORE_TOKEN is unset" {
  unset CICAID_CORE_TOKEN || true

  run bash "$SCRIPT" echo "should not run"

  [ "$status" -eq 1 ]
  [[ "$output" == *"CICAID_CORE_TOKEN is empty or unset"* ]]
  [[ "$output" == *"#6754"* ]]
}

@test "fails with a clear error when CICAID_CORE_TOKEN is empty" {
  export CICAID_CORE_TOKEN=""

  run bash "$SCRIPT" echo "should not run"

  [ "$status" -eq 1 ]
  [[ "$output" == *"CICAID_CORE_TOKEN is empty or unset"* ]]
}

@test "configures the git credential rewrite before running the wrapped command" {
  export CICAID_CORE_TOKEN="fake-token-123"

  run bash "$SCRIPT" bash -c 'git config --global --get "url.https://x-access-token:${CICAID_CORE_TOKEN}@github.com/leonarduk/cicaid-core.insteadOf"'

  [ "$status" -eq 0 ]
  [ "$output" = "https://github.com/leonarduk/cicaid-core" ]
}

@test "propagates the wrapped command's exit code" {
  export CICAID_CORE_TOKEN="fake-token-123"

  run bash "$SCRIPT" bash -c 'exit 7'

  [ "$status" -eq 7 ]
}

@test "unsets the git credential after the wrapped command succeeds" {
  export CICAID_CORE_TOKEN="fake-token-123"

  bash "$SCRIPT" true

  run git config --global --get "$(config_key "fake-token-123")"
  [ "$status" -ne 0 ]
}

@test "unsets the git credential even when the wrapped command fails" {
  export CICAID_CORE_TOKEN="fake-token-123"

  run bash "$SCRIPT" bash -c 'exit 1'
  [ "$status" -eq 1 ]

  run git config --global --get "$(config_key "fake-token-123")"
  [ "$status" -ne 0 ]
}

@test "does not leak the token itself into stdout/stderr" {
  export CICAID_CORE_TOKEN="super-secret-token-xyz"

  run bash "$SCRIPT" echo "install ran"

  [ "$status" -eq 0 ]
  [[ "$output" != *"super-secret-token-xyz"* ]]
}
