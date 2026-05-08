# Lambda integration fixtures

This directory contains local fixtures for the Lambda invocation smoke harness.
The Makefile targets invoke each handler with a representative payload, write the
actual response under `tests/integration/actual/`, and use `jq` to assert the
full response against the matching expected-response fixture.

## Directory layout

- `payloads/api_http_event.json` — API Gateway HTTP API v2 request for `GET /health`.
- `payloads/price_refresh_event.json` — EventBridge scheduled event for the price-refresh Lambda.
- `payloads/trading_agent_event.json` — EventBridge scheduled event for the trading-agent Lambda.
- `payloads/scheduled_event.json` — Generic EventBridge event used by the Docker-based curl targets.
- `expected/api_http_response.json` — Expected response shape for the HTTP API health check.
- `expected/price_refresh_response.json` — Expected response shape for the price-refresh scheduled invocation.
- `expected/trading_agent_response.json` — Expected response shape for the trading-agent scheduled invocation.
- `invoke_lambda.py` — Deterministic local invocation helper used by `make lambda-test*`.

## Running the checks (Python-based, no Docker required)

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

## Running the checks (Docker-based)

The older `make lambda-test-price` and `make lambda-test-trading` targets invoke
the handlers via `curl` against locally running Docker containers. Start the harness
first with `make lambda-up`, then use those targets. These targets do **not** assert
response shape — they print the raw handler output for manual inspection.

## Updating expected responses

When a handler intentionally changes its successful response contract:

1. Run the relevant `make lambda-test-*` target to regenerate the corresponding
   file under `tests/integration/actual/`.
2. Inspect the generated response and verify the changed shape is intentional.
3. Copy the actual response over the matching file in `tests/integration/expected/`.
4. Re-run `make lambda-test` and confirm each `jq` assertion passes.

Keep the expected files focused on stable response shape. Avoid adding volatile
values unless the harness stubs them to deterministic values. Note that
`_eventbridge_response` serialises handler results with `sort_keys=True`, so
expected fixture keys must be in alphabetical order.
