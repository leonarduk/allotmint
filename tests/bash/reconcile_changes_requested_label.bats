#!/usr/bin/env bats
# Unit tests for .github/scripts/reconcile_changes_requested_label.sh, covering
# the ENABLE_CLAUDE/ENABLE_GPT/ENABLE_DEEPSEEK enable/disable branching that
# decides which reviewers' check-run conclusions are required before the
# 'Changes Requested' label is removed (#4236), plus check-run name matching
# for the reusable-workflow "ai-review / " prefix and skipped-duplicate
# handling (PR #8598).

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
# Remaining args describe the fake check-runs for that head SHA, each as
# NAME=CONCLUSION or NAME=CONCLUSION@STARTED_AT (e.g.
# "ai-review / Claude AI code review=success@2026-01-01T00:00:05Z").
# CONCLUSION "pending" emits an in-progress run (null conclusion) and
# "queued" a not-yet-started run (null conclusion and null started_at). The
# check-runs endpoint prints one compact JSON object per run -- what the real
# `gh api --paginate --jq '.check_runs[] | {...}'` call produces -- so the
# script's own jq filtering is exercised for real.
# Every invocation is appended to $CALL_LOG for later assertions.
write_fake_gh() {
  local head_sha="$1"
  local has_label="$2"
  shift 2

  local runs_file="$FAKE_BIN/check_runs.jsonl"
  : > "$runs_file"
  local pair name rest conclusion started_at
  for pair in "$@"; do
    name="${pair%=*}"
    rest="${pair##*=}"
    conclusion="${rest%%@*}"
    started_at="2026-01-01T00:00:00Z"
    if [[ "$rest" == *@* ]]; then
      started_at="${rest#*@}"
    fi
    if [ "$conclusion" = "queued" ]; then
      printf '{"name":"%s","status":"queued","conclusion":null,"started_at":null}\n' \
        "$name" >> "$runs_file"
    elif [ "$conclusion" = "pending" ]; then
      printf '{"name":"%s","status":"in_progress","conclusion":null,"started_at":"%s"}\n' \
        "$name" "$started_at" >> "$runs_file"
    else
      printf '{"name":"%s","status":"completed","conclusion":"%s","started_at":"%s"}\n' \
        "$name" "$conclusion" "$started_at" >> "$runs_file"
    fi
  done

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
    echo "    cat '${runs_file}'"
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

@test "ENABLE_CLAUDE=false excludes Claude from the required set" {
  export ENABLE_CLAUDE="false"
  write_fake_gh "sha123" "true" \
    "GPT AI code review=success" \
    "DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"enabled reviewers: GPT AI code review DeepSeek AI code review"* ]]
  [[ "$output" != *"Claude AI code review:"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "ENABLE_DEEPSEEK=false excludes DeepSeek from the required set" {
  export ENABLE_DEEPSEEK="false"
  write_fake_gh "sha123" "true" \
    "Claude AI code review=success" \
    "GPT AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"enabled reviewers: Claude AI code review GPT AI code review"* ]]
  [[ "$output" != *"DeepSeek AI code review:"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "two disabled reviewers leaves only the remaining one's conclusion required" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  # Only DeepSeek is enabled and it's still pending, so the label must stay.
  write_fake_gh "sha123" "true" \
    "DeepSeek AI code review=pending"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"enabled reviewers: DeepSeek AI code review"* ]]
  [[ "$output" == *"leaving 'Changes Requested' label as-is"* ]]
  ! grep -q -- "--remove-label" "$CALL_LOG"
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

@test "check-run names prefixed by the reusable-workflow caller job still match" {
  # Real check-runs are named "<caller job> / <job name>" because the reviews
  # run inside _ai-pr-review.yml via workflow_call (PR #8598 regression).
  write_fake_gh "sha123" "true"     "ai-review / Claude AI code review=success"     "ai-review / GPT AI code review=success"     "ai-review / DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"Claude AI code review: success"* ]]
  [[ "$output" == *"GPT AI code review: success"* ]]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "a later skipped duplicate does not override an earlier success" {
  # Mirrors PR #8598 head ec0f1fef: success at 20:50:51Z, then a skipped
  # duplicate of the same job at 20:50:56Z.
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true"     "ai-review / DeepSeek AI code review=success@2026-10-03T20:50:51Z"     "ai-review / DeepSeek AI code review=skipped@2026-10-03T20:50:56Z"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "only skipped or neutral runs for a reviewer count as pending" {
  write_fake_gh "sha123" "true"     "ai-review / Claude AI code review=success"     "ai-review / GPT AI code review=success"     "ai-review / DeepSeek AI code review=skipped@2026-01-01T00:00:01Z"     "ai-review / DeepSeek AI code review=neutral@2026-01-01T00:00:02Z"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: pending"* ]]
  [[ "$output" == *"leaving 'Changes Requested' label as-is"* ]]
  ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "the latest non-skipped run wins when a reviewer re-ran" {
  write_fake_gh "sha123" "true"     "ai-review / Claude AI code review=success"     "ai-review / GPT AI code review=success"     "ai-review / DeepSeek AI code review=success@2026-01-01T00:00:01Z"     "ai-review / DeepSeek AI code review=failure@2026-01-01T00:00:09Z"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: failure"* ]]
  ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "a check-run whose name merely ends with the reviewer name does not match" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true"     "Legacy DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: pending"* ]]
  ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "a queued re-run (null started_at) is pending, not shadowed by an older success" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true"     "ai-review / DeepSeek AI code review=success@2026-01-01T00:00:01Z"     "ai-review / DeepSeek AI code review=queued"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: pending"* ]]
  ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "an in-progress re-run is pending, not shadowed by an older success" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true"     "ai-review / DeepSeek AI code review=success@2026-01-01T00:00:01Z"     "ai-review / DeepSeek AI code review=pending@2026-01-01T00:00:09Z"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: pending"* ]]
  ! grep -q -- "--remove-label" "$CALL_LOG"
}
