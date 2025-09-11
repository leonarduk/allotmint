# Smoke Tests

Run a quick check against key backend endpoints after deployment.

## Environment variables

- `SMOKE_URL` – base URL of the backend to test.
- `TEST_ID_TOKEN` – optional ID token added as a `Bearer` token for endpoints requiring authentication.

## Usage

```bash
SMOKE_URL=https://example.com npm run smoke:test
```

Include `TEST_ID_TOKEN` if the target requires auth:

```bash
SMOKE_URL=https://example.com TEST_ID_TOKEN=token npm run smoke:test
```

The script exits non-zero if any endpoint returns an unexpected status, allowing CI to fail fast.
