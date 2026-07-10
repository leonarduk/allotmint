#!/usr/bin/env bats
# Unit tests for .github/scripts/reconcile_changes_requested_label.sh, covering
# the ENABLE_CLAUDE/ENABLE_GPT/ENABLE_DEEPSEEK enable/disable branching that
# decides which reviewers' check-run conclusions are required before the
# 'Changes Requested' label is removed. See #4236.

SCRIPT="$BATS_TEST_DIRNAME/../../.github/scripts/reconcile_changes_requested_label.sh"

setup() {
  FAKE_BIN="$(mktemp -d)"
  CALL_LOG="$(mktemp)"
  PATH="$FAKE_BIN:$PATH"
  export GH_TOKEN="fake-token"
  export REPO="owner/repo"
  export CALL_LOG
}

teardown() {
  rm -rf "$FAKE_BIN"
  rm -f "$CALL_LOG"
}

# Writes a fake `gh` executable that stands in for the real GitHub CLI.
# HEAD_SHA is what `gh pr view --json headRefOid` returns.
# HAS_LABEL is what `gh pr view --json labels` reports ("true"/"false").
# Remaining args are NAME=CONCLUSION pairs describing the fake check-runs
# available for that head SHA (e.g. "Claude AI code review=success").
# Every invocation is appended to $CALL_LOG for later assertions.
write_fake_gh() {
  local head_sha="$1"
  local has_label="$2"
  shift 2

  cat > "$FAKE_BIN/gh" <<'HEADER'
#!/usr/bin/env bash
echo "$*" >> "$CALL_LOG"
HEADER

  {
    echo "case \"\$1 \$2\" in"
    echo "  'pr view')"
    echo "    if [[ \"\$*\" == *'--json headRefOid'* ]]; then"
    echo "      echo '${head_sha}'"
    echo "    elif [[ \"\$*\" == *'--json labels'* ]]; then"
    echo "      echo '${has_label}'"
    echo "    fi"
    echo "    ;;"
    echo "  'api repos/${REPO}/commits/${head_sha}/check-runs')"
    printf '    JQ_ARG="$*"\n'
    for pair in "$@"; do
      local name="${pair%=*}"
      local conclusion="${pair##*=}"
      printf '    if [[ "$JQ_ARG" == *%s* ]]; then echo %s; exit 0; fi\n' \
        "$(printf '%q' "\"$name\"")" "$(printf '%q' "$conclusion")"
    done
    echo '    echo "pending"'
    echo '    ;;'
    echo "  'pr edit'|'pr comment')"
    echo '    ;;'
    echo 'esac'
  } >> "$FAKE_BIN/gh"

  chmod +x "$FAKE_BIN/gh"
}

@test "default (all unset) requires all three reviewers' conclusions" {
  write_fake_gh "sha123" "true" \
    "Claude AI code review=success" \
    "GPT AI code review=success" \
    "DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"enabled reviewers: Claude AI code review GPT AI code review DeepSeek AI code review"* ]]
  [[ "$output" == *"Claude AI code review: success"* ]]
  [[ "$output" == *"GPT AI code review: success"* ]]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "ENABLE_GPT=false excludes GPT from the required set" {
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true" \
    "Claude AI code review=success" \
    "DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"enabled reviewers: Claude AI code review DeepSeek AI code review"* ]]
  [[ "$output" != *"GPT AI code review:"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "a disabled reviewer's pending check-run does not block label removal" {
  export ENABLE_GPT="false"
  # The GPT check-run doesn't exist at all (job skipped), which the fake gh
  # reports as "pending" -- but since GPT is disabled it must not be queried
  # or counted against ALL_SUCCESS.
  write_fake_gh "sha123" "true" \
    "Claude AI code review=success" \
    "DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "all disabled reviewers exits cleanly without requiring any conclusion" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  export ENABLE_DEEPSEEK="false"
  write_fake_gh "sha123" "true"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"No AI reviewers are enabled; nothing to reconcile for PR #42."* ]]
  ! grep -q -- "check-runs" "$CALL_LOG"
  ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "one enabled reviewer still pending leaves the label in place" {
  write_fake_gh "sha123" "true" \
    "Claude AI code review=success" \
    "GPT AI code review=pending" \
    "DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"leaving 'Changes Requested' label as-is"* ]]
  ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "an enabled reviewer with no check-run at all is treated as pending" {
  # No entry provided for DeepSeek -> fake gh falls through to "pending".
  write_fake_gh "sha123" "true" \
    "Claude AI code review=success" \
    "GPT AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: pending"* ]]
  [[ "$output" == *"leaving 'Changes Requested' label as-is"* ]]
  ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "all enabled reviewers passing but label absent is a no-op" {
  write_fake_gh "sha123" "false" \
    "Claude AI code review=success" \
    "GPT AI code review=success" \
    "DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"Label not present on PR #42; nothing to remove."* ]]
  ! grep -q -- "--remove-label" "$CALL_LOG"
}
