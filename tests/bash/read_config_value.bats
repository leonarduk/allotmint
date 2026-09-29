#!/usr/bin/env bats
# Unit tests for scripts/bash/lib/read_config_value.sh, used by
# scripts/bash/run-local-api.sh to read config.yaml's nested server:/paths:
# keys (a flat `awk '/^key:/'` read them all as empty).

LIB="$BATS_TEST_DIRNAME/../../scripts/bash/lib/read_config_value.sh"

setup() {
  source "$LIB"
  CFG="$BATS_TEST_TMPDIR/config.yaml"
  cat >"$CFG" <<'EOF'
# comment
paths:
  log_config: backend/logging.ini   # trailing comment
server:
  app_env: "local"
  uvicorn_port: 6468
  empty: ''
  cors:
    local:
    - http://localhost:2568
  reload: true
base_currency: GBP
EOF
}

@test "reads a key nested under a section" {
  run read_config_value "$CFG" server.uvicorn_port
  [ "$output" = "6468" ]
}

@test "strips quotes and trailing comments" {
  [ "$(read_config_value "$CFG" server.app_env)" = "local" ]
  [ "$(read_config_value "$CFG" paths.log_config)" = "backend/logging.ini" ]
}

@test "reads a key after a deeper-nested block in the same section" {
  [ "$(read_config_value "$CFG" server.reload)" = "true" ]
}

@test "reads a top-level key" {
  [ "$(read_config_value "$CFG" base_currency)" = "GBP" ]
}

@test "does not match a key nested more than one level deep" {
  [ "$(read_config_value "$CFG" server.local fallback)" = "fallback" ]
}

@test "does not match a same-named key in another section or at the top level" {
  [ "$(read_config_value "$CFG" paths.uvicorn_port fallback)" = "fallback" ]
  [ "$(read_config_value "$CFG" uvicorn_port fallback)" = "fallback" ]
}

@test "falls back to the default for a missing or empty value" {
  [ "$(read_config_value "$CFG" server.missing 8080)" = "8080" ]
  [ "$(read_config_value "$CFG" server.empty dflt)" = "dflt" ]
  [ "$(read_config_value "$BATS_TEST_TMPDIR/nope.yaml" server.app_env local)" = "local" ]
}

@test "reads the repo's own config.yaml server settings" {
  local repo_cfg="$BATS_TEST_DIRNAME/../../config.yaml"
  [ -f "$repo_cfg" ] || skip "config.yaml not present"
  [ -n "$(read_config_value "$repo_cfg" server.uvicorn_port)" ]
  [ -n "$(read_config_value "$repo_cfg" paths.log_config)" ]
}
