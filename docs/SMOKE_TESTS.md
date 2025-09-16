# Smoke Tests

Run quick checks against critical backend endpoints and the frontend smoke test page after deployment.

## Environment variables

- `SMOKE_URL` – base URL of the deployment to exercise.
- `TEST_ID_TOKEN` – optional ID token added as a `Bearer` token for backend endpoints requiring authentication.
- `SMOKE_AUTH_TOKEN` – optional bearer token stored in the frontend's `localStorage`; falls back to `TEST_ID_TOKEN` when unset.

## Usage

```bash
SMOKE_URL=https://example.com npm run smoke:test
```

```bash
SMOKE_URL=https://example.com npm --prefix frontend run smoke:frontend
```

Include `TEST_ID_TOKEN` if the target requires auth:

```bash
SMOKE_URL=https://example.com TEST_ID_TOKEN=token npm run smoke:test
```

```bash
SMOKE_URL=https://example.com TEST_ID_TOKEN=token npm --prefix frontend run smoke:frontend
```

Each command exits non-zero if any check fails, allowing CI to fail fast.
