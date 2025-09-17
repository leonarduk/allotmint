# Smoke Tests

Run quick checks against critical backend endpoints and the frontend smoke test page after deployment.

## Environment variables

- `SMOKE_URL` – base URL of the deployment to exercise for both backend and
  frontend suites.
- `TEST_ID_TOKEN` – optional ID token added as a `Bearer` token for backend endpoints requiring authentication.
- `SMOKE_AUTH_TOKEN` – optional bearer token stored in the frontend's `localStorage`; falls back to `TEST_ID_TOKEN` when unset.

## Usage

Run the backend and frontend suites together with a single command:

```bash
SMOKE_URL=https://example.com npm run smoke:test:all
```

Run only the backend API checks:

```bash
SMOKE_URL=https://example.com npm run smoke:test
```

Run only the frontend smoke page checks:

```bash
SMOKE_URL=https://example.com npm --prefix frontend run smoke:frontend
```

Include `TEST_ID_TOKEN` (and optionally `SMOKE_AUTH_TOKEN`) if the target
requires auth; the backend smoke runner forwards it as a bearer token:

```bash
SMOKE_URL=https://example.com TEST_ID_TOKEN=token npm run smoke:test:all
```

Each command exits non-zero if any check fails, allowing CI to fail fast.

The legacy `scripts/smoke-test.ps1` helper remains available for quick single-endpoint checks—provide one or more URLs via the `SMOKE_TEST_URLS` environment variable or as command-line arguments.
