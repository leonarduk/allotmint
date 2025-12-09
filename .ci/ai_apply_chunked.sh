
#!/usr/bin/env bash
set -euo pipefail

# === Configuration ===
MODEL_NAME="${MODEL_NAME:-Qwen2.5-Coder}"
LM_API_BASE="${LM_API_BASE:-http://localhost:1234}"
OUTPUT_MODE="${OUTPUT_MODE:-patch}" # "patch" or "file"
PROMPT_FILE="${PROMPT_FILE:-.ci/prompt.md}"
WORK_DIR="$(pwd)"
MAX_CONTEXT_LINES="${MAX_CONTEXT_LINES:-800}"
CHUNK_STRATEGY="${CHUNK_STRATEGY:-directory}"
NUM_COMMITS="${NUM_COMMITS:-10}"
TARGET_PATHS="${TARGET_PATHS:-backend frontend/src}"
AI_OUTPUT_FILE="${WORK_DIR}/.ci/ai_output.txt"

echo "=== AI Apply Configuration ==="
echo "Model: ${MODEL_NAME}"
echo "API: ${LM_API_BASE}"
echo "Strategy: ${CHUNK_STRATEGY}"
echo "Max context lines: ${MAX_CONTEXT_LINES}"
echo "Output mode: ${OUTPUT_MODE}"
echo "Target paths: ${TARGET_PATHS}"

mkdir -p "${WORK_DIR}/.ci"

# === Helper Functions ===
estimate_tokens() {
  local file="$1"
  local lines=$(wc -l < "$file" 2>/dev/null || echo 0)
  echo $(( lines * 4 )) # Rough estimate: 4 tokens per line
}

process_chunk() {
  local chunk_name="$1"
  local chunk_file="$2"
  local output_file="${WORK_DIR}/.ci/ai_output_${chunk_name}.txt"

  echo "=== Processing chunk: ${chunk_name} ==="
  local lines=$(wc -l < "${chunk_file}")
  local est_tokens=$(estimate_tokens "${chunk_file}")
  echo "Chunk size: ${lines} lines (~${est_tokens} tokens)"

  if [ ${est_tokens} -gt 30000 ]; then
    echo "⚠️ WARNING: Chunk may exceed model context window"
  fi

  # Compose request using jq with --argfile for large context
  PROMPT_CONTENT=$(cat "${PROMPT_FILE}")
  jq -n \
    --arg model "${MODEL_NAME}" \
    --arg extra "${PROMPT_CONTENT}\n\nFocus on: ${chunk_name}" \
    --arg temperature "0.2" \
    --arg max_tokens "4000" \
    --argfile context "${chunk_file}" \
    '{model: $model, prompt: ($extra + "\n\n" + ($context|tostring)), temperature: ($temperature|tonumber), max_tokens: ($max_tokens|tonumber)}' \
  | curl -sS -X POST "${LM_API_BASE}/v1/completions" \
    -H "Content-Type: application/json" \
    -d @- \
    -o "${output_file}.raw"

  # Validate response
  if ! jq -e '.choices[0].text' "${output_file}.raw" >/dev/null; then
    echo "❌ Error: LM Studio response invalid for chunk ${chunk_name}"
    cat "${output_file}.raw"
    return 1
  fi

  jq -r '.choices[0].text' "${output_file}.raw" > "${output_file}"
  rm -f "${output_file}.raw"
  echo "✅ AI output saved to ${output_file}"

  # Apply changes
  if [[ "${OUTPUT_MODE}" == "patch" ]]; then
    echo "Applying patch for ${chunk_name}..."
    if git apply --reject --whitespace=fix "${output_file}" 2>/dev/null; then
      echo "✅ Patch applied successfully"
    else
      echo "⚠️ Patch failed for ${chunk_name}, check .rej files"
    fi
  else
    echo "Applying file replacements for ${chunk_name}..."
    awk '
      /^=== BEGIN / { inblock=1; file=$3; sub(/===/, "", file); next }
      /^=== END / { inblock=0; close(file); next }
      inblock { print > file }
    ' "${output_file}"
  fi

  # Show changes
  if ! git diff --quiet; then
    echo "✅ Changes applied for ${chunk_name}:"
    git diff --stat
  else
    echo "ℹ️ No changes detected for ${chunk_name}"
  fi
}

