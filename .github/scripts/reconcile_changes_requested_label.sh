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
# Usage: reconcile_changes_requested_label.sh <pr_number>
# Required env: GH_TOKEN, REPO, ENABLE_CLAUDE, ENABLE_GPT, ENABLE_DEEPSEEK
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

# Fetch every check-run for the head SHA once (one compact JSON object per
# line, across all pages) and filter locally with jq for each reviewer.
CHECK_RUNS=$(gh api "repos/${REPO}/commits/${HEAD_SHA}/check-runs" --paginate \
  --jq '.check_runs[] | {name, status, conclusion, started_at}')

# Resolve one reviewer's effective conclusion from $CHECK_RUNS.
# - The review jobs run inside the reusable _ai-pr-review.yml workflow, so the
#   check-run is named "<caller job> / <job name>" (e.g.
#   "ai-review / DeepSeek AI code review"). Match the bare name or any
#   " / <name>" suffix so a caller-job rename doesn't silently break this.
# - A single push can produce duplicate check-runs for the same job where the
#   later one is "skipped" (e.g. a second trigger whose job-level `if:` was
#   false). skipped/neutral runs carry no verdict, so ignore them and take the
#   latest remaining run; in-progress runs have a null conclusion -> pending.
reviewer_conclusion() {
  printf '%s\n' "$CHECK_RUNS" | jq -rs --arg name "$1" '
    [ .[]
      | select(.name == $name or (.name | endswith(" / " + $name)))
      | select(.conclusion != "skipped" and .conclusion != "neutral") ]
    | sort_by(.started_at) | last | .conclusion // "pending"'
}

ALL_SUCCESS=true
for NAME in "${ENABLED_CHECK_NAMES[@]}"; do
  CONCLUSION=$(reviewer_conclusion "$NAME")
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
