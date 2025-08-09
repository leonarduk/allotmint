#!/usr/bin/env bash
set -euo pipefail
export ALLOTMINT_ENV=local
uvicorn backend.local_api.main:app \
  --reload \
  --port 8000 \
  --log-config backend/logging.ini
