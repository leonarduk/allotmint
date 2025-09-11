#!/usr/bin/env bash
# Synchronize data directory from various sources.
set -euo pipefail

DATA_DIR="${1:-data}"

if [ -d "$DATA_DIR" ] && [ -n "$(ls -A "$DATA_DIR" 2>/dev/null)" ]; then
  echo "Data directory '$DATA_DIR' already populated; skipping sync." >&2
  exit 0
fi

# If data is a git submodule, update it
if [ -f .gitmodules ] && git config --file .gitmodules --get-regexp path | grep -q "^submodule\.${DATA_DIR}\.path" 2>/dev/null; then
  echo "Syncing data via git submodule..." >&2
  git submodule update --init "$DATA_DIR"
  exit 0
fi

if [ -n "${DATA_REPO:-}" ]; then
  BRANCH="${DATA_BRANCH:-main}"
  echo "Cloning data repository $DATA_REPO (branch $BRANCH)..." >&2
  git clone --depth 1 --branch "$BRANCH" "$DATA_REPO" "$DATA_DIR"
  exit 0
fi

if [ -n "${DATA_BUCKET:-}" ]; then
  PREFIX="${DATA_PREFIX:-}"
  SRC="s3://${DATA_BUCKET}/${PREFIX}"
  echo "Syncing data from $SRC..." >&2
  if ! command -v aws >/dev/null 2>&1; then
    echo "aws CLI not found; please install AWS CLI to sync from S3." >&2
    exit 1
  fi
  aws s3 sync "$SRC" "$DATA_DIR"
  exit 0
fi

echo "No data source configured. Set DATA_REPO or DATA_BUCKET or define a git submodule." >&2
exit 1
