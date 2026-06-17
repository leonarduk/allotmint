#!/bin/bash
# Publish a PR from the current branch with optional Ollama assistance.

REPO_ROOT=$(git rev-parse --show-toplevel)
if [ -z "$REPO_ROOT" ]; then
    echo "Error: not in a git repository" >&2
    exit 1
fi

# Pass all arguments to the Python script
python "$REPO_ROOT/scripts/publish_pr.py" "$@"
exit $?
