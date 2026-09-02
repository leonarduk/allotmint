#!/usr/bin/env bash
# Runs a command (typically a pip install) with git credentials configured so it
# can clone the private leonarduk/cicaid-pro repo. The AI-review modules the
# generated workflows import (review_diff, review_comment, deepseek_review,
# gpt_review, etc.) only exist in cicaid-pro, not the public leonarduk/cicaid
# "free shell" package, so a plain pip install of the public wheel/repo 404s
# or is missing these modules.
#
# Fails fast with an actionable message if CICAID_PRO_TOKEN is unset or empty,
# instead of letting the wrapped command fail later with a confusing git auth
# error. The credential rewrite is scoped to exactly this invocation through
# Git's GIT_CONFIG_* environment variables; the token is never written to a
# config file.
#
# Uses `url.<base>.insteadOf` with the token embedded as URL userinfo, rather
# than a `credential.<url>.helper` shell snippet that reads the token from the
# env var at request time. The helper form looks more secure on paper (the raw
# token never touches disk), but empirically it is NOT reliable here: any
# pre-existing generic `credential.helper` (e.g. Git Credential Manager, or a
# local `gh auth login`) is consulted first and can supply -- or fail to yield
# to -- a different credential before a URL-scoped helper ever runs, since
# helpers accumulate across config scopes rather than "most specific wins".
# The `insteadOf` rewrite has no such ambiguity: the token is embedded
# directly in the URL, which git's transport layer uses unconditionally
# without consulting the credential-helper chain at all. GitHub's own PAT
# formats (ghp_/github_pat_/gho_/ghs_/ghr_) are always alphanumeric and never
# contain the URL-reserved characters (@, :, /) that would make this rewrite
# unsafe, so that's not a practical concern for the token this script expects.
#
# Usage: pip_install_cicaid_pro.sh <command...>
# Required env: CICAID_PRO_TOKEN
set -euo pipefail

if [ -z "${CICAID_PRO_TOKEN:-}" ]; then
  echo "::error::CICAID_PRO_TOKEN is empty or unset. Add a fine-grained PAT (Contents: Read-only, scoped to leonarduk/cicaid-pro) as the CICAID_PRO_TOKEN repository secret (Settings > Secrets and variables > Actions) before this workflow can install cicaid-devtools-pro." >&2
  exit 1
fi

export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0="url.https://x-access-token:${CICAID_PRO_TOKEN}@github.com/leonarduk/cicaid-pro.insteadOf"
export GIT_CONFIG_VALUE_0="https://github.com/leonarduk/cicaid-pro"

exec "$@"
