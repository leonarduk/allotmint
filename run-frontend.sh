#!/usr/bin/env bash
set -euo pipefail

# Ensure the script runs from repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/frontend"

# Install dependencies
npm install

# Start the Vite development server
npm run dev
