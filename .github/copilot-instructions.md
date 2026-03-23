# GitHub Copilot Instructions for AllotMint

Read `AGENTS.md` for full repository guidance. Use these short rules while generating code or PRs in this repo:

- For contributor setup/run-mode guidance, prefer `docs/CONTRIBUTOR_RUNBOOK.md`.
- Backend entrypoint: `backend.app:create_app`; local app: `backend.local_api.main:app`.
- Primary backend tests live in top-level `tests/`.
- Use `make format` and `make lint` for Python changes.
- Use `npm --prefix frontend run lint` and `npm --prefix frontend run test -- --run` for frontend changes.
- Prefer `bash scripts/bash/run-local-api.sh` for the local backend instead of outdated `uvicorn app:app` examples.
- Verify command names against actual `package.json`, `Makefile`, and scripts before updating docs.
- Keep changes out of generated dependency folders such as `node_modules/`.
- Be careful when changing `data/`, auth defaults, or smoke-test flows; these are tightly coupled to local development and demos.
- Preserve bash/PowerShell parity when editing shared developer workflows.
