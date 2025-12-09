#!/usr/bin/env bash
set -euo pipefail

MODEL_NAME="${MODEL_NAME:-Qwen2.5-Coder}"
LM_API_BASE="${LM_API_BASE:-http://localhost:1234}"
OUTPUT_MODE="${OUTPUT_MODE:-file}" # "file" or "patch"
TARGET_PATHS="${TARGET_PATHS:-backend frontend/src}"
PROMPT_FILE="${PROMPT_FILE:-.ci/prompt.md}"
WORK_DIR="$(pwd)"
CONTEXT_FILE="${WORK_DIR}/.ci/context.txt"
AI_OUTPUT_FILE="${WORK_DIR}/.ci/ai_output.txt"

# Chunking configuration
MAX_CONTEXT_LINES="${MAX_CONTEXT_LINES:-800}"  # Roughly 20-25k tokens at ~30 chars/line
CHUNK_STRATEGY="${CHUNK_STRATEGY:-directory}"  # "directory", "filetype", "size", or "recent"

echo "=== AI Apply Configuration ==="
echo "Model: ${MODEL_NAME}"
echo "API: ${LM_API_BASE}"
echo "Strategy: ${CHUNK_STRATEGY}"
echo "Max context lines: ${MAX_CONTEXT_LINES}"

# Function to estimate tokens (rough: 1 line ≈ 25-30 tokens)
estimate_tokens() {
  local file="$1"
  local lines=$(wc -l < "$file" 2>/dev/null || echo 0)
  echo $(( lines * 25 ))
}

# Function to process a single chunk
process_chunk() {
  local chunk_name="$1"
  local chunk_file="$2"
  local output_file="${WORK_DIR}/.ci/ai_output_${chunk_name}.txt"
  
  echo "=== Processing chunk: ${chunk_name} ==="
  
  local lines=$(wc -l < "${chunk_file}")
  local est_tokens=$(estimate_tokens "${chunk_file}")
  echo "Chunk size: ${lines} lines (~${est_tokens} tokens)"
  
  if [ ${est_tokens} -gt 30000 ]; then
    echo "WARNING: Chunk may exceed model context window"
  fi
  
  # Compose request
  PROMPT_CONTENT=$(cat "${PROMPT_FILE}")
  CONTEXT_CONTENT=$(cat "${chunk_file}")
  
  REQUEST_PAYLOAD=$(jq -n \
    --arg model "${MODEL_NAME}" \
    --arg prompt "${PROMPT_CONTENT}\n\nChunk: ${chunk_name}\n\n${CONTEXT_CONTENT}" \
    '{model: $model, prompt: $prompt, temperature: 0.2, max_tokens: 4000}')
  
  # Call LM Studio API
  HTTP_CODE=$(curl -sS -w "%{http_code}" -o "${output_file}.raw" -X POST "${LM_API_BASE}/v1/completions" \
    -H "Content-Type: application/json" \
    -d "${REQUEST_PAYLOAD}")
  
  if [ "${HTTP_CODE}" != "200" ]; then
    echo "Error: LM Studio returned HTTP ${HTTP_CODE} for chunk ${chunk_name}"
    cat "${output_file}.raw"
    return 1
  fi
  
  # Extract text
  jq -r '.choices[0].text' "${output_file}.raw" > "${output_file}"
  rm -f "${output_file}.raw"
  
  echo "Chunk ${chunk_name} processed → ${output_file}"
  
  # Apply changes immediately if in patch mode
  if [[ "${OUTPUT_MODE}" == "patch" ]]; then
    if [ -s "${output_file}" ]; then
      git apply --reject --whitespace=fix "${output_file}" 2>&1 || {
        echo "Warning: Patch for ${chunk_name} had conflicts"
      }
    fi
  fi
}

