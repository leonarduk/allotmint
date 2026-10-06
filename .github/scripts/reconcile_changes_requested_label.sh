#!/usr/bin/env bash
# Reconcile the 'Changes Requested' label on a single PR against the conclusions
# of all enabled AI review check-runs for its current head SHA.
#
# Shared by both triggers of sync-changes-requested-label.yml:
#   - the workflow_run-triggered job, which reconciles the PR tied to the review
#     workflow that just completed
#   - the schedule-triggered job, which sweeps every open PR still carrying the
#     label as a fallback for the "stuck label" scenario (see
#     docs/AI_REVIEW_WORKFLOWS.md#stuck-label-fallback) where workflow_run never
#     fires (e.g. the triggering run was cancelled before completion)
#
# Also called inline by _ai-pr-review.yml right after a reviewer approves,
# while that job still holds its runner. That reviewer's own check-run is still
# in progress at that point, so it passes its verdict in:
#   ASSUME_SUCCESS_CHECK  reviewer check name to count as "success"
#                         (e.g. "DeepSeek AI code review")
#   REVIEWED_SHA          the commit that reviewer approved; the assumption is
#                         applied only if it is still the PR's head, so a
#                         newer push's pending review is never skipped.
# Without this, clearing the label depended entirely on a separate
# workflow_run job getting a runner, and on GitHub's best-effort schedule for
# the fallback sweep; both failed on 2026-10-05 and left PR #9466 labelled
# after its final review approved.
#
# Usage: reconcile_changes_requested_label.sh <pr_number>
# Required env: GH_TOKEN, REPO, ENABLE_CLAUDE, ENABLE_GPT, ENABLE_DEEPSEEK
# Optional env: ASSUME_SUCCESS_CHECK, REVIEWED_SHA (see above)
set -euo pipefail

PR_NUMBER="${1:?Usage: reconcile_changes_requested_label.sh <pr_number>}"

HEAD_SHA=$(gh pr view "$PR_NUMBER" --repo "$REPO" --json headRefOid --jq '.headRefOid')
if [ -z "$HEAD_SHA" ]; then
  echo "Could not resolve head SHA for PR #${PR_NUMBER}; skipping."
  exit 0
fi

# Build the list of enabled reviewers from their check-run names.
# When a reviewer is disabled (vars.ENABLE_*_REVIEW=false), its workflow
# job is skipped entirely, so no check-run exists. This excludes disabled
# reviewers so it doesn't wait forever for a check-run that will never appear.
# Each name is multi-word (e.g. "Claude AI code review"), so these must be
# kept as array elements rather than a space-joined string -- an unquoted
# string expansion in the loop below would word-split each name apart and
# never match a real check-run name.
ENABLED_CHECK_NAMES=()

if [ "${ENABLE_CLAUDE:-true}" != "false" ]; then
  ENABLED_CHECK_NAMES+=("Claude AI code review")
fi

if [ "${ENABLE_GPT:-true}" != "false" ]; then
  ENABLED_CHECK_NAMES+=("GPT AI code review")
fi

if [ "${ENABLE_DEEPSEEK:-true}" != "false" ]; then
  ENABLED_CHECK_NAMES+=("DeepSeek AI code review")
fi

if [ "${#ENABLED_CHECK_NAMES[@]}" -eq 0 ]; then
  echo "No AI reviewers are enabled; nothing to reconcile for PR #${PR_NUMBER}."
  exit 0
fi

echo "PR #${PR_NUMBER} (${HEAD_SHA}) — enabled reviewers: ${ENABLED_CHECK_NAMES[*]}"

ASSUMED_CHECK=""
if [ -n "${ASSUME_SUCCESS_CHECK:-}" ]; then
  if [ "${REVIEWED_SHA:-}" = "$HEAD_SHA" ]; then
    ASSUMED_CHECK="$ASSUME_SUCCESS_CHECK"
    echo "Counting ${ASSUMED_CHECK} as success (it approved ${HEAD_SHA} in the calling job)."
  else
    echo "Not assuming ${ASSUME_SUCCESS_CHECK}: it reviewed ${REVIEWED_SHA:-<unset>}, but the head is now ${HEAD_SHA}."
  fi
