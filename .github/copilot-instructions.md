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

## Code quality invariants (non-negotiable)

Derived from NASA/JPL Power of Ten — applicable subset only (C-specific rules omitted):

- **Function length**: ~60 lines max. Refactor before adding more to an oversized function.
- **Zero lint warnings**: `make lint` and `npm --prefix frontend run lint` must pass clean. Rewrite code that triggers false positives rather than suppressing them.
- **No silent error swallowing**: no bare `except: pass`, no silent `catch` blocks, no unhandled Promise rejections.
- **No ignored return values**: if you discard a return value intentionally, make it explicit and add a comment explaining why.
- **Minimum scope**: declare variables as late and as locally as possible; avoid unnecessary module-level mutable state.
