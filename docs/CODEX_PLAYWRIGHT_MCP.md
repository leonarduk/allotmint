# Codex Playwright MCP setup

This guide provides exact, copy/paste-ready registration steps for enabling a Playwright MCP server with Codex.

## 1) Prerequisite

Install Node.js (18+) so `npx` is available.

## 2) Codex + MCP registration (exact steps)

### Option A (recommended): Codex CLI config file

1. Create the Codex config directory and file:

```bash
mkdir -p ~/.codex
cat > ~/.codex/config.toml <<'TOML'
[mcp_servers.playwright]
command = "npx"
args = ["-y", "@playwright/mcp@latest"]
TOML
```

2. Save the file at this exact location:
   - macOS/Linux: `~/.codex/config.toml`
   - Windows (PowerShell): `$HOME/.codex/config.toml`

This location is where Codex CLI reads MCP server registrations.

### Option B: Codex app MCP settings UI

If you are using the Codex app UI instead of the CLI config file:

1. Open **Settings**.
2. Open **MCP Settings** (or **Tools → MCP Servers**, depending on app version).
3. Add a custom server with:
   - Name: `playwright`
   - Command: `npx`
   - Args: `-y @playwright/mcp@latest`
4. Save and restart the Codex session for the workspace.

## 3) Verify registration

Run this command and confirm `playwright` appears in the output:

```bash
codex mcp list
```

If `playwright` is not listed, re-check the config path and restart Codex.

## 4) Workspace note

If your environment uses per-workspace MCP policies, ensure the `playwright` server is enabled for this repository after registration.
# Codex + Playwright MCP browser-testing plan

This document captures the recommended setup for AI-driven browser testing in AllotMint, plus a minimal proof-of-concept (POC) path that can be validated today.

## 1. Recommendation (default approach)

Use **both** of these paths, with clear roles:

1. **Deterministic regression checks (default for CI and repeatable local validation):**
   - Keep using repository-owned Playwright tests under `frontend/tests/`.
   - Run these with standard `npm` scripts.
2. **Exploratory AI-driven browser control (default for interactive debugging and discovery):**
   - Use Codex with a Playwright MCP server so the agent can drive a real browser session.
   - Treat this as an interactive development aid, not a replacement for deterministic tests.

Why this split works best here:

- deterministic tests are versioned, reviewable, and CI-friendly;
- MCP-driven sessions are stronger for ad-hoc exploration, triage, and reproducing UX regressions quickly;
- both modes can share the same local app startup and smoke URL assumptions.

## 2. Local setup

### Prerequisites

- Python + backend dependencies installed.
- Node dependencies installed at root and `frontend/`.
- Chromium installable through Playwright (`playwright install chromium`).
- A running backend + frontend stack, or at least frontend preview for isolated route checks.

### Install commands

From repo root:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
npm install
npm --prefix frontend install
```

Install Playwright browser runtime:

```bash
npm --prefix frontend exec playwright install chromium
```

### Codex + MCP registration (what to configure)

Use a Playwright MCP server configuration in your Codex environment (for example Microsoft `playwright-mcp`) and enable it for this workspace.

Minimum config expectations:

- MCP server is registered and visible to Codex.
- Server can launch a browser in your local environment.
- Codex has access to your local app URL (typically `http://localhost:5173`).

### Verify Codex browser control works

1. Start backend:

   ```bash
   bash scripts/bash/run-local-api.sh
   ```

2. Start frontend dev server (separate shell):

   ```bash
   npm --prefix frontend run dev
   ```

3. In Codex with Playwright MCP enabled, ask Codex to:
   - open `http://localhost:5173/smoke-test`,
   - verify the `Smoke test` heading,
   - navigate to `/portfolio`,
   - verify the route marker indicates owner mode.

Success evidence: Codex returns successful browser actions/assertions and no browser-launch errors from MCP.

## 3. Repo integration (implemented)

### Files and scripts

- Added `frontend` script `smoke:codex:poc` for a minimal deterministic browser POC.
- Added root script alias `smoke:test:codex:poc` so contributors can run it from repo root.
- Added this document as the canonical Codex+MCP plan.

### Scope boundaries

- No broad new test framework was introduced.
- No CI workflow was changed in this issue.
- No speculative infrastructure was added.

## 4. Minimal proof of concept

The implemented POC flow uses an existing deterministic Playwright scenario (`bootstrap to portfolio happy path`) from `frontend/tests/smoke.spec.ts`:

1. Build preview frontend.
2. Launch Playwright against preview server.
3. Navigate to `/portfolio`.
4. Assert route and mode markers.
5. Verify owner selector is visible (meaningful UI interaction surface is present and loaded).

This gives a small but real browser-based end-to-end check while preserving existing smoke-test patterns.

## 5. Validation commands

### Deterministic automated POC

From repo root:

```bash
npm run smoke:test:codex:poc
```

Equivalent frontend-only command:

```bash
npm --prefix frontend run smoke:codex:poc
```

Expected success evidence:

- Playwright exits with success.
- The `bootstrap to portfolio happy path` test passes.
- No preview server startup failures.

### Exploratory AI-driven browser control

- Start local stack (`run-local-api.sh` + `frontend dev`).
- Run Codex with Playwright MCP.
- Ask Codex to execute the same navigation/assertion steps interactively.

Expected success evidence:

- Browser starts via MCP.
- Codex can navigate and report assertions.
- Failures are actionable (selector mismatch, route marker mismatch, or network/auth errors).

## 6. Risks, limitations, and deferrals

### Real risks

- **Flaky UI automation:** dynamic loading and network timing can make selectors intermittently unavailable.
- **Auth/session mismatch:** local auth-disabled mode and protected deployment mode can behave differently.
- **MCP/browser startup issues:** local sandboxing, missing browser binaries, or server registration errors can block exploratory mode.
- **CI limitations for MCP mode:** interactive agent-driven workflows are not directly CI-native.
- **Slower exploratory loops:** agentic interaction is slower than direct deterministic Playwright runs for regression gating.

### Explicit deferrals

- No CI integration for MCP exploratory runs yet.
- No broad test-suite restructure.
- No new auth harness solely for MCP scenarios.

Use deterministic Playwright tests for regression confidence, and MCP-driven Codex sessions for exploratory diagnosis.
