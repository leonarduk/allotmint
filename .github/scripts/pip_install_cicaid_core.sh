#!/usr/bin/env bash
# Runs a command (typically a pip install) with git credentials configured so it
# can clone the now-private leonarduk/cicaid-core repo. leonarduk/cicaid was
# renamed to leonarduk/cicaid-core (private) and its old name reused by a new,
# unrelated public repo, so old github.com/leonarduk/cicaid/releases/... wheel
# URLs 404 (#6754); requirements-dev.txt and backend/requirements-test.txt now
# pin cicaid-devtools to the private repo instead.
#
# Fails fast with an actionable message if CICAID_CORE_TOKEN is unset or empty,
# instead of letting the wrapped command fail later with a confusing git auth
# error. The credential rewrite is scoped to exactly this invocation: it's
# configured immediately before running the command and unset again straight
# after (even on failure), so the token isn't left sitting in the runner's
# ~/.gitconfig for the rest of the job.
#
# Usage: pip_install_cicaid_core.sh <command...>
# Required env: CICAID_CORE_TOKEN
set -euo pipefail

if [ -z "${CICAID_CORE_TOKEN:-}" ]; then
  echo "::error::CICAID_CORE_TOKEN is empty or unset. Add a fine-grained PAT (Contents: Read-only, scoped to leonarduk/cicaid-core) as the CICAID_CORE_TOKEN repository secret (Settings > Secrets and variables > Actions) before this workflow can install cicaid-devtools. See issue #6754." >&2
  exit 1
fi

CONFIG_KEY="url.https://x-access-token:${CICAID_CORE_TOKEN}@github.com/leonarduk/cicaid-core.insteadOf"

cleanup() {
  git config --global --unset "$CONFIG_KEY" >/dev/null 2>&1 || true
}
trap cleanup EXIT

git config --global "$CONFIG_KEY" "https://github.com/leonarduk/cicaid-core"

"$@"
