#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.lambda.yml}
ENV_FILE=${ENV_FILE:-.env.lambda.example}
PAYLOAD_FILE=${PAYLOAD_FILE:-tests/integration/lambda/payloads/http-health-v2.json}
EXPECTED_FILE=${EXPECTED_FILE:-tests/integration/lambda/expected/http-health-v2.json}
LAMBDA_HOST_PORT=${LAMBDA_HOST_PORT:-9000}
KEEP_LAMBDA_TEST_STACK=${KEEP_LAMBDA_TEST_STACK:-false}
PYTHON_BIN=${PYTHON_BIN:-python3}

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to run the Lambda test harness." >&2
  exit 127
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required to run the Lambda test harness." >&2
  exit 127
fi
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python is required to validate Lambda responses: ${PYTHON_BIN}" >&2
  exit 127
fi
INVOKE_URL="http://127.0.0.1:${LAMBDA_HOST_PORT}/2015-03-31/functions/function/invocations"
RESPONSE_FILE=$(mktemp)

cleanup() {
  rm -f "${RESPONSE_FILE}"
  if [[ "${KEEP_LAMBDA_TEST_STACK}" != "true" ]]; then
    docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" down --remove-orphans
  fi
}
trap cleanup EXIT

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Environment file not found: ${ENV_FILE}" >&2
  exit 2
fi
if [[ ! -f "${PAYLOAD_FILE}" ]]; then
  echo "Payload file not found: ${PAYLOAD_FILE}" >&2
  exit 2
fi
if [[ ! -f "${EXPECTED_FILE}" ]]; then
  echo "Expected response file not found: ${EXPECTED_FILE}" >&2
  exit 2
fi

docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up --build -d lambda-backend

"${PYTHON_BIN}" - "${INVOKE_URL}" <<'PY'
import sys
import time
import urllib.error
import urllib.request

url = sys.argv[1]
deadline = time.monotonic() + 60
last_error = "Lambda RIE endpoint was not reached"
while time.monotonic() < deadline:
    request = urllib.request.Request(url, data=b"{}", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            _ = response.read()
            sys.exit(0)
    except urllib.error.HTTPError as exc:
        _ = exc.read()
        sys.exit(0)
    except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
        last_error = str(exc)
        time.sleep(1)
print(last_error, file=sys.stderr)
sys.exit(1)
PY

curl --fail --silent --show-error \
  --header 'Content-Type: application/json' \
  --data-binary "@${PAYLOAD_FILE}" \
  "${INVOKE_URL}" > "${RESPONSE_FILE}"

"${PYTHON_BIN}" - "${EXPECTED_FILE}" "${RESPONSE_FILE}" <<'PY'
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_lambda_response(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    body = normalized.get("body")
    if isinstance(body, str) and body:
        try:
            normalized["body"] = json.loads(body)
        except json.JSONDecodeError:
            normalized["body"] = body
    return normalized


def assert_subset(expected: Any, actual: Any, path: str = "response") -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise AssertionError(f"{path} expected object, got {type(actual).__name__}")
        for key, expected_value in expected.items():
            if key not in actual:
                raise AssertionError(f"{path}.{key} is missing")
            assert_subset(expected_value, actual[key], f"{path}.{key}")
        return
    if expected != actual:
        raise AssertionError(f"{path} expected {expected!r}, got {actual!r}")


expected = load_json(sys.argv[1])
actual = normalize_lambda_response(load_json(sys.argv[2]))
assert_subset(expected, actual)
print(json.dumps(actual, indent=2, sort_keys=True))
PY