fi

# Fetch every check-run for the head SHA once, as one TSV line per run:
#   name <TAB> started_at <TAB> id <TAB> status <TAB> conclusion
# The --jq filter runs once per *page* under --paginate. So it only emits
# per-run lines, and the choice of the latest run happens in bash below, after
# all pages are collected. (A whole-array reduction such as `sort_by | last`
# would give one answer per page and never equal "success" once a commit had
# more than one page of check-runs.)
#
# Runs concluded skipped/neutral/cancelled are dropped: they carry no review
# verdict. A no-op `labeled` event, for example, starts a DeepSeek PR Review
# run whose ai-review job is skipped. That run reuses the same check name and
# starts *after* the real review, so if it were kept it would hide the real
# success and leave the label stuck (#8812). A run with no started_at yet
# (queued) sorts last, so a pending re-review always counts as the latest
# state.
CHECK_RUNS=$(gh api "repos/${REPO}/commits/${HEAD_SHA}/check-runs?per_page=100" --paginate \
  --jq '.check_runs[]
    | select(.conclusion != "skipped" and .conclusion != "neutral" and .conclusion != "cancelled")
    | [.name, (.started_at // "9999-12-31T23:59:59Z"), (.id | tostring), .status, (.conclusion // "")]
    | @tsv')

# Prints the verdict of the latest verdict-bearing check-run for reviewer $1:
# its conclusion if completed, "pending" if it hasn't completed or no such run
# exists. Reviews run through the reusable _ai-pr-review.yml workflow, so
# GitHub names the check-run "<caller job> / <job name>" (e.g.
# "ai-review / DeepSeek AI code review"). Both that prefixed form and the
# bare name are accepted, so a reviewer that is later called directly still
# matches.
latest_verdict() {
  local want="$1"
  local name started id status conclusion
  local best_started="" best_id=0 best_status="" best_conclusion=""
  while IFS=$'\t' read -r name started id status conclusion; do
    [ -n "$name" ] || continue
    if [ "$name" != "$want" ] && [[ "$name" != *" / ${want}" ]]; then
      continue
    fi
    if [ -z "$best_started" ] || [[ "$started" > "$best_started" ]] ||
      { [ "$started" = "$best_started" ] && [ "$id" -gt "$best_id" ]; }; then
      best_started="$started"
      best_id="$id"
      best_status="$status"
      best_conclusion="$conclusion"
    fi
  done <<<"$CHECK_RUNS"

  if [ -z "$best_started" ] || [ "$best_status" != "completed" ] || [ -z "$best_conclusion" ]; then
    echo "pending"
  else
    echo "$best_conclusion"
  fi
}

ALL_SUCCESS=true
for NAME in "${ENABLED_CHECK_NAMES[@]}"; do
  if [ -n "$ASSUMED_CHECK" ] && [ "$NAME" = "$ASSUMED_CHECK" ]; then
    CONCLUSION="success"
  else
    CONCLUSION=$(latest_verdict "$NAME")
  fi
  echo "  ${NAME}: ${CONCLUSION}"
  if [ "$CONCLUSION" != "success" ]; then
    ALL_SUCCESS=false
  fi
done

if [ "$ALL_SUCCESS" != "true" ]; then
  echo "At least one enabled review hasn't approved yet; leaving 'Changes Requested' label as-is."
  exit 0
fi

HAS_LABEL=$(gh pr view "$PR_NUMBER" --repo "$REPO" --json labels \
  --jq '[.labels[].name] | any(. == "Changes Requested")')

if [ "$HAS_LABEL" != "true" ]; then
  echo "Label not present on PR #${PR_NUMBER}; nothing to remove."
  exit 0
fi

gh pr edit "$PR_NUMBER" --repo "$REPO" --remove-label "Changes Requested"
gh pr comment "$PR_NUMBER" --repo "$REPO" --body \
  "All enabled AI reviews have passed for the latest commit -- removing the 'Changes Requested' label."
