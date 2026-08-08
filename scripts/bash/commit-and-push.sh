#!/bin/bash
# Commit local changes with cicaid and push to origin.

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$REPO_ROOT" ]; then
    echo "Error: not in a git repository" >&2
    exit 1
fi

cd "$REPO_ROOT" || exit 1
exec cicaid commit-and-push "$@"
