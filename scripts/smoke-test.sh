#!/usr/bin/env bash
set -euo pipefail
URL="${1:-https://app.allotmint.io}"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$URL")
if [ "$STATUS" -ne 200 ]; then
  echo "Smoke test failed for $URL with status $STATUS" >&2
  exit 1
fi
echo "Smoke test passed for $URL"
