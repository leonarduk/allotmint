#!/usr/bin/env bash
# Decide whether AI-review follow-up issues have already been filed for a PR,
# so _ai-pr-review.yml's "Create follow-up issues" step runs only for the first
# approving review of a PR, not for every re-review on each new push.
#
# Re-reviews of the same PR restate the same "Suggested follow-up issues"
# bullets with slightly different wording, so without this gate every approved
# re-run filed a fresh batch of near-duplicate tickets (e.g. #9474/#9485 and
# #9482/#9494/#9500 all came from re-reviews of PR #9466).
#
# Every issue cicaid_devtools.lib.followup_issues files carries the
# "ai-suggested" label and a PR reference ending "AI review of PR #<n>.": the
# normal footer is "_Follow-up from AI review of PR #<n>._" and the fallback
# body (used when the body-writing LLM call fails) is "Follow-up suggested by
# AI review of PR #<n>." (docs/AI_REVIEW_WORKFLOWS.md). Matching the shared
# suffix covers both; the trailing "." keeps #42 from matching #420.
#
# Matching on what was actually filed (rather than on earlier review comments)
# means a PR whose first review requested changes and filed nothing still gets
# its follow-ups on the first approval.
#
# Usage: followups_already_filed.sh <pr_number>
# Required env: GH_TOKEN, REPO
# Optional env: SINCE (ISO-8601, e.g. the PR's created_at) to bound the scan.
#   The API's `since` filters on updated_at, which is a superset here: a
#   follow-up for a PR is created (so last updated) after the PR was opened.
#   Unset, every ai-suggested issue is scanned (slower, still correct).
# Closed follow-ups count too (state=all): once a suggestion has been filed and
# triaged, a re-review must not re-file it even if it was closed.
# Prints "skip=true" or "skip=false" (for $GITHUB_OUTPUT). If the lookup fails,
# it warns and prints "skip=false", keeping the previous behaviour of filing.
set -euo pipefail

PR_NUMBER="${1:?Usage: followups_already_filed.sh <pr_number>}"
if ! [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "::error::PR number must be numeric, got '${PR_NUMBER}'" >&2
  exit 1
fi

MARKER="AI review of PR #${PR_NUMBER}."
QUERY="repos/${REPO}/issues?labels=ai-suggested&state=all&per_page=100"
if [ -n "${SINCE:-}" ]; then
  QUERY="${QUERY}&since=${SINCE}"
else
  echo "SINCE not set; scanning all ai-suggested issues for PR #${PR_NUMBER}." >&2
fi

# --jq runs per page under --paginate, so this emits one number per matching
# issue across all pages. The issues endpoint also returns PRs; drop those.
if ! MATCHES=$(gh api "$QUERY" --paginate --jq \
  ".[] | select(.pull_request == null) | select((.body // \"\") | contains(\"${MARKER}\")) | .number"); then
  echo "::warning title=Follow-up dedupe::Could not list ai-suggested issues for PR #${PR_NUMBER}; filing follow-ups as before." >&2
  echo "skip=false"
  exit 0
fi

if [ -n "$MATCHES" ]; then
  echo "Follow-ups already filed for PR #${PR_NUMBER}: $(echo "$MATCHES" | tr '\n' ' ')" >&2
  echo "skip=true"
else
  echo "skip=false"
fi
