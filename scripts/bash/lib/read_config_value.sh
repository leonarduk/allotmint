#!/usr/bin/env bash
# Shared helper for local dev scripts: read one scalar from a two-level YAML
# file such as config.yaml, e.g. `server.uvicorn_port`, without needing a
# YAML parser. Mirrors run-backend.ps1's Get-ConfigValue: supports a
# top-level key or a key one level under a section; strips quotes and
# trailing comments; ignores lists and deeper nesting.

# Prints the value of $2 (`key` or `section.key`) from YAML file $1, or $3
# (default: empty) when the file, section or key is missing or empty.
read_config_value() {
  local file="$1" path="$2" default="${3:-}"
  local section="" key="$path"
  if [[ "$path" == *.* ]]; then
    section="${path%%.*}"
    key="${path#*.}"
  fi

  local value=""
  if [[ -f "$file" ]]; then
    value=$(awk -v section="$section" -v key="$key" -v sq="'" '
      /^[[:space:]]*(#|$)/ { next }
      {
        match($0, /^[ ]*/)
        indent = RLENGTH
        line = substr($0, indent + 1)
        if (indent == 0) { current = line; sub(/:.*/, "", current); child = -1 }
        else if (child < 0) { child = indent }
        if ((section == "" && indent == 0) || (section != "" && current == section && indent == child)) {
          if (index(line, key ":") == 1) {
            value = substr(line, length(key) + 2)
            sub(/^[ \t]+/, "", value)
            if (substr(value, 1, 1) == "\"" || substr(value, 1, 1) == sq) {
              quote = substr(value, 1, 1)
              value = substr(value, 2)
              sub(quote ".*$", "", value)
            } else {
              sub(/[ \t]+#.*$/, "", value)
              sub(/[ \t]+$/, "", value)
            }
            print value
            exit
          }
        }
      }' "$file")
  fi
  echo "${value:-$default}"
}
