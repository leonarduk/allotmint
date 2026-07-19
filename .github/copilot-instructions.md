# GitHub Copilot / Kun Agent Instructions for AllotMint

Read `AGENTS.md` for full repository guidance. Use these short rules while generating code or PRs in this repo:

- **Workspace root:** Use the repository root as the base for all file reads and writes. If you are unsure, call `ls` or `bash pwd` to determine it at the start of each session.
- **Execution-first:** In your first response after loading a skill or receiving a clear action request, you MUST call the first relevant tool. Do not narrate your plan. Call the tool now.
- Create or switch to a non-`main` branch before editing files; if the checkout is dirty with unrelated work, use a clean worktree from `main`.
- For contributor setup/run-mode guidance, prefer `docs/CONTRIBUTOR_RUNBOOK.md`.
- Backend entrypoint: `backend.app:create_app`; local app: `backend.local_api.main:app`.
- Primary backend tests live in top-level `tests/`.
- Use `make format` and `make lint` for Python changes.
- Use `npm --prefix frontend run lint` and `npm --prefix frontend run test -- --run` for frontend changes.
- Prefer `bash scripts/bash/run-local-api.sh` for the local backend instead of outdated `uvicorn app:app` examples.
- Verify command names against actual `package.json`, `Makefile`, and scripts before updating docs.
- If your change implements an issue, include an auto-closing PR reference (for example: `Closes #1234`).
- When creating an issue, always use the template format from `.github/ISSUE_TEMPLATE/` and include all required sections: What, Why, How, Constraints, LLM tier, Success looks like, Failure looks like.
- When rebasing a PR, force-push to the same branch — don't create a new one.
- Keep changes out of generated dependency folders such as `node_modules/`.
- Be careful when changing `data/`, auth defaults, or smoke-test flows; these are tightly coupled to local development and demos.
- Preserve bash/PowerShell parity when editing shared developer workflows.
- For Codex browser-testing setup and POC commands, see `docs/CODEX_PLAYWRIGHT_MCP.md`.

## Code quality invariants (non-negotiable)

See `docs/CONTRIBUTING.md` ("Code quality invariants" section) for the
canonical rules: function length, zero lint warnings, no silent error
swallowing, no ignored return values, minimum scope.
