#!/usr/bin/env bash
set -euo pipefail

# Ensure script runs from the frontend directory
cd "$(dirname "$0")"

npm run preview >/dev/null &
PREVIEW_PID=$!
# Give the preview server time to start
sleep 5
# Fail if the homepage does not load successfully
curl -f http://localhost:4173 > /dev/null
kill $PREVIEW_PID
