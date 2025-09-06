#!/usr/bin/env bash
set -euo pipefail

# Ensure the script runs from the frontend directory
cd "$(dirname "$0")"

# Ensure environment variables are populated
if [ ! -f .env ]; then
  cp .env.example .env
fi

# Override .env values with any provided environment variables
for var in VITE_ALLOTMINT_API_BASE VITE_APP_BASE_URL VITE_API_TOKEN; do
  if [ -n "${!var:-}" ]; then
    sed -i "s|^${var}=.*|${var}=${!var}|" .env
  fi
done

npm install
npm run build
