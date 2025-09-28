#!/usr/bin/env bash
set -euo pipefail

# Ensure the script runs from the frontend directory
cd "$(dirname "$0")"

# Populate git metadata for build provenance if available
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  VITE_GIT_COMMIT_DEFAULT="$(git rev-parse HEAD)"
  VITE_GIT_BRANCH_DEFAULT="$(git rev-parse --abbrev-ref HEAD)"
  : "${VITE_GIT_COMMIT:=$VITE_GIT_COMMIT_DEFAULT}"
  : "${VITE_GIT_BRANCH:=$VITE_GIT_BRANCH_DEFAULT}"
fi

export VITE_GIT_COMMIT="${VITE_GIT_COMMIT:-}"
export VITE_GIT_BRANCH="${VITE_GIT_BRANCH:-}"

# Ensure environment variables are populated
if [ ! -f .env ]; then
  cp .env.example .env
fi

# Override .env values with any provided environment variables
for var in VITE_ALLOTMINT_API_BASE VITE_APP_BASE_URL VITE_API_TOKEN VITE_GIT_COMMIT VITE_GIT_BRANCH; do
  if [ -n "${!var:-}" ]; then
    if grep -q "^${var}=" .env; then
      sed -i "s|^${var}=.*|${var}=${!var}|" .env
    else
      printf '%s=%s\n' "$var" "${!var}" >> .env
    fi
  fi
done

npm install
npm run build
