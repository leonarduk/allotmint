# Lambda integration fixtures

This directory contains local fixtures for the Lambda invocation smoke harness.
The Makefile targets invoke each handler with a representative payload, write the
actual response under `tests/integration/actual/`, and use `jq` to assert the
response `statusCode` against the matching expected-response fixture.

## Directory layout

- `payloads/api_http_event.json` — API Gateway HTTP API v2 request for `GET /health`.
- `payloads/price_refresh_event.json` — EventBridge scheduled event for the price-refresh Lambda.
- `payloads/trading_agent_event.json` — EventBridge scheduled event for the trading-agent Lambda.
- `expected/api_http_response.json` — Expected response shape for the HTTP API health check.
- `expected/price_refresh_response.json` — Expected response shape for the price-refresh scheduled invocation.
- `expected/trading_agent_response.json` — Expected response shape for the trading-agent scheduled invocation.
- `invoke_lambda.py` — Deterministic local invocation helper used by `make lambda-test*`.

## Running the checks

Run all Lambda fixture checks:

```bash
make lambda-test
```

Run an individual check:

```bash
make lambda-test-api
make lambda-test-price-refresh
make lambda-test-trading-agent
```

The EventBridge handlers are normalized to a small Lambda-style envelope with a
`statusCode`, JSON `body`, and `isBase64Encoded` flag. The harness stubs external
price refresh and trading-agent side effects so these checks remain deterministic
and do not require public network access, AWS, or writable production data.

## Updating expected responses

When a handler intentionally changes its successful response contract:

1. Run the relevant `make lambda-test-*` target to regenerate the corresponding
   file under `tests/integration/actual/`.
2. Inspect the generated response and verify the changed shape is intentional.
3. Copy the actual response over the matching file in `tests/integration/expected/`.
4. Re-run `make lambda-test` and confirm each `jq` status-code assertion passes.

Keep the expected files focused on stable response shape. Avoid adding volatile
values unless the harness stubs them to deterministic values.
# Integration test payloads

Sample event payloads for invoking Lambda handlers via the local Docker test harness.

| File | Handler | Description |
|---|---|---|
| `payloads/api_http_event.json` | `lambda-api` (port 9010) | HTTP API Gateway v2 `GET /health` request |
| `payloads/scheduled_event.json` | `lambda-price-refresh` (port 9011), `lambda-trading-agent` (port 9012) | EventBridge scheduled event |

## Usage

Start the harness first, then use the `make lambda-test*` targets or invoke directly:

```bash
# Start all services
make lambda-up

# Invoke via make targets
make lambda-test           # API handler  -> GET /health
make lambda-test-price     # price-refresh handler
make lambda-test-trading   # trading-agent handler

# Or invoke directly with curl
curl -s -XPOST "http://localhost:9010/2015-03-31/functions/function/invocations" \
    -H "Content-Type: application/json" \
    -d @tests/integration/payloads/api_http_event.json | python -m json.tool

# Tear down
make lambda-down
```

To add a new payload, drop a `.json` file in `payloads/` and invoke the
relevant handler port directly with `curl`.
