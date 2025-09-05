#!/usr/bin/env bash
set -euo pipefail

# Ensure script runs from the frontend directory
cd "$(dirname "$0")"

npm run preview >/dev/null &
PREVIEW_PID=$!
# Give the preview server time to start
sleep 5
trap 'kill $PREVIEW_PID' EXIT
# Fail if the homepage does not load successfully
if ! curl -f http://localhost:4173 > /dev/null; then
  echo "Smoke test failed: homepage did not load" >&2
  exit 1
fi
