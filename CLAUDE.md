# CLAUDE.md

This file gives Claude-style coding agents a fast, practical overview for working effectively in AllotMint. For the full repo policy, read `AGENTS.md` first; this file is the concise companion.

## Quick start

- Root guide of record: `AGENTS.md`
- Backend app factory: `backend.app:create_app`
- Local backend app: `backend.local_api.main:app`
- Frontend app entry: `frontend/src/main.tsx`
- Primary backend tests: top-level `tests/`

## Most useful commands

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
npm install
npm --prefix frontend install
make format
make lint
npm --prefix frontend run lint
npm --prefix frontend run test -- --run
bash scripts/bash/run-local-api.sh
npm --prefix frontend run dev
npm run smoke:test
npm run smoke:test:all
```

## High-signal warnings

- Do not trust stale prose that references `uvicorn app:app`; verify actual backend entrypoints first.
- Python config is split: root `pyproject.toml` handles pytest/coverage, while `backend/pyproject.toml` drives Black/isort/Ruff for the backend.
- Backend lint/format config currently targets Python 3.11 semantics even though some docs mention Python 3.12.
- Avoid editing generated or vendored folders like `node_modules/`.
- Be cautious around `data/`, auth toggles, and smoke-test identities; these often affect local demos and automated flows.
- Preserve cross-platform workflow parity when touching scripts because the repo uses both bash and PowerShell helpers.

## Preferred workflow

1. Inspect `git status` and avoid disturbing user changes.
2. Read the exact script/package targets you plan to mention or change.
3. Make the smallest coherent change.
4. Run the narrowest useful validation.
5. Update nearby docs when commands or behavior changed.

## If you touch specific areas

### Backend
- Keep domain logic out of routes when possible.
- Add/update pytest coverage under `tests/`.
- Mock external integrations instead of depending on live network access.

### Frontend
- Follow existing TypeScript/ESLint/Prettier conventions.
- Add/update Vitest coverage for logic changes.
- Capture screenshots for visible UI changes when tooling allows.

### Docs / scripts / workflows
- Look for duplicate instructions in `docs/`, `scripts/README.md`, root scripts, and workflow YAML.
- Prefer consolidating or correcting instructions rather than introducing a new conflicting variant.
