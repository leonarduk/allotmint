#!/usr/bin/env bats
# Unit tests for scripts/bash/fetch-cloudwatch-logs.sh covering the
# AccessDenied, empty-result, and success paths documented at the top of
# the script under test. See #3807, #4075, #4076.

SCRIPT="$BATS_TEST_DIRNAME/../../scripts/bash/fetch-cloudwatch-logs.sh"

setup() {
  FAKE_BIN="$(mktemp -d)"
  PATH="$FAKE_BIN:$PATH"
}

teardown() {
  rm -rf "$FAKE_BIN"
}

# Writes a fake `aws` executable to $FAKE_BIN that stands in for
# `aws logs filter-log-events ...`. The script under test only inspects
# stdout (see its "Capture stdout ... separately from stderr" comment), so
# STDOUT_TEXT is what fetch-cloudwatch-logs.sh actually sees.
write_fake_aws() {
  local stdout_text="$1"
  local exit_code="$2"
  cat > "$FAKE_BIN/aws" <<EOF
#!/usr/bin/env bash
printf '%s\n' "$stdout_text"
exit $exit_code
EOF
  chmod +x "$FAKE_BIN/aws"
}

@test "exits 0 and emits a scoped warning on AccessDeniedException" {
  write_fake_aws "An error occurred (AccessDeniedException) when calling the FilterLogEvents operation" 1

  run bash "$SCRIPT" "/aws/lambda/my-fn" 600

  [ "$status" -eq 0 ]
  [[ "$output" == *"::warning::logs:FilterLogEvents denied for /aws/lambda/my-fn; CloudWatch logs not available (see #3742)"* ]]
}

@test "exits 0 and emits a generic warning on a non-AccessDenied API error" {
  write_fake_aws "An error occurred (ThrottlingException) when calling the FilterLogEvents operation" 1

  run bash "$SCRIPT" "/aws/lambda/my-fn" 600

  [ "$status" -eq 0 ]
  [[ "$output" == *"::warning::Failed to fetch CloudWatch logs for /aws/lambda/my-fn:"* ]]
  [[ "$output" == *"ThrottlingException"* ]]
}

@test "prints a friendly message when the log group has no matching events" {
  write_fake_aws "None" 0

  run bash "$SCRIPT" "/aws/lambda/my-fn" 600

  [ "$status" -eq 0 ]
  [ "$output" = "(no log events found)" ]
}

@test "filters out None entries and prints real log messages on success" {
  write_fake_aws "$(printf 'None\nFirst log line\nSecond log line')" 0

  run bash "$SCRIPT" "/aws/lambda/my-fn" 600

  [ "$status" -eq 0 ]
  [[ "$output" != *"None"* ]]
  [[ "$output" == *"First log line"* ]]
  [[ "$output" == *"Second log line"* ]]
}

@test "requires a log group name argument" {
  run bash "$SCRIPT"

  [ "$status" -ne 0 ]
  [[ "$output" == *"log group name required"* ]]
}

@test "requires a lookback window argument" {
  run bash "$SCRIPT" "/aws/lambda/my-fn"

  [ "$status" -ne 0 ]
  [[ "$output" == *"lookback window in seconds required"* ]]
}
