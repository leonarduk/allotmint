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
# Always exits 0 (log fetching is diagnostic, not load-bearing); on error it
# emits a `::warning::` GitHub Actions annotation instead of failing or
# silently printing "(no log events found)".

set -uo pipefail

log_group="${1:?log group name required}"
lookback_seconds="${2:?lookback window in seconds required}"

start_ms=$(( ($(date +%s) - lookback_seconds) * 1000 ))

# Capture stdout (log data) separately from stderr (warnings/diagnostics).
# Stderr from AWS CLI is allowed to flow to the workflow log; only stdout
# is processed through grep -v to filter "None" entries.
output="$(aws logs filter-log-events \
    --log-group-name "$log_group" \
    --start-time "$start_ms" \
    --query 'events[].message' \
    --output text)"
exit_code=$?

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
