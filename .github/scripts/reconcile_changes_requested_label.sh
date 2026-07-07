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
ENABLED_CHECK_NAMES=""

if [ "${ENABLE_CLAUDE:-true}" != "false" ]; then
  ENABLED_CHECK_NAMES="$ENABLED_CHECK_NAMES Claude AI code review"
fi

if [ "${ENABLE_GPT:-true}" != "false" ]; then
  ENABLED_CHECK_NAMES="$ENABLED_CHECK_NAMES GPT AI code review"
fi

if [ "${ENABLE_DEEPSEEK:-true}" != "false" ]; then
  ENABLED_CHECK_NAMES="$ENABLED_CHECK_NAMES DeepSeek AI code review"
fi

if [ -z "$ENABLED_CHECK_NAMES" ]; then
  echo "No AI reviewers are enabled; nothing to reconcile for PR #${PR_NUMBER}."
  exit 0
fi

echo "PR #${PR_NUMBER} (${HEAD_SHA}) — enabled reviewers:${ENABLED_CHECK_NAMES}"

ALL_SUCCESS=true
for NAME in $ENABLED_CHECK_NAMES; do
  CONCLUSION=$(gh api "repos/${REPO}/commits/${HEAD_SHA}/check-runs" --paginate \
    --jq "[.check_runs[] | select(.name == \"${NAME}\")] | sort_by(.started_at) | last | .conclusion // \"pending\"")
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
