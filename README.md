# AllotMint 🌱💷

[![codecov](https://codecov.io/gh/leonarduk/allotmint/branch/main/graph/badge.svg)](https://codecov.io/gh/leonarduk/allotmint)

AllotMint is a family investing platform with a FastAPI backend, React frontend, and AWS deployment support.

- Product and architecture overview: [docs/README.md](docs/README.md)
- Local setup and contributor workflow: [docs/CONTRIBUTOR_RUNBOOK.md](docs/CONTRIBUTOR_RUNBOOK.md)
- User-oriented setup/readme: [docs/USER_README.md](docs/USER_README.md)

## Coverage reporting

GitHub Actions uploads both backend (`coverage.xml`) and frontend (`frontend/coverage/lcov.info`) coverage reports to Codecov on pull requests and pushes to `main`.



## Local Docker development

Run the full AllotMint stack (backend + frontend) with real local fixture data.

### Prerequisites

- Docker Engine 24+
- Docker Compose v2 (`docker compose`)

### Quick start

1. Copy local environment defaults:

   ```bash
   cp .env.local.example .env.local
   ```

2. Start both services:

   ```bash
   make local-up
   ```

3. Open:

   - Frontend UI: http://localhost:3000
   - Backend OpenAPI docs: http://localhost:8000/docs

The backend bind-mounts `./data` into `/app/data` so portfolio/account fixtures are served live from your local repository checkout.

### Stop services

```bash
make local-down
```

## Local network setup (LAN testing)

Use these steps when you want phones/tablets/laptops on your WiFi network to hit a backend running on your development machine.

### Prerequisites

- Python 3.11+ with dependencies installed:
  - `python -m pip install -r requirements.txt -r requirements-dev.txt`
  - (CI/CD workflows run on Python 3.12)
- Node.js 20+ for frontend tooling.
- Local environment defaults:
  - `cp .env.local.example .env.local`

### Steps

1. Set runtime API base URL for the frontend in `frontend/public/config.json`:

   ```json
   {
     "apiBaseUrl": "http://<YOUR-LAN-IP>:8000"
   }
   ```

2. Start the backend and bind to all interfaces (`0.0.0.0`):

   ```bash
   bash scripts/bash/run-local-api.sh
   ```

3. Start the frontend:

   ```bash
   npm --prefix frontend run dev -- --host 0.0.0.0
   ```

4. Allow inbound TCP `8000` in your machine firewall so other LAN devices can reach the FastAPI backend.

### Notes

- `frontend/public/config.json` is fetched with `cache: "no-store"` in the SPA bootstrap and deployed with `Cache-Control: no-cache, no-store, must-revalidate` in CDK, so backend URL changes should take effect immediately.
- iOS Safari blocks mixed content (`https://...` frontend calling `http://...` API). For LAN testing, serve frontend over HTTP (or use HTTPS end-to-end).
- This project does not currently register a service worker, so `/config.json` is not intercepted by client-side SW caching.
