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
