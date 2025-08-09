#!/usr/bin/env bash
set -euo pipefail

# ensure script runs from repository root so log files are written consistently
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export ALLOTMINT_ENV=local
uvicorn backend.local_api.main:app \
  --reload \
  --port 8000 \
  --log-config backend/logging.ini
