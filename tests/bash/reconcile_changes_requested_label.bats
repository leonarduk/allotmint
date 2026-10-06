#!/usr/bin/env bats
# Unit tests for .github/scripts/reconcile_changes_requested_label.sh, covering
# the ENABLE_CLAUDE/ENABLE_GPT/ENABLE_DEEPSEEK enable/disable branching that
# decides which reviewers' check-run conclusions are required before the
# 'Changes Requested' label is removed (see #4236), and how the latest verdict is
# picked from the check-runs for the head SHA (see #8812).

bats_require_minimum_version 1.5.0

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
# CHECK_RUNS_FILE holds one or more JSON documents, each shaped like one page
# of the check-runs API response ({"check_runs": [...]}). For the check-runs
# call, the fake runs the script's own --jq filter through the real `jq` on
# each document separately, the same way `gh api --paginate --jq` filters
# each page. So the tests exercise the actual filter, not a string match on
# it.
# Every invocation is appended to $CALL_LOG for later assertions.
write_fake_gh_json() {
  export FAKE_HEAD_SHA="$1"
  export FAKE_HAS_LABEL="$2"
  export FAKE_CHECK_RUNS_FILE="$3"

  cat > "$FAKE_BIN/gh" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "$CALL_LOG"
case "$1 $2" in
  'pr view')
    if [[ "$*" == *'--json headRefOid'* ]]; then
      echo "$FAKE_HEAD_SHA"
    elif [[ "$*" == *'--json labels'* ]]; then
      echo "$FAKE_HAS_LABEL"
    fi
    ;;
  "api repos/${REPO}/commits/${FAKE_HEAD_SHA}/check-runs"*)
    jq_expr=""
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "--jq" ]; then
        jq_expr="$2"
        break
      fi
      shift
    done
    jq -r "$jq_expr" "$FAKE_CHECK_RUNS_FILE"
    ;;
  'pr edit'|'pr comment')
    ;;
esac
FAKE

  chmod +x "$FAKE_BIN/gh"
}

