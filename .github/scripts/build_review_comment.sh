#!/usr/bin/env bash
# Usage: build_review_comment.sh <body_file> <provider_label> <workflow_file> <run_url>
# Writes the PR comment markdown to stdout.
# Extracted from the inline guard previously in claude-pr-review.yml and
# gpt-pr-review.yml so the logic can be unit-tested without duplicating it.
set -euo pipefail

body_file="$1"
provider="$2"
workflow="$3"
run_url="$4"

if [ -s "$body_file" ]; then
    echo "## ${provider} AI Code Review"
    echo ""
    cat "$body_file"
    echo ""
    echo "---"
    echo "*Reviewed by ${provider} via [${workflow}](.github/workflows/${workflow}). Advisory only.*"
else
    echo "## ${provider} AI Code Review - Failed"
    echo ""
    echo "The ${provider} review failed to complete. Check [Actions](${run_url}) for error details."
fi
