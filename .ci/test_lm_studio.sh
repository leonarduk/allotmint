#!/usr/bin/env bash
# Quick test script to verify LM Studio setup

set -e

LM_API_BASE="${LM_API_BASE:-http://localhost:1234}"

echo "=== Testing LM Studio Connection ==="
echo "API Base: ${LM_API_BASE}"
echo ""

# Test 1: Can we reach the server?
echo "Test 1: Server reachable..."
if curl -sS -f "${LM_API_BASE}/v1/models" > /dev/null 2>&1; then
  echo "✅ Server is reachable"
else
  echo "❌ Cannot reach server at ${LM_API_BASE}"
  echo "   Make sure LM Studio is running with 'Local Server' enabled"
  exit 1
fi

# Test 2: List available models
echo ""
echo "Test 2: Available models..."
MODELS=$(curl -sS "${LM_API_BASE}/v1/models" | jq -r '.data[].id' 2>/dev/null)
if [ -n "${MODELS}" ]; then
  echo "✅ Found models:"
  echo "${MODELS}" | sed 's/^/   - /'
else
  echo "❌ No models found or jq not installed"
  exit 1
fi

# Test 3: Simple completion
echo ""
echo "Test 3: Test completion..."
RESPONSE=$(curl -sS -X POST "${LM_API_BASE}/v1/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "'"$(echo "${MODELS}" | head -1)"'",
    "prompt": "Write a Python function that adds two numbers:",
    "max_tokens": 100,
    "temperature": 0.1
  }' | jq -r '.choices[0].text' 2>/dev/null)

if [ -n "${RESPONSE}" ] && [ "${RESPONSE}" != "null" ]; then
  echo "✅ Completion successful"
  echo "   Sample output:"
  echo "${RESPONSE}" | head -5 | sed 's/^/   /'
else
  echo "❌ Completion failed"
  exit 1
fi

echo ""
echo "=== All tests passed! ==="
echo ""
echo "Your LM Studio is ready for use with the AI dev pipeline."
echo "Model to use: $(echo "${MODELS}" | head -1)"
