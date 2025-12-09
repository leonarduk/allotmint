#!/bin/sh
set -eu

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
EXTRA_INSTRUCTION="${EXTRA_INSTRUCTION:-}"
AI_OUTPUT_FILE="${WORK_DIR}/.ci/ai_output.txt"

echo "=== AI Apply Configuration ==="
echo "Model: $MODEL_NAME"
echo "API: $LM_API_BASE"
echo "Strategy: $CHUNK_STRATEGY"
echo "Max context lines: $MAX_CONTEXT_LINES"
echo "Output mode: $OUTPUT_MODE"
echo "Target paths: $TARGET_PATHS"
[ -n "$EXTRA_INSTRUCTION" ] && echo "Extra instruction: $EXTRA_INSTRUCTION"

mkdir -p "$WORK_DIR/.ci"

# === Helper Functions ===
estimate_tokens() {
  file="$1"
  lines=$(wc -l < "$file" 2>/dev/null || echo 0)
  echo $((lines * 25)) # Rough estimate: ~25 tokens per line
}

process_chunk() {
  chunk_name="$1"
  chunk_file="$2"
  output_file="$WORK_DIR/.ci/ai_output_${chunk_name}.txt"

  echo "=== Processing chunk: $chunk_name ==="
  lines=$(wc -l < "$chunk_file")
  est_tokens=$(estimate_tokens "$chunk_file")
  echo "Chunk size: $lines lines (~$est_tokens tokens)"

  if [ "$est_tokens" -gt 30000 ]; then
    echo "⚠️ WARNING: Chunk may exceed model context window"
  fi

  # Read files into shell variables
  PROMPT_CONTENT=$(cat "$PROMPT_FILE")
  CONTEXT_CONTENT=$(cat "$chunk_file")
  
  # Build complete prompt
  COMPLETE_PROMPT="$PROMPT_CONTENT

Chunk: $chunk_name"
  
  [ -n "$EXTRA_INSTRUCTION" ] && COMPLETE_PROMPT="$COMPLETE_PROMPT

Additional instruction: $EXTRA_INSTRUCTION"
  
  COMPLETE_PROMPT="$COMPLETE_PROMPT

$CONTEXT_CONTENT"

  # Build JSON payload without --argfile
  # Escape the prompt content for JSON
  ESCAPED_PROMPT=$(printf '%s' "$COMPLETE_PROMPT" | jq -Rs .)
  
  REQUEST_JSON=$(jq -n \
    --arg model "$MODEL_NAME" \
    --argjson prompt "$ESCAPED_PROMPT" \
    '{
      model: $model,
      prompt: $prompt,
      temperature: 0.2,
      max_tokens: 4000
    }')

  # Call LM Studio API
  HTTP_CODE=$(curl -sS -w "%{http_code}" -o "$output_file.raw" -X POST "$LM_API_BASE/v1/completions" \
    -H "Content-Type: application/json" \
    -d "$REQUEST_JSON")

  if [ "$HTTP_CODE" != "200" ]; then
    echo "❌ Error: LM Studio returned HTTP $HTTP_CODE for chunk $chunk_name"
    cat "$output_file.raw"
    return 1
  fi

  if ! jq -e '.choices[0].text' "$output_file.raw" >/dev/null 2>&1; then
    echo "❌ Error: LM Studio response invalid for chunk $chunk_name"
    cat "$output_file.raw"
    return 1
  fi

  jq -r '.choices[0].text' "$output_file.raw" > "$output_file"
  rm -f "$output_file.raw"
  echo "✅ AI output saved to $output_file"

  # Apply changes based on mode
  if [ "$OUTPUT_MODE" = "patch" ]; then
    echo "Applying patch for $chunk_name..."
    if [ -s "$output_file" ]; then
      # Check if output looks like a patch
      if head -1 "$output_file" | grep -q "^---" || grep -q "^diff" "$output_file"; then
        if git apply --reject --whitespace=fix "$output_file" 2>/dev/null; then
          echo "✅ Patch applied successfully"
        else
          echo "⚠️ Patch had conflicts for $chunk_name, check .rej files"
        fi
      else
        echo "ℹ️ Output doesn't look like a patch, skipping application"
        echo "First line: $(head -1 "$output_file")"
      fi
    else
      echo "ℹ️ Empty output for $chunk_name"
    fi
  else
    echo "Applying file replacements for $chunk_name..."
    awk '
      /^=== BEGIN / { inblock=1; file=$3; sub(/===/, "", file); next }
      /^=== END / { inblock=0; close(file); next }
      inblock { print > file }
    ' "$output_file"
  fi

  if ! git diff --quiet; then
    echo "✅ Changes applied for $chunk_name:"
    git diff --stat
  else
    echo "ℹ️ No changes detected for $chunk_name"
  fi
}

