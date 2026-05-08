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
