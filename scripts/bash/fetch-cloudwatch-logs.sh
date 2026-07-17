#!/usr/bin/env bash
# Fetch recent CloudWatch log events for a log group, distinguishing a genuine
# "no events" result from an API error (e.g. AccessDeniedException) so deploy
# steps don't silently swallow IAM permission regressions. See #3742.
#
# Usage: fetch-cloudwatch-logs.sh <log-group-name> <lookback-seconds>
#
# aws logs tail is CLI v2 only; filter-log-events is used for CLI v1
# compatibility. filter-log-events returns at most 10 000 events per call (no
# pagination); an empty/"None" result over --output text means no events
# matched (AWS CLI JMESPath null -> text "None").
#
# stdout/stderr contract (see #4074, #4870):
#   stdout - result data only, one line per log message (newline-delimited,
#     no JSON/other structure), in the order returned by filter-log-events.
#     If no events matched, stdout is exactly the literal line
#     "(no log events found)". Callers that want to programmatically detect
#     "no events" vs "events present" should match on that literal string
#     rather than checking for empty stdout, since stdout is never empty.
#   stderr - diagnostics only, never result data. All output on stderr is a
#     GitHub Actions `::warning::...` annotation (AccessDeniedException on
#     the log group, a non-numeric lookback-seconds argument, or any other
#     AWS CLI failure); none of it is fatal to the calling workflow. Callers
#     do not need to parse stderr - it exists for the workflow log/UI only.
#   exit codes - always 0. Log fetching is diagnostic, not load-bearing, so
#     AWS CLI/API errors and invalid arguments are reported via the
#     `::warning::` stderr annotation above rather than a non-zero exit or a
#     silently swallowed failure.
#
# Example:
#   $ ./fetch-cloudwatch-logs.sh /aws/lambda/my-fn 300
#   (no log events found)          # -> stdout; log group had no events
#   $ ./fetch-cloudwatch-logs.sh /aws/lambda/no-access 300
#   ::warning::logs:FilterLogEvents denied for /aws/lambda/no-access; CloudWatch logs not available (see #3742)
#                                   # -> stderr; stdout is empty, exit code 0

set -euo pipefail

log_group="${1:?log group name required}"
lookback_seconds="${2:?lookback window in seconds required}"

# Reject non-numeric input before it reaches the date arithmetic below, where
# a bad value (e.g. empty string, negative number, or non-numeric garbage)
# would otherwise produce a bogus start-time or a confusing arithmetic error.
if ! [[ "$lookback_seconds" =~ ^[0-9]+$ ]]; then
    echo "::warning::lookback-seconds must be a non-negative integer, got '$lookback_seconds' for $log_group; skipping log fetch" >&2
    exit 0
fi

start_ms=$(( ($(date +%s) - lookback_seconds) * 1000 ))

# Capture stdout (log data) separately from stderr (warnings/diagnostics).
# Stderr from AWS CLI is allowed to flow to the workflow log; only stdout
# is processed through grep -v to filter "None" entries.
# The `|| exit_code=$?` form keeps this command-substitution failure
# "checked" so `set -e` doesn't abort the script before the exit_code
# handling below runs.
exit_code=0
output="$(aws logs filter-log-events \
    --log-group-name "$log_group" \
    --start-time "$start_ms" \
    --query 'events[].message' \
    --output text)" || exit_code=$?

if [ "$exit_code" -ne 0 ]; then
    if printf '%s' "$output" | grep -q "AccessDeniedException"; then
        echo "::warning::logs:FilterLogEvents denied for $log_group; CloudWatch logs not available (see #3742)"
    else
        echo "::warning::Failed to fetch CloudWatch logs for $log_group: $output"
    fi
    exit 0
fi

filtered="$(printf '%s' "$output" | grep -v '^None$' || true)"
if [ -z "$filtered" ]; then
    echo "(no log events found)"
else
    printf '%s\n' "$filtered"
fi
