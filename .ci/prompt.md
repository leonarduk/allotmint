# AI Code Improvement Task

You are analyzing a chunk of code from the allotmint project (a financial planning application with Python backend and React frontend).

## Your Goal
Make targeted improvements to the code while maintaining stability and consistency. Focus on:
- Adding comprehensive error handling where missing
- Improving logging with structured context
- Fixing obvious bugs or code smells
- Adding type hints (Python) or improving types (TypeScript)
- Ensuring tests would pass (don't break existing functionality)

## Critical Constraints
- **Make minimal, surgical changes** - do not refactor working code unnecessarily
- **Preserve all public APIs** - no breaking changes to function signatures, endpoints, or interfaces
- **Keep the existing code style** - match indentation, naming conventions, import order
- **Only modify files shown in the context** - do not reference or create new files
- **Atomic changes only** - each change should be independent and safe

## Output Format
Respond ONLY with a unified diff (patch format) that can be applied with `git apply`.

Format:
```
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -10,7 +10,10 @@
 existing line
-line to remove
+line to add
+another line to add
 existing line
```

If no changes are needed for this chunk, respond with:
```
NO_CHANGES_NEEDED
```

## Code Context
Below are the files in this chunk. Analyze them and produce a patch with your improvements:
