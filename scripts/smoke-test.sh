#!/usr/bin/env bash
set -euo pipefail
URL="${1:-${SMOKE_TEST_URL:-}}"
if [ -z "$URL" ]; then
  echo "Usage: SMOKE_TEST_URL=<url> $0 [url]" >&2
  exit 1
fi

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$URL")
if [ "$STATUS" -ne 200 ]; then
  echo "Smoke test failed for $URL with status $STATUS" >&2
  exit 1
fi
echo "Smoke test passed for $URL"
