# AI Dev Build - Quick Reference

## Chunking Strategies

### 1. **recent** (Default - Recommended)
- Analyzes only files changed in last N commits (default: 10)
- **Use when:** You want to improve recent work
- **Pros:** Fast, focused, fits in context easily
- **Cons:** Might miss related files not recently changed

### 2. **size**
- Packs files into chunks by size, small files first
- **Use when:** You want comprehensive analysis but need even token distribution
- **Pros:** Efficient packing, processes entire codebase
- **Cons:** Unrelated files grouped together, less context coherence

### 3. **directory**
- Processes each directory as a separate chunk
- **Use when:** Your code is well-organized by module/feature
- **Pros:** Maintains logical context, good for modular codebases
- **Cons:** Large directories might exceed token limits

### 4. **filetype**
- Groups by extension (.py, .ts, etc.)
- **Use when:** You want to apply language-specific improvements
- **Pros:** Consistent changes across one language
- **Cons:** Loses cross-file context

## Configuration

### Environment Variables (set in Jenkinsfile.ai or shell)

```bash
# Required
LM_API_BASE="http://localhost:1234"      # Your LM Studio endpoint
MODEL_NAME="Qwen2.5-Coder"               # Model name in LM Studio

# Chunking (optional)
CHUNK_STRATEGY="recent"                   # recent|size|directory|filetype
MAX_CONTEXT_LINES="800"                   # Lines per chunk (~20-25k tokens)
NUM_COMMITS="10"                          # For 'recent' strategy

# Output (optional)
OUTPUT_MODE="patch"                       # patch|file
TARGET_PATHS="backend frontend/src"       # Paths to analyze
```

## Token Estimation

- **1 line ≈ 25-30 tokens** (average)
- **32k context** ≈ 1000-1200 lines of code
- **Safe chunk size:** 800 lines (leaves room for prompt + response)

## Running Locally

### Test chunking without LM Studio:
```bash
cd /path/to/allotmint
export CHUNK_STRATEGY=recent
export MAX_CONTEXT_LINES=800
export TARGET_PATHS="backend/routes frontend/src/components"

# Dry run - just build chunks, don't call API
.ci/ai_apply.sh
ls -lh .ci/chunk_*.txt
```

### Run with LM Studio:
```bash
# Make sure LM Studio is running on localhost:1234
export LM_API_BASE="http://localhost:1234"
export MODEL_NAME="Qwen2.5-Coder"
export CHUNK_STRATEGY=recent

.ci/ai_apply.sh
```

## Jenkins Parameters

When you trigger "Build with Parameters" in Jenkins:

| Parameter | Options | Description |
|-----------|---------|-------------|
| CHUNK_STRATEGY | recent, size, directory, filetype | How to split code |
| MAX_CONTEXT_LINES | 800 (default) | Lines per chunk |
| NUM_COMMITS | 10 (default) | For "recent" strategy only |

## Troubleshooting

### "Chunk may exceed model context window"
- Reduce MAX_CONTEXT_LINES (try 600 or 400)
- Use 'recent' strategy to analyze fewer files
- Target specific paths: `TARGET_PATHS="backend/routes"`

### "No files found to process"
- Check TARGET_PATHS points to actual directories
- Verify file extensions match: .py, .ts, .tsx, .js, .jsx

### "Patch failed"
- Model might not be generating valid diffs
- Try OUTPUT_MODE="file" (less reliable but more forgiving)
- Improve prompt.md to be more explicit about patch format

### "PR creation failed"
- Check `gh auth status` on Jenkins node
- Verify GITHUB_TOKEN credential exists in Jenkins
- Ensure token has repo write permissions

## Best Practices

1. **Start small:** Use `recent` strategy with last 5 commits
2. **Iterate:** Run multiple times with different chunks
3. **Review:** Always review the PR before merging
4. **Tune prompts:** Adjust `.ci/prompt.md` for your needs
5. **Monitor tokens:** Check `.ci/chunk_*.txt` sizes before processing

## Example Workflow

```bash
# 1. Recent changes only (safest)
CHUNK_STRATEGY=recent NUM_COMMITS=5 .ci/ai_apply.sh

# 2. Specific module
CHUNK_STRATEGY=directory TARGET_PATHS="backend/routes" .ci/ai_apply.sh

# 3. All Python files
CHUNK_STRATEGY=filetype TARGET_PATHS="backend" .ci/ai_apply.sh

# 4. Full repo (many chunks)
CHUNK_STRATEGY=size MAX_CONTEXT_LINES=600 .ci/ai_apply.sh
```
