#!/usr/bin/env bash
# Quick test script to validate your setup before running in Jenkins

set -euo pipefail

echo "=== AI Dev Build - Setup Validator ==="
echo ""

ERRORS=0
WARNINGS=0

# Check if in repo root
if [ ! -f "package.json" ] || [ ! -f "pyproject.toml" ]; then
  echo "❌ Not in allotmint repo root"
  ERRORS=$((ERRORS + 1))
else
  echo "✓ In repo root"
fi

# Check .ci directory
if [ ! -d ".ci" ]; then
  echo "❌ .ci directory missing"
  ERRORS=$((ERRORS + 1))
else
  echo "✓ .ci directory exists"
fi

# Check scripts exist and are executable
for script in ai_apply.sh validate.sh; do
  if [ ! -f ".ci/${script}" ]; then
    echo "❌ .ci/${script} missing"
    ERRORS=$((ERRORS + 1))
  elif [ ! -x ".ci/${script}" ]; then
    echo "⚠️  .ci/${script} not executable (run: chmod +x .ci/${script})"
    WARNINGS=$((WARNINGS + 1))
  else
    echo "✓ .ci/${script} exists and executable"
  fi
done

# Check prompt exists
if [ ! -f ".ci/prompt.md" ]; then
  echo "❌ .ci/prompt.md missing"
  ERRORS=$((ERRORS + 1))
else
  echo "✓ .ci/prompt.md exists"
fi

# Check required commands
for cmd in git jq curl find awk; do
  if ! command -v ${cmd} >/dev/null 2>&1; then
    echo "❌ ${cmd} not found"
    ERRORS=$((ERRORS + 1))
  else
    echo "✓ ${cmd} available"
  fi
done

# Check gh (GitHub CLI) - required for PR creation
if ! command -v gh >/dev/null 2>&1; then
  echo "⚠️  gh (GitHub CLI) not found - PR creation will fail"
  echo "   Install: https://cli.github.com/"
  WARNINGS=$((WARNINGS + 1))
else
  echo "✓ gh available"
  if gh auth status >/dev/null 2>&1; then
    echo "✓ gh authenticated"
  else
    echo "⚠️  gh not authenticated (run: gh auth login)"
    WARNINGS=$((WARNINGS + 1))
  fi
fi

# Check LM Studio connectivity
LM_API_BASE="${LM_API_BASE:-http://localhost:1234}"
echo ""
echo "Testing LM Studio connection at ${LM_API_BASE}..."

if curl -sf "${LM_API_BASE}/v1/models" >/dev/null 2>&1; then
  echo "✓ LM Studio API accessible"
  
  # List available models
  MODELS=$(curl -sf "${LM_API_BASE}/v1/models" | jq -r '.data[].id' 2>/dev/null || echo "")
  if [ -n "${MODELS}" ]; then
    echo "  Available models:"
    echo "${MODELS}" | while read -r model; do
      echo "    - ${model}"
    done
  fi
else
  echo "⚠️  LM Studio API not accessible"
  echo "   Make sure LM Studio is running and local server is enabled"
  WARNINGS=$((WARNINGS + 1))
fi

# Check target paths exist
echo ""
echo "Checking target paths..."
TARGET_PATHS="${TARGET_PATHS:-backend frontend/src}"
for path in ${TARGET_PATHS}; do
  if [ ! -d "${path}" ]; then
    echo "⚠️  Target path ${path} does not exist"
    WARNINGS=$((WARNINGS + 1))
  else
    FILE_COUNT=$(find "${path}" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) -not -path "*/node_modules/*" -not -path "*/.venv/*" | wc -l)
    echo "✓ ${path} exists (${FILE_COUNT} code files)"
  fi
done

# Estimate total size
echo ""
echo "Estimating repository size..."
TOTAL_LINES=$(find ${TARGET_PATHS} -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) \
  -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/__pycache__/*" \
  -exec wc -l {} \; 2>/dev/null | awk '{sum+=$1} END {print sum}')

echo "Total lines of code: ${TOTAL_LINES}"
EST_TOKENS=$((TOTAL_LINES * 25))
echo "Estimated tokens: ~${EST_TOKENS}"

if [ ${EST_TOKENS} -gt 30000 ]; then
  echo "⚠️  Total size exceeds typical context window (32k tokens)"
  echo "   Chunking is required - use CHUNK_STRATEGY environment variable"
  WARNINGS=$((WARNINGS + 1))
  
  # Suggest chunk size
  MAX_CONTEXT_LINES="${MAX_CONTEXT_LINES:-800}"
  NUM_CHUNKS=$((TOTAL_LINES / MAX_CONTEXT_LINES + 1))
  echo "   With MAX_CONTEXT_LINES=${MAX_CONTEXT_LINES}, you'll need ~${NUM_CHUNKS} chunks"
else
  echo "✓ Total size fits in context window"
fi

# Test chunk creation (dry run)
echo ""
echo "Testing chunk creation (dry run)..."
CHUNK_STRATEGY="${CHUNK_STRATEGY:-recent}"
export CHUNK_STRATEGY
export TARGET_PATHS
export MAX_CONTEXT_LINES="${MAX_CONTEXT_LINES:-800}"

# Create a temporary test context file
TEST_CONTEXT=".ci/test_context.txt"
> "${TEST_CONTEXT}"

case "${CHUNK_STRATEGY}" in
  recent)
    NUM_COMMITS="${NUM_COMMITS:-10}"
    CHANGED_FILES=$(git diff --name-only HEAD~${NUM_COMMITS}..HEAD 2>/dev/null | grep -E '\.(py|ts|tsx|js|jsx)$' | wc -l || echo 0)
    echo "Strategy: recent (last ${NUM_COMMITS} commits)"
    echo "Changed files: ${CHANGED_FILES}"
    if [ ${CHANGED_FILES} -eq 0 ]; then
      echo "⚠️  No changes in last ${NUM_COMMITS} commits"
      echo "   Try increasing NUM_COMMITS or use a different strategy"
      WARNINGS=$((WARNINGS + 1))
    fi
    ;;
  directory|size|filetype)
    echo "Strategy: ${CHUNK_STRATEGY}"
    echo "This will process all files in TARGET_PATHS"
    ;;
esac

rm -f "${TEST_CONTEXT}"

# Summary
echo ""
echo "=== Summary ==="
if [ ${ERRORS} -eq 0 ] && [ ${WARNINGS} -eq 0 ]; then
  echo "✓ All checks passed! Ready to run AI dev build."
  echo ""
  echo "Next steps:"
  echo "  1. Make sure LM Studio is running with a loaded model"
  echo "  2. Test locally: .ci/ai_apply.sh"
  echo "  3. Or run in Jenkins: trigger the AI Dev Build job"
elif [ ${ERRORS} -eq 0 ]; then
  echo "⚠️  ${WARNINGS} warning(s) - setup is functional but could be improved"
  exit 0
else
  echo "❌ ${ERRORS} error(s), ${WARNINGS} warning(s) - fix errors before running"
  exit 1
fi
