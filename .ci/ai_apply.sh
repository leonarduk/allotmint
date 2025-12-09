#!/usr/bin/env bash
set -euo pipefail

MODEL_NAME="${MODEL_NAME:-Qwen2.5-Coder}"
LM_API_BASE="${LM_API_BASE:-http://localhost:1234}"
OUTPUT_MODE="${OUTPUT_MODE:-file}" # "file" or "patch"
TARGET_PATHS="${TARGET_PATHS:-backend frontend/src}"  # Updated for your project structure
PROMPT_FILE="${PROMPT_FILE:-.ci/prompt.md}"
WORK_DIR="$(pwd)"
CONTEXT_FILE="${WORK_DIR}/.ci/context.txt"
AI_OUTPUT_FILE="${WORK_DIR}/.ci/ai_output.txt"

echo "=== Building context from: ${TARGET_PATHS} ==="

# Clear previous context
> "${CONTEXT_FILE}"

# Build context: list changed or relevant files
for path in ${TARGET_PATHS}; do
  if [ ! -d "${path}" ]; then
    echo "Warning: ${path} does not exist, skipping"
    continue
  fi
  
  echo "Scanning ${path}..."
  
  # Find Python and TypeScript/JavaScript files
  find "${path}" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/__pycache__/*" | while read -r file; do
    echo "=== BEGIN ${file} ===" >> "${CONTEXT_FILE}"
    cat "${file}" >> "${CONTEXT_FILE}"
    echo -e "\n=== END ${file} ===\n" >> "${CONTEXT_FILE}"
  done
done

if [ ! -s "${CONTEXT_FILE}" ]; then
  echo "Error: No files found to process in ${TARGET_PATHS}"
  exit 1
fi

echo "Context built: $(wc -l < "${CONTEXT_FILE}") lines"

# Compose request
echo "=== Preparing LM Studio request ==="
PROMPT_CONTENT=$(cat "${PROMPT_FILE}")
CONTEXT_CONTENT=$(cat "${CONTEXT_FILE}")

REQUEST_PAYLOAD=$(jq -n \
  --arg model "${MODEL_NAME}" \
  --arg prompt "${PROMPT_CONTENT}\n\n${CONTEXT_CONTENT}" \
  '{model: $model, prompt: $prompt, temperature: 0.2, max_tokens: 4000}')

# Call LM Studio API
echo "=== Calling LM Studio at ${LM_API_BASE} ==="
HTTP_CODE=$(curl -sS -w "%{http_code}" -o "${AI_OUTPUT_FILE}.raw" -X POST "${LM_API_BASE}/v1/completions" \
  -H "Content-Type: application/json" \
  -d "${REQUEST_PAYLOAD}")

if [ "${HTTP_CODE}" != "200" ]; then
  echo "Error: LM Studio API returned HTTP ${HTTP_CODE}"
  cat "${AI_OUTPUT_FILE}.raw"
  exit 1
fi

# Extract the text from the response
jq -r '.choices[0].text' "${AI_OUTPUT_FILE}.raw" > "${AI_OUTPUT_FILE}"
rm -f "${AI_OUTPUT_FILE}.raw"

echo "AI output saved to ${AI_OUTPUT_FILE}"

# Apply output
if [[ "${OUTPUT_MODE}" == "patch" ]]; then
  echo "=== Applying as patch ==="
  if command -v git >/dev/null 2>&1; then
    git apply --reject --whitespace=fix "${AI_OUTPUT_FILE}" || {
      echo "Patch failed; check .ci/ai_output.txt and .rej files"
      exit 1
    }
  else
    echo "git not found; cannot apply patch."
    exit 1
  fi
else
  echo "=== Applying as file replacements ==="
  # Parse for file markers and overwrite files
  # Format: "=== BEGIN path === ... === END path ==="
  awk '
    /^=== BEGIN / { 
      inblock=1
      file=$3
      sub(/===/, "", file)
      gsub(/^[ \t]+|[ \t]+$/, "", file)  # trim whitespace
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

echo "AI changes applied."