# === Chunking Strategies ===
chunk_by_directory() {
  echo "=== Chunking by directory ==="
  chunk_num=0
  
  for path in $TARGET_PATHS; do
    [ ! -d "$path" ] && { echo "⚠️ Path $path not found, skipping"; continue; }
    
    find "$path" -type d -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/.git/*" -not -path "*/__pycache__/*" | while read dir; do
      chunk_file="$WORK_DIR/.ci/chunk_$chunk_num.txt"
      : > "$chunk_file"
      
      # Find code files in this directory (non-recursive)
      find "$dir" -maxdepth 1 -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) 2>/dev/null | while read file; do
        echo "=== BEGIN $file ===" >> "$chunk_file"
        cat "$file" >> "$chunk_file"
        printf "\n=== END %s ===\n\n" "$file" >> "$chunk_file"
      done
      
      # Only process if chunk has content and is within size limit
      if [ -s "$chunk_file" ]; then
        lines=$(wc -l < "$chunk_file")
        if [ "$lines" -gt 0 ] && [ "$lines" -le "$MAX_CONTEXT_LINES" ]; then
          process_chunk "dir_${chunk_num}_$(basename "$dir")" "$chunk_file"
          chunk_num=$((chunk_num + 1))
        elif [ "$lines" -gt "$MAX_CONTEXT_LINES" ]; then
          echo "⚠️ Skipping large directory $(basename "$dir") ($lines lines)"
        fi
      fi
      rm -f "$chunk_file"
    done
  done
}

chunk_by_size() {
  echo "=== Chunking by size ==="
  chunk_file="$WORK_DIR/.ci/chunk_current.txt"
  chunk_num=0
  : > "$chunk_file"
  
  for path in $TARGET_PATHS; do
    [ ! -d "$path" ] && continue
    
    # Get all files sorted by size
    find "$path" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) \
      -not -path "*/node_modules/*" -not -path "*/.venv/*" -not -path "*/__pycache__/*" \
      -exec wc -l {} \; 2>/dev/null | sort -n | while read file_lines file_path; do
      
      chunk_lines=$(wc -l < "$chunk_file" 2>/dev/null || echo 0)
      
      # If adding this file would exceed limit, process current chunk
      if [ $((chunk_lines + file_lines)) -gt "$MAX_CONTEXT_LINES" ] && [ "$chunk_lines" -gt 0 ]; then
        process_chunk "size_$chunk_num" "$chunk_file"
        chunk_num=$((chunk_num + 1))
        : > "$chunk_file"
      fi
      
      echo "=== BEGIN $file_path ===" >> "$chunk_file"
      cat "$file_path" >> "$chunk_file"
      printf "\n=== END %s ===\n\n" "$file_path" >> "$chunk_file"
    done
  done
  
  # Process final chunk
  if [ -s "$chunk_file" ]; then
    process_chunk "size_$chunk_num" "$chunk_file"
  fi
  rm -f "$chunk_file"
}

chunk_recent_changes() {
  echo "=== Chunking recent changes only ==="
  chunk_file="$WORK_DIR/.ci/chunk_recent.txt"
  : > "$chunk_file"
  
  # Get files changed in last N commits
  git diff --name-only HEAD~"$NUM_COMMITS"..HEAD 2>/dev/null | grep -E '\.(py|ts|tsx|js|jsx)$' | while read file; do
    if [ -f "$file" ]; then
      echo "=== BEGIN $file ===" >> "$chunk_file"
      cat "$file" >> "$chunk_file"
      printf "\n=== END %s ===\n\n" "$file" >> "$chunk_file"
    fi
  done
  
  if [ -s "$chunk_file" ]; then
    lines=$(wc -l < "$chunk_file")
    if [ "$lines" -le "$MAX_CONTEXT_LINES" ]; then
      process_chunk "recent" "$chunk_file"
    else
      echo "⚠️ Recent changes too large ($lines lines), falling back to size-based chunking"
      rm -f "$chunk_file"
      chunk_by_size
    fi
  else
    echo "No recent changes found, falling back to directory-based chunking"
    chunk_by_directory
  fi
  
  rm -f "$chunk_file"
}

# === Main Execution ===
case "$CHUNK_STRATEGY" in
  directory) chunk_by_directory ;;
  size) chunk_by_size ;;
  recent) chunk_recent_changes ;;
  *)
    echo "❌ Unknown strategy: $CHUNK_STRATEGY"
    echo "Valid strategies: directory, size, recent"
    exit 1
    ;;
esac

# Merge outputs if in file mode
if [ "$OUTPUT_MODE" = "file" ]; then
  echo "=== Merging AI outputs ==="
  cat "$WORK_DIR"/.ci/ai_output_*.txt > "$AI_OUTPUT_FILE" 2>/dev/null || touch "$AI_OUTPUT_FILE"
  echo "Merged output saved to $AI_OUTPUT_FILE"
fi

echo "=== Complete ==="
echo "Processed chunks saved in .ci/"
ls -lh "$WORK_DIR"/.ci/ai_output*.txt 2>/dev/null || echo "No outputs generated"