# Convenience wrapper over write_fake_gh_json. The remaining args are
# NAME=CONCLUSION pairs, each becoming one check-run, with started_at values
# increasing in argument order (e.g. "Claude AI code review=success").
# CONCLUSION "pending" becomes an in-progress run with no conclusion. Any
# other value becomes a completed run with that conclusion.
write_fake_gh() {
  local head_sha="$1"
  local has_label="$2"
  shift 2

  local runs="" sep="" i=0 pair name conclusion status conclusion_json
  for pair in "$@"; do
    i=$((i + 1))
    name="${pair%=*}"
    conclusion="${pair##*=}"
    status="completed"
    conclusion_json="\"${conclusion}\""
    if [ "$conclusion" = "pending" ]; then
      status="in_progress"
      conclusion_json="null"
    fi
    runs+="${sep}{\"id\": ${i}, \"name\": \"${name}\", \"status\": \"${status}\","
    runs+=" \"conclusion\": ${conclusion_json},"
    runs+=" \"started_at\": \"2026-10-03T20:50:$(printf '%02d' "$i")Z\"}"
    sep=", "
  done

  echo "{\"check_runs\": [${runs}]}" > "$FAKE_BIN/check_runs.json"
  write_fake_gh_json "$head_sha" "$has_label" "$FAKE_BIN/check_runs.json"
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
  run ! grep -q -- "--remove-label" "$CALL_LOG"
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
  run ! grep -q -- "check-runs" "$CALL_LOG"
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "one enabled reviewer still pending leaves the label in place" {
  write_fake_gh "sha123" "true" \
    "Claude AI code review=success" \
    "GPT AI code review=pending" \
    "DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"leaving 'Changes Requested' label as-is"* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
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
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "all enabled reviewers passing but label absent is a no-op" {
  write_fake_gh "sha123" "false" \
    "Claude AI code review=success" \
    "GPT AI code review=success" \
    "DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"Label not present on PR #42; nothing to remove."* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

# --- #8812: check-run name matching and duplicate-run selection -------------

@test "reusable-workflow prefixed check name matches the reviewer (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true" \
    "ai-review / DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "a check name that merely ends with the reviewer name does not match (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  # Only "<job> / <name>" or the bare name count -- not any string that
  # happens to end with the reviewer's name.
  write_fake_gh "sha123" "true" \
    "ai-review / Not DeepSeek AI code review=success" \
    "XDeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: pending"* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "success followed by a later skipped duplicate counts as success (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  # Mirrors PR #8598 @ ec0f1fef: the real review succeeded at 20:50:51Z, and a
  # no-op labeled-event run's skipped job started later, at 20:50:56Z (and is
  # listed first by the API).
  cat > "$FAKE_BIN/runs.json" <<'JSON'
{"check_runs": [
  {"id": 2, "name": "ai-review / DeepSeek AI code review", "status": "completed", "conclusion": "skipped", "started_at": "2026-10-03T20:50:56Z"},
  {"id": 1, "name": "ai-review / DeepSeek AI code review", "status": "completed", "conclusion": "success", "started_at": "2026-10-03T20:50:51Z"}
]}
JSON
  write_fake_gh_json "sha123" "true" "$FAKE_BIN/runs.json"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "later neutral and cancelled duplicates are ignored too (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true" \
    "ai-review / DeepSeek AI code review=success" \
    "ai-review / DeepSeek AI code review=neutral" \
    "ai-review / DeepSeek AI code review=cancelled"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "a real failure keeps the label even with a later skipped duplicate (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true" \
    "ai-review / DeepSeek AI code review=failure" \
    "ai-review / DeepSeek AI code review=skipped"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: failure"* ]]
  [[ "$output" == *"leaving 'Changes Requested' label as-is"* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "an enabled reviewer with only skipped runs is treated as pending (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true" \
    "ai-review / DeepSeek AI code review=skipped"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: pending"* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "a later successful re-run supersedes an earlier failure (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true" \
    "ai-review / DeepSeek AI code review=failure" \
    "ai-review / DeepSeek AI code review=success"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "a later failed re-review supersedes an earlier success (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true" \
    "ai-review / DeepSeek AI code review=success" \
    "ai-review / DeepSeek AI code review=failure"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: failure"* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "an in-progress re-review after a success keeps the label until it finishes (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  write_fake_gh "sha123" "true" \
    "ai-review / DeepSeek AI code review=success" \
    "ai-review / DeepSeek AI code review=pending"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: pending"* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "a queued run with no started_at counts as the latest, pending (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  cat > "$FAKE_BIN/runs.json" <<'JSON'
{"check_runs": [
  {"id": 1, "name": "ai-review / DeepSeek AI code review", "status": "completed", "conclusion": "success", "started_at": "2026-10-03T20:50:51Z"},
  {"id": 2, "name": "ai-review / DeepSeek AI code review", "status": "queued", "conclusion": null, "started_at": null}
]}
JSON
  write_fake_gh_json "sha123" "true" "$FAKE_BIN/runs.json"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: pending"* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "the verdict is chosen across all paginated pages, not per page (#8812)" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  # Two pages: the skipped duplicate is on page 1 and the real success is on
  # page 2. The old per-page `sort_by | last` reduction printed one value per
  # page, so the result never equalled "success".
  cat > "$FAKE_BIN/runs.json" <<'JSON'
{"check_runs": [
  {"id": 2, "name": "ai-review / DeepSeek AI code review", "status": "completed", "conclusion": "skipped", "started_at": "2026-10-03T20:50:56Z"},
  {"id": 3, "name": "CodeQL", "status": "completed", "conclusion": "success", "started_at": "2026-10-03T20:51:17Z"}
]}
{"check_runs": [
  {"id": 1, "name": "ai-review / DeepSeek AI code review", "status": "completed", "conclusion": "success", "started_at": "2026-10-03T20:50:51Z"}
]}
JSON
  write_fake_gh_json "sha123" "true" "$FAKE_BIN/runs.json"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "all three prefixed reviewers passing removes the label (#8812)" {
  write_fake_gh "sha123" "true" \
    "ai-review / Claude AI code review=success" \
    "ai-review / GPT AI code review=success" \
    "ai-review / DeepSeek AI code review=success" \
    "ai-review / DeepSeek AI code review=skipped"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"Claude AI code review: success"* ]]
  [[ "$output" == *"GPT AI code review: success"* ]]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

# --- inline reconcile from the approving review job -------------------------
# _ai-pr-review.yml calls the script while its own check-run is still in
# progress, passing ASSUME_SUCCESS_CHECK/REVIEWED_SHA for its own verdict.

@test "the calling reviewer's in-progress run counts as success for the reviewed head" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  export ASSUME_SUCCESS_CHECK="DeepSeek AI code review"
  export REVIEWED_SHA="sha123"
  write_fake_gh "sha123" "true" \
    "ai-review / DeepSeek AI code review=pending"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"Counting DeepSeek AI code review as success"* ]]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  grep -q -- "--remove-label Changes Requested" "$CALL_LOG"
}

@test "the assumption is ignored when a newer commit has been pushed" {
  export ENABLE_CLAUDE="false"
  export ENABLE_GPT="false"
  export ASSUME_SUCCESS_CHECK="DeepSeek AI code review"
  export REVIEWED_SHA="oldsha"
  write_fake_gh "newsha" "true" \
    "ai-review / DeepSeek AI code review=pending"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"Not assuming DeepSeek AI code review"* ]]
  [[ "$output" == *"DeepSeek AI code review: pending"* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "the assumption covers only the calling reviewer, not the others" {
  export ENABLE_GPT="false"
  export ASSUME_SUCCESS_CHECK="DeepSeek AI code review"
  export REVIEWED_SHA="sha123"
  write_fake_gh "sha123" "true" \
    "ai-review / DeepSeek AI code review=pending" \
    "ai-review / Claude AI code review=pending"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"DeepSeek AI code review: success"* ]]
  [[ "$output" == *"Claude AI code review: pending"* ]]
  [[ "$output" == *"leaving 'Changes Requested' label as-is"* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}

@test "the assumption cannot override another reviewer's failure" {
  export ENABLE_GPT="false"
  export ASSUME_SUCCESS_CHECK="DeepSeek AI code review"
  export REVIEWED_SHA="sha123"
  write_fake_gh "sha123" "true" \
    "ai-review / DeepSeek AI code review=pending" \
    "ai-review / Claude AI code review=failure"

  run bash "$SCRIPT" 42

  [ "$status" -eq 0 ]
  [[ "$output" == *"Claude AI code review: failure"* ]]
  run ! grep -q -- "--remove-label" "$CALL_LOG"
}
