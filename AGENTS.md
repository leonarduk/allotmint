so # Repository Guidelines

## Project Structure & Module Organization
Backend FastAPI service lives in `backend/`, arranged by domain (`routes/`, `utils/`, `tasks/`) with data fixtures under `backend/tests/fixtures`. Shared integration suites sit in top-level `tests/`, mirroring backend package names for parity. The React/Vite client is in `frontend/` (`src/` for features, `tests/unit/` for Vitest specs), while IaC and scripts live in `cdk/`, `infra/`, and `scripts/` and deployment docs in `docs/`.

## Build, Test, and Development Commands
Install backend deps with `python -m pip install -r requirements.txt -r requirements-dev.txt` and run `uvicorn backend.app:create_app --factory --reload` for local APIs. Use `make format` before committing and `make lint` (Black, isort, Ruff, pytest) for the full gate. Frontend setup uses `npm install` inside `frontend/`, `npm run dev` for the SPA, `npm run build` for a production bundle, and `npm run deploy:aws` for CDN pushes; repo-level `npm run smoke:test` exercises the integrated smoke harness.

## Coding Style & Naming Conventions
Python code targets 3.12+, 4-space indentation, 120-character lines, and imports grouped by isort's Black profile; keep modules domain-oriented and prefer descriptive function names like `fetch_meta_timeseries`. TypeScript follows Prettier (`tabWidth: 2`, `singleQuote: true`, semicolons enforced) and ESLint; collocate component styles as `.module.css` when styling React views. Name tests `test_<feature>.py` or `<Component>.test.tsx` and keep generated assets out of version control per `.gitignore`.

## Testing Guidelines
Backend suites rely on pytest with fixtures in `tests/common/`; run targeted checks via `pytest tests/routes/test_accounts_api.py` and capture coverage with `pytest --cov=backend`. Frontend unit tests use Vitest (`npm run test` or `npm run coverage`), while browser flows run Playwright via `npm run smoke:frontend`; review `docs/SMOKE_TESTS.md` for required environment flags. Expect CI to execute backend integration and frontend test workflows, so ensure deterministic outcomes and include data stubs under `tests/data/`.

## Commit & Pull Request Guidelines
Follow the existing imperative commit style (`Fix local data discovery issues`, see `git log`) and keep scope focused. Before opening a PR, run `make lint`, `npm run lint`, and the relevant smoke scripts, then attach the command output or coverage deltas in the PR body. Link tracking issues, document config changes in `docs/` when applicable, and include screenshots for UI tweaks; reviewers expect concise summaries and validation steps.
