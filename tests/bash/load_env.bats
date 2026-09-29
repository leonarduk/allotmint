#!/usr/bin/env bats
# Unit tests for scripts/bash/lib/load_env.sh, shared by run-local-api.sh
# and run-mcp-server.sh.

LIB="$BATS_TEST_DIRNAME/../../scripts/bash/lib/load_env.sh"

setup() {
  source "$LIB"
  REPO="$BATS_TEST_TMPDIR/repo"
  mkdir -p "$REPO"
  printf 'LOADED_FROM=shared\n' >"$BATS_TEST_TMPDIR/shared.env"
  export ALLOTMINT_ENV_FILE="$BATS_TEST_TMPDIR/shared.env"
  unset LOADED_FROM
}

@test "exports the shared env file when the repo has no .env" {
  load_allotmint_env "$REPO"

  [ "$LOADED_FROM" = "shared" ]
  run bash -c 'echo "$LOADED_FROM"'
  [ "$output" = "shared" ]
}

@test "a repo-local .env wins over the shared file" {
  printf 'LOADED_FROM=repo\n' >"$REPO/.env"
  load_allotmint_env "$REPO"

  [ "$LOADED_FROM" = "repo" ]
}

@test "does nothing when neither file exists" {
  export ALLOTMINT_ENV_FILE="$BATS_TEST_TMPDIR/missing.env"
  load_allotmint_env "$REPO"

  [ -z "${LOADED_FROM:-}" ]
}
