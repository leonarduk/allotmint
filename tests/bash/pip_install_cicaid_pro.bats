#!/usr/bin/env bats
# Unit tests for .github/scripts/pip_install_cicaid_pro.sh, covering the
# CICAID_CORE_TOKEN validation and process-scoped git credential configuration
# introduced to fix the cicaid-devtools 404 (#6754). Raised by the DeepSeek
# review on PR #6755: the original workflow steps had no pre-flight check for a
# missing/empty token (confusing auth failure instead).

SCRIPT="$BATS_TEST_DIRNAME/../../.github/scripts/pip_install_cicaid_pro.sh"

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

@test "configures a process-scoped git credential rewrite" {
  export CICAID_CORE_TOKEN="fake-token-123"

  run bash "$SCRIPT" bash -c 'git config --get "url.https://x-access-token:${CICAID_CORE_TOKEN}@github.com/leonarduk/cicaid-pro.insteadOf"'

  [ "$status" -eq 0 ]
  [ "$output" = "https://github.com/leonarduk/cicaid-pro" ]
}

@test "propagates the wrapped command's exit code" {
  export CICAID_CORE_TOKEN="fake-token-123"

  run bash "$SCRIPT" bash -c 'exit 7'

  [ "$status" -eq 7 ]
}

@test "does not write the git credential to the global config" {
  export CICAID_CORE_TOKEN="fake-token-123"

  bash "$SCRIPT" true

  run grep -R "fake-token-123" "$FAKE_HOME"
  [ "$status" -ne 0 ]
}

@test "does not leak the token itself into stdout/stderr" {
  export CICAID_CORE_TOKEN="super-secret-token-xyz"

  run bash "$SCRIPT" echo "install ran"

  [ "$status" -eq 0 ]
  [[ "$output" != *"super-secret-token-xyz"* ]]
}
