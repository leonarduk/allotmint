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
