#!/usr/bin/env bash
set -euo pipefail

# Ensure the script runs from the frontend directory
cd "$(dirname "$0")"

npm install
npm run build
