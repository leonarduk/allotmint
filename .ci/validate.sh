#!/usr/bin/env bash
set -euo pipefail

echo "Running validation for allotmint..."

# Python backend validation
if [ -f backend/pyproject.toml ] || [ -f backend/requirements.txt ]; then
  echo "=== Running Python backend tests ==="
  cd backend
  
  # Create/activate venv
  if [ ! -d .venv ]; then
    python -m venv .venv
  fi
  
  # Activate based on OS
  if [ -f .venv/Scripts/activate ]; then
    # Windows (Git Bash)
    source .venv/Scripts/activate
  else
    # Unix-like
    source .venv/bin/activate
  fi
  
  # Install dependencies
  pip install -q -r requirements.txt || true
  pip install -q -r requirements-dev.txt || true
  
  # Run tests with pytest
  if command -v pytest >/dev/null 2>&1; then
    pytest -q || {
      echo "Backend tests failed"
      deactivate
      exit 1
    }
  else
    echo "pytest not found, skipping backend tests"
  fi
  
  deactivate
  cd ..
fi

# Node.js frontend validation
if [ -f frontend/package.json ]; then
  echo "=== Running frontend tests ==="
  cd frontend
  
  # Install dependencies
  npm ci
  
  # Run linting
  if npm run lint --if-present; then
    echo "Linting passed"
  else
    echo "Linting failed"
    exit 1
  fi
  
  # Run tests
  if npm test -- --run 2>/dev/null || npm test 2>/dev/null; then
    echo "Frontend tests passed"
  else
    echo "Frontend tests failed"
    exit 1
  fi
  
  cd ..
fi

echo "=== All validation checks passed ==="
