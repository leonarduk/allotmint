
#!/bin/bash
set -euo pipefail

# -----------------------------------------------------------------------------
# SYNOPSIS
#   Installs frontend dependencies and runs the coverage test suite.
# DESCRIPTION
#   This script automates:
#     1. Install NPM dependencies under the frontend workspace.
#     2. Run the coverage script defined in package.json.
# -----------------------------------------------------------------------------

echo "Starting frontend coverage..."

# Resolve repository root based on script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
while [[ ! -f "$REPO_ROOT/package.json" && "$REPO_ROOT" != "/" ]]; do
    REPO_ROOT="$(dirname "$REPO_ROOT")"
done

if [[ ! -f "$REPO_ROOT/package.json" ]]; then
    echo "Unable to locate repository root from '$SCRIPT_DIR'."
    exit 1
fi

FRONTEND_PATH="$REPO_ROOT/frontend"
if [[ ! -d "$FRONTEND_PATH" ]]; then
    echo "Frontend directory not found at '$FRONTEND_PATH'."
    exit 1
fi

# Check npm availability
if ! command -v npm &>/dev/null; then
    echo "npm is required but was not found in PATH."
    exit 1
fi

# Execute steps
cd "$FRONTEND_PATH"
echo "Installing frontend dependencies..."
npm install

echo "Running frontend coverage tests..."
npm run coverage

echo "Coverage completed successfully."
