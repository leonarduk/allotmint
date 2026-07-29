#!/bin/bash
# Commit local changes (with an Ollama-drafted message) and push to origin.

REPO_ROOT=$(git rev-parse --show-toplevel)
if [ -z "$REPO_ROOT" ]; then
    echo "Error: not in a git repository" >&2
    exit 1
fi

# Pass all arguments to the Python script
python "$REPO_ROOT/scripts/developer_tools/j_commit_and_push.py" "$@"
exit $?