# Strategy 1: Chunk by directory
chunk_by_directory() {
  echo "=== Chunking by directory ==="
  local chunk_num=0
  
  for path in ${TARGET_PATHS}; do
    if [ ! -d "${path}" ]; then
      echo "Warning: ${path} does not exist, skipping"
      continue
    fi
    
    # Find all subdirectories
    find "${path}" -type d -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/__pycache__/*" -not -path "*/.git/*" | while read -r dir; do
      local chunk_file="${WORK_DIR}/.ci/chunk_${chunk_num}.txt"
      > "${chunk_file}"
      
      # Add all code files in this directory (non-recursive)
      find "${dir}" -maxdepth 1 -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) | while read -r file; do
        echo "=== BEGIN ${file} ===" >> "${chunk_file}"
        cat "${file}" >> "${chunk_file}"
        echo -e "\n=== END ${file} ===\n" >> "${chunk_file}"
      done
      
      # Only process if chunk has content
      if [ -s "${chunk_file}" ]; then
        local lines=$(wc -l < "${chunk_file}")
        if [ ${lines} -gt ${MAX_CONTEXT_LINES} ]; then
          echo "Skipping large directory ${dir} (${lines} lines)"
        else
          process_chunk "dir_${chunk_num}_$(basename ${dir})" "${chunk_file}"
          chunk_num=$((chunk_num + 1))
        fi
      fi
      rm -f "${chunk_file}"
    done
  done
}

# Strategy 2: Chunk by file type
chunk_by_filetype() {
  echo "=== Chunking by file type ==="
  
  local filetypes=("py" "ts" "tsx" "js" "jsx")
  local chunk_num=0
  
  for ext in "${filetypes[@]}"; do
    local chunk_file="${WORK_DIR}/.ci/chunk_${ext}.txt"
    > "${chunk_file}"
    
    for path in ${TARGET_PATHS}; do
      [ ! -d "${path}" ] && continue
      
      find "${path}" -type f -name "*.${ext}" -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/__pycache__/*" | while read -r file; do
        local file_lines=$(wc -l < "${file}" 2>/dev/null || echo 0)
        local chunk_lines=$(wc -l < "${chunk_file}" 2>/dev/null || echo 0)
        
        # Start new chunk if adding this file would exceed limit
        if [ $((chunk_lines + file_lines)) -gt ${MAX_CONTEXT_LINES} ] && [ ${chunk_lines} -gt 0 ]; then
          process_chunk "${ext}_${chunk_num}" "${chunk_file}"
          chunk_num=$((chunk_num + 1))
          > "${chunk_file}"
        fi
        
        echo "=== BEGIN ${file} ===" >> "${chunk_file}"
        cat "${file}" >> "${chunk_file}"
        echo -e "\n=== END ${file} ===\n" >> "${chunk_file}"
      done
    done
    
    # Process remaining files for this type
    if [ -s "${chunk_file}" ]; then
      process_chunk "${ext}_${chunk_num}" "${chunk_file}"
    fi
    rm -f "${chunk_file}"
  done
}

# Strategy 3: Chunk by file size (pack small files together)
chunk_by_size() {
  echo "=== Chunking by size ==="
  
  local chunk_file="${WORK_DIR}/.ci/chunk_current.txt"
  local chunk_num=0
  > "${chunk_file}"
  
  # Get all files sorted by size
  for path in ${TARGET_PATHS}; do
    [ ! -d "${path}" ] && continue
    
    find "${path}" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) \
      -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/__pycache__/*" \
      -exec wc -l {} \; | sort -n | while read -r file_lines file_path; do
      
      local chunk_lines=$(wc -l < "${chunk_file}" 2>/dev/null || echo 0)
      
      # If adding this file would exceed limit, process current chunk and start new one
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
  
  # Process final chunk
  if [ -s "${chunk_file}" ]; then
    process_chunk "size_${chunk_num}" "${chunk_file}"
  fi
  rm -f "${chunk_file}"
}

# Strategy 4: Only recent changes (git diff based)
chunk_recent_changes() {
  echo "=== Chunking recent changes only ==="
  
  local chunk_file="${WORK_DIR}/.ci/chunk_recent.txt"
  > "${chunk_file}"
  
  # Get files changed in last N commits (default 10)
  local num_commits="${NUM_COMMITS:-10}"
  
  git diff --name-only HEAD~${num_commits}..HEAD | grep -E '\.(py|ts|tsx|js|jsx)$' | while read -r file; do
    if [ -f "${file}" ]; then
      echo "=== BEGIN ${file} ===" >> "${chunk_file}"
      cat "${file}" >> "${chunk_file}"
      echo -e "\n=== END ${file} ===\n" >> "${chunk_file}"
    fi
  done
  
  if [ -s "${chunk_file}" ]; then
    local lines=$(wc -l < "${chunk_file}")
    if [ ${lines} -le ${MAX_CONTEXT_LINES} ]; then
      process_chunk "recent" "${chunk_file}"
    else
      echo "Recent changes too large (${lines} lines), falling back to size-based chunking"
      rm -f "${chunk_file}"
      chunk_by_size
    fi
  else
    echo "No recent changes found, processing all files"
    chunk_by_size
  fi
  
  rm -f "${chunk_file}"
}

# Main execution
case "${CHUNK_STRATEGY}" in
  directory)
    chunk_by_directory
    ;;
  filetype)
    chunk_by_filetype
    ;;
  size)
    chunk_by_size
    ;;
  recent)
    chunk_recent_changes
    ;;
  *)
    echo "Unknown strategy: ${CHUNK_STRATEGY}"
    echo "Valid strategies: directory, filetype, size, recent"
    exit 1
    ;;
esac

# Merge all outputs if in file mode
if [[ "${OUTPUT_MODE}" == "file" ]]; then
  echo "=== Merging chunk outputs ==="
  cat ${WORK_DIR}/.ci/ai_output_*.txt > "${AI_OUTPUT_FILE}" 2>/dev/null || touch "${AI_OUTPUT_FILE}"
  
  # Parse and apply
  awk '
    /^=== BEGIN / { inblock=1; file=$3; sub(/===/, "", file); next }
    /^=== END / { inblock=0; close(file); next }
    inblock { print > file }
  ' "${AI_OUTPUT_FILE}"
  
  echo "AI changes applied from all chunks"
fi

echo "=== Complete ==="
echo "Processed outputs in .ci/"
ls -lh ${WORK_DIR}/.ci/ai_output*.txt 2>/dev/null || echo "No outputs generated"
