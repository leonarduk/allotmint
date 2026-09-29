#!/usr/bin/env bash
# Shared helper for local dev scripts: export the variables from the repo's
# .env, else the shared env file outside every repo/worktree, so credentials
# never need copying around (see ALLOTMINT_ENV_FILE in
# docs/CONTRIBUTOR_RUNBOOK.md). A repo-local .env wins (backward compat).

# Loads $1/.env, else ${ALLOTMINT_ENV_FILE:-~/workspace/GitHub/allotmint/.env.shared}.
load_allotmint_env() {
  local repo_root="$1"
  local shared_env_file="${ALLOTMINT_ENV_FILE:-$HOME/workspace/GitHub/allotmint/.env.shared}"
  local env_file=""
  if [[ -f "$repo_root/.env" ]]; then
    env_file="$repo_root/.env"
  elif [[ -f "$shared_env_file" ]]; then
    env_file="$shared_env_file"
  fi
  if [[ -n "$env_file" ]]; then
    set -o allexport
    # shellcheck disable=SC1090
    source "$env_file"
    set +o allexport
  fi
}
