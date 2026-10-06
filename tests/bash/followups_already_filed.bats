#!/usr/bin/env bats
# Unit tests for .github/scripts/followups_already_filed.sh, which gates the
# "Create follow-up issues" step of _ai-pr-review.yml so re-reviews of a PR
# don't file duplicate follow-up issues.

SCRIPT="$BATS_TEST_DIRNAME/../../.github/scripts/followups_already_filed.sh"

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

# Fake `gh api` that applies the script's own --jq filter to each JSON page in
# $1 (one page per line), mimicking `gh api --paginate --jq`. FAKE_GH_FAIL=1
# makes it exit non-zero instead.
write_fake_gh() {
  export FAKE_PAGES_FILE="$1"
  cat > "$FAKE_BIN/gh" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "$CALL_LOG"
if [ "${FAKE_GH_FAIL:-0}" = "1" ]; then
  echo "HTTP 502" >&2
  exit 1
fi
jq_expr=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--jq" ]; then jq_expr="$2"; break; fi
  shift
done
while IFS= read -r page; do
  [ -n "$page" ] && jq -r "$jq_expr" <<<"$page"
done < "$FAKE_PAGES_FILE"
FAKE
  chmod +x "$FAKE_BIN/gh"
}

pages() {
  local f
  f="$(mktemp)"
  printf '%s\n' "$@" > "$f"
  echo "$f"
}

@test "skips when a follow-up for this PR already exists" {
  write_fake_gh "$(pages '[{"number":1,"body":"x\n\n_Follow-up from AI review of PR #42._"}]')"
  run bash "$SCRIPT" 42
  [ "$status" -eq 0 ]
  [[ "$output" == *"skip=true"* ]]
}

@test "matches the fallback body written when the LLM call fails" {
  write_fake_gh "$(pages '[{"number":1,"body":"Follow-up suggested by AI review of PR #42."}]')"
  run bash "$SCRIPT" 42
  [[ "$output" == *"skip=true"* ]]
}

@test "files when no follow-up for this PR exists" {
  write_fake_gh "$(pages '[{"number":1,"body":"_Follow-up from AI review of PR #41._"}]')"
  run bash "$SCRIPT" 42
  [ "$status" -eq 0 ]
  [ "$output" = "skip=false" ]
}

@test "does not treat a longer PR number as a match" {
  write_fake_gh "$(pages '[{"number":1,"body":"_Follow-up from AI review of PR #420._"}]')"
  run bash "$SCRIPT" 42
  [ "$output" = "skip=false" ]
}

@test "finds a match on a later page and ignores pull requests" {
  write_fake_gh "$(pages \
    '[{"number":1,"body":"unrelated"},{"number":2,"pull_request":{},"body":"_Follow-up from AI review of PR #42._"}]' \
    '[{"number":3,"body":null},{"number":4,"body":"_Follow-up from AI review of PR #42._"}]')"
  run bash "$SCRIPT" 42
  [[ "$output" == *"skip=true"* ]]
}

@test "a PR body mentioning the marker is not counted" {
  write_fake_gh "$(pages '[{"number":2,"pull_request":{},"body":"_Follow-up from AI review of PR #42._"}]')"
  run bash "$SCRIPT" 42
  [ "$output" = "skip=false" ]
}

@test "passes SINCE through to the API query" {
  write_fake_gh "$(pages '[]')"
  SINCE="2026-10-05T18:00:00Z" run bash "$SCRIPT" 42
  [ "$output" = "skip=false" ]
  grep -q "labels=ai-suggested&state=all&per_page=100&since=2026-10-05T18:00:00Z" "$CALL_LOG"
}

@test "fails open with a warning when the lookup fails" {
  write_fake_gh "$(pages '[]')"
  FAKE_GH_FAIL=1 run bash "$SCRIPT" 42
  [ "$status" -eq 0 ]
  [[ "$output" == *"::warning"* ]]
  [[ "$output" == *"skip=false"* ]]
}

@test "rejects a non-numeric PR number" {
  write_fake_gh "$(pages '[]')"
  run bash "$SCRIPT" '42"; rm -rf /'
  [ "$status" -eq 1 ]
}
