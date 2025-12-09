#!/usr/bin/env bash
# Chunk strategy: Process directories in sequence

set -euo pipefail

MODEL_NAME="${MODEL_NAME:-Qwen2.5-Coder}"
LM_API_BASE="${LM_API_BASE:-http://localhost:1234}"
OUTPUT_MODE="${OUTPUT_MODE:-patch}"
PROMPT_FILE="${PROMPT_FILE:-.ci/prompt.md}"
WORK_DIR="$(pwd)"

# Define chunks - each should fit in ~25k tokens (leaving room for prompt/response)
CHUNKS=(
  "backend/routes"
  "backend/utils"
  "backend/agent"
  "backend/common"
  "backend/integrations"
  "frontend/src/components"
  "frontend/src/pages"
  "frontend/src/hooks"
  "frontend/src/utils"
)

# Or if CHUNK_INDEX is set, process just that chunk
if [ -n "${CHUNK_INDEX:-}" ]; then
  if [ "${CHUNK_INDEX}" -ge "${#CHUNKS[@]}" ]; then
    echo "Error: CHUNK_INDEX ${CHUNK_INDEX} out of range (0-$((${#CHUNKS[@]}-1)))"
    exit 1
  fi
  CHUNKS=("${CHUNKS[$CHUNK_INDEX]}")
  echo "=== Processing chunk ${CHUNK_INDEX}: ${CHUNKS[0]} ==="
fi

# Process each chunk
for TARGET_PATH in "${CHUNKS[@]}"; do
  if [ ! -d "${TARGET_PATH}" ]; then
    echo "Warning: ${TARGET_PATH} does not exist, skipping"
    continue
  fi
  
  echo ""
  echo "========================================"
  echo "Processing: ${TARGET_PATH}"
  echo "========================================"
  
  CONTEXT_FILE="${WORK_DIR}/.ci/context_$(echo ${TARGET_PATH} | tr '/' '_').txt"
  AI_OUTPUT_FILE="${WORK_DIR}/.ci/ai_output_$(echo ${TARGET_PATH} | tr '/' '_').txt"
  
  # Build context for this chunk
  > "${CONTEXT_FILE}"
  
  echo "Scanning ${TARGET_PATH}..."
  find "${TARGET_PATH}" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) \
    -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/__pycache__/*" \
    -not -name "*.test.*" -not -name "*.spec.*" | while read -r file; do
    echo "=== BEGIN ${file} ===" >> "${CONTEXT_FILE}"
    cat "${file}" >> "${CONTEXT_FILE}"
    echo -e "\n=== END ${file} ===\n" >> "${CONTEXT_FILE}"
  done
  
  if [ ! -s "${CONTEXT_FILE}" ]; then
    echo "No files found in ${TARGET_PATH}, skipping"
    continue
  fi
  
  CONTEXT_LINES=$(wc -l < "${CONTEXT_FILE}")
  ESTIMATED_TOKENS=$((CONTEXT_LINES * 4))  # Rough estimate: 4 tokens per line
  echo "Context: ${CONTEXT_LINES} lines (~${ESTIMATED_TOKENS} tokens)"
  
  if [ ${ESTIMATED_TOKENS} -gt 25000 ]; then
    echo "WARNING: Context might be too large (>${MODEL_MAX_TOKENS:-32000} tokens)"
    echo "Consider splitting ${TARGET_PATH} further"
  fi
  
  # Compose request
  echo "Calling LM Studio..."
  PROMPT_CONTENT=$(cat "${PROMPT_FILE}")
  CONTEXT_CONTENT=$(cat "${CONTEXT_FILE}")
  
  REQUEST_PAYLOAD=$(jq -n \
    --arg model "${MODEL_NAME}" \
    --arg prompt "${PROMPT_CONTENT}\n\nFocus on: ${TARGET_PATH}\n\n${CONTEXT_CONTENT}" \
    '{model: $model, prompt: $prompt, temperature: 0.2, max_tokens: 4000}')
  
  HTTP_CODE=$(curl -sS -w "%{http_code}" -o "${AI_OUTPUT_FILE}.raw" -X POST "${LM_API_BASE}/v1/completions" \
    -H "Content-Type: application/json" \
    -d "${REQUEST_PAYLOAD}")
  
  if [ "${HTTP_CODE}" != "200" ]; then
    echo "Error: LM Studio API returned HTTP ${HTTP_CODE} for ${TARGET_PATH}"
    cat "${AI_OUTPUT_FILE}.raw"
    continue
  fi
  
  jq -r '.choices[0].text' "${AI_OUTPUT_FILE}.raw" > "${AI_OUTPUT_FILE}"
  rm -f "${AI_OUTPUT_FILE}.raw"
  
  echo "AI output saved to ${AI_OUTPUT_FILE}"
  
  # Apply output
  if [[ "${OUTPUT_MODE}" == "patch" ]]; then
    echo "Applying patch for ${TARGET_PATH}..."
    if git apply --reject --whitespace=fix "${AI_OUTPUT_FILE}" 2>/dev/null; then
      echo "✅ Patch applied successfully"
    else
      echo "⚠️  Patch failed for ${TARGET_PATH}, check .rej files"
    fi
  else
    echo "Applying file replacements for ${TARGET_PATH}..."
    awk '
      /^=== BEGIN / { 
        inblock=1
        file=$3
        sub(/===/, "", file)
        gsub(/^[ \t]+|[ \t]+$/, "", file)
        next
      }
      /^=== END / { 
        inblock=0
        close(file)
        if (file != "") {
          print "Updated: " file > "/dev/stderr"
        }
        next
      }
      inblock { 
        if (file != "") {
          print > file
        }
      }
    ' "${AI_OUTPUT_FILE}"
  fi
  
  # Show what changed
  if ! git diff --quiet "${TARGET_PATH}"; then
    echo "✅ Changes applied to ${TARGET_PATH}:"
    git diff --stat "${TARGET_PATH}"
  else
    echo "ℹ️  No changes in ${TARGET_PATH}"
  fi
  
  echo ""
done

echo "=== All chunks processed ==="