# === Chunking Strategies ===
chunk_by_directory() {
  echo "=== Chunking by directory ==="
  local chunk_num=0
  for path in ${TARGET_PATHS}; do
    [ ! -d "${path}" ] && continue
    find "${path}" -type d -not -path "*/node_modules/*" -not -path "*/.git/*" | while read -r dir; do
      local chunk_file="${WORK_DIR}/.ci/chunk_${chunk_num}.txt"
      > "${chunk_file}"
      find "${dir}" -maxdepth 1 -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) \
        -not -path "*/node_modules/*" | while read -r file; do
        echo "=== BEGIN ${file} ===" >> "${chunk_file}"
        cat "${file}" >> "${chunk_file}"
        echo -e "\n=== END ${file} ===\n" >> "${chunk_file}"
      done
      if [ -s "${chunk_file}" ] && [ $(wc -l < "${chunk_file}") -le ${MAX_CONTEXT_LINES} ]; then
        process_chunk "dir_${chunk_num}_$(basename ${dir})" "${chunk_file}"
        chunk_num=$((chunk_num + 1))
      fi
      rm -f "${chunk_file}"
    done
  done
}

chunk_by_filetype() {
  echo "=== Chunking by file type ==="
  local filetypes=("py" "ts" "tsx" "js" "jsx")
  local chunk_num=0
  for ext in "${filetypes[@]}"; do
    local chunk_file="${WORK_DIR}/.ci/chunk_${ext}.txt"
    > "${chunk_file}"
    for path in ${TARGET_PATHS}; do
      [ ! -d "${path}" ] && continue
      find "${path}" -type f -name "*.${ext}" -not -path "*/node_modules/*" | while read -r file; do
        echo "=== BEGIN ${file} ===" >> "${chunk_file}"
        cat "${file}" >> "${chunk_file}"
        echo -e "\n=== END ${file} ===\n" >> "${chunk_file}"
      done
    done
    if [ -s "${chunk_file}" ]; then
      process_chunk "${ext}_${chunk_num}" "${chunk_file}"
    fi
    rm -f "${chunk_file}"
  done
}

chunk_by_size() {
  echo "=== Chunking by size ==="
  local chunk_file="${WORK_DIR}/.ci/chunk_current.txt"
  local chunk_num=0
  > "${chunk_file}"
  for path in ${TARGET_PATHS}; do
    [ ! -d "${path}" ] && continue
    find "${path}" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) \
      -not -path "*/node_modules/*" -exec wc -l {} \; | sort -n | while read -r file_lines file_path; do
      local chunk_lines=$(wc -l < "${chunk_file}" 2>/dev/null || echo 0)
      if [ $((chunk_lines + file_lines)) -gt ${MAX_CONTEXT_LINES} ] && [ ${chunk_lines} -gt 0 ]; then
        process_chunk "size_${chunk_num}" "${chunk_file}"
        chunk_num=$((chunk_num + 1))
        > "${chunk_file}"
      fi
      echo "=== BEGIN ${file_path} ===" >> "${chunk_file}"
      cat "${file_path}" >> "${chunk_file}"
      echo -e "\n=== END ${file_path} ===\n" >> "${chunk_file}"
    done
  done
  if [ -s "${chunk_file}" ]; then
    process_chunk "size_${chunk_num}" "${chunk_file}"
  fi
  rm -f "${chunk_file}"
}

chunk_recent_changes() {
  echo "=== Chunking recent changes only ==="
  local chunk_file="${WORK_DIR}/.ci/chunk_recent.txt"
  > "${chunk_file}"
  git diff --name-only HEAD~${NUM_COMMITS}..HEAD | grep -E '\.(py|ts|tsx|js|jsx)$' | while read -r file; do
    if [ -f "${file}" ]; then
      echo "=== BEGIN ${file} ===" >> "${chunk_file}"
      cat "${file}" >> "${chunk_file}"
      echo -e "\n=== END ${file} ===\n" >> "${chunk_file}"
    fi
  done
  if [ -s "${chunk_file}" ]; then
    process_chunk "recent" "${chunk_file}"
  else
    echo "No recent changes found, falling back to size-based chunking"
    chunk_by_size
  fi
  rm -f "${chunk_file}"
}

# === Main Execution ===
case "${CHUNK_STRATEGY}" in
  directory) chunk_by_directory ;;
  filetype) chunk_by_filetype ;;
  size) chunk_by_size ;;
  recent) chunk_recent_changes ;;
  *) echo "Unknown strategy: ${CHUNK_STRATEGY}"; exit 1 ;;
esac

# Merge outputs if OUTPUT_MODE=file
if [[ "${OUTPUT_MODE}" == "file" ]]; then
  echo "=== Merging AI outputs ==="
  cat ${WORK_DIR}/.ci/ai_output_*.txt > "${AI_OUTPUT_FILE}" 2>/dev/null || touch "${AI_OUTPUT_FILE}"
  echo "Merged output saved to ${AI_OUTPUT_FILE}"
fi

echo "=== Complete ==="
