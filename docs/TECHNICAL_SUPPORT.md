# Technical Support Guide

## Environment Setup
- **Python**: Install dependencies with `pip install -r requirements.txt`.
- **Frontend**: From `frontend`, install packages via `npm install`.
- **Configuration**: Copy `config.example.yaml` to `config.yaml` and `.env.example`
  to `.env` for local or AWS environments. Provide secrets via environment variables.

## Data Quality Admin
- **Screen**: `/data-quality` shows a tabbed admin surface (Issues / Steward
  report / Series / Holdings / Metadata / Audit) when the `enable_data_quality_admin` config flag
  is enabled (default: on). When disabled, the page falls back to the original
  read-only series table.
- **Issues tab**: lists unified issues across holdings (wrong exchange,
  unresolved ticker, missing series), cached series (stale, gaps, duplicates,
  outliers, ticker mismatch) and instrument metadata. Filter by type, severity
  or ticker; every fix has a Preview (before → after) and, when applied,
  creates a `.bak` backup and an append-only audit record.
- **Audit tab**: shows the JSONL audit trail (`{data_root}/audit/`); reversible
  actions (wrong-exchange corrections, dedupe, ticker normalization) can be
  undone from there.
- **Steward report tab** (#10471): an AI agent triages the open issues on held
  instruments (high severity and largest £ exposure first), investigates each
  with read-only MCP tools only, and groups them as *Fix available*, *Needs
  human* or *Not a real problem*, with the tool calls and results behind each
  verdict. It never writes data: *Apply* calls the same fix endpoint as the
  Issues tab, after confirmation. It uses the chat assistant's provider
  (`CHAT_PROVIDER`/`CHAT_MODEL`, Ollama by default locally, so free) and needs
  `MCP_SERVER_URL`. Locally, *Run now* calls `POST /data-steward/run`; on AWS
  `DataStewardLambda` runs nightly at 02:00 UTC (set the `mcp_server_url` and
  `mcp_server_function_arn` CDK context). Reports are saved as
  `{data_root}/data_steward/reports/<date>.json` plus `latest.json` (or under
  `DATA_STEWARD_REPORTS_URI`). Cost is capped by `DATA_STEWARD_MAX_ISSUES`
  (default 10) and `DATA_STEWARD_MAX_TOOL_CALLS` per issue (default 6); a
  failed run still saves a report listing its errors.
- **Holding writes** go through the same accounts-store write path as manual
  holdings; the shared demo dataset under `data/accounts/` is read-only and
  must be copied to a writable root before fixes can be applied.

## Updating a Local Install
- **Screen**: the Support page's **Update app** section (local deployments
  only — `server.app_env: local`). It is hidden on AWS, where the
  `/support/app-update` routes are not registered; AWS is updated by the
  deploy pipeline, not from inside the running app.
- **What it does**: *Check for updates* runs `git fetch`; *Update now*
  fast-forwards the current branch to its upstream (`git merge --ff-only`).
  It refuses when tracked files have uncommitted changes, HEAD is detached,
  the branch has no upstream, or there are local commits not on the upstream.
- **After updating**: the backend restarts itself when started with reload
  enabled (`server.reload`, the default for `run-local-api.sh` /
  `run-backend.ps1`) and the Vite dev server hot-reloads the frontend. If the
  result lists changed dependency manifests, re-run `pip install` /
  `npm install` and restart — the update never installs dependencies itself.
- **Access**: open when auth is disabled (typical local setup); with auth
  enabled it is restricted to `auth.allowed_emails`. See
  `backend/routes/app_update.py`.

## Restarting the Local MCP Server
- **Screen**: the Support page's **MCP server** panel, next to the MCP tools
  list (local deployments only — `server.app_env: local`; on AWS the MCP
  server is a Lambda and the `/support/mcp-server` routes are not registered).
- **Status**: whether the server listens on its port (from `MCP_SERVER_URL`,
  else `MCP_SERVER_PORT`, else 8001), its PID and start time, the
  allotmint-pro checkout and HEAD commit, the `tools/list` tool count, and a
  warning when a newer commit or newer `.py` file exists in allotmint-pro or
  allotmint `backend/` than the running process.
- **Restart**: stops the server and starts a fresh one in the background by
  running the same foreground launcher a terminal would
  (`scripts/run-mcp-server.ps1` on Windows, `scripts/bash/run-mcp-server.sh`
  elsewhere), so env loading, the allotmint-pro lookup and `PYTHONPATH` match.
  Output is appended to `logs/mcp-server.log`. It then waits for the port and
  a successful `tools/list` (90 s), and returns the new PID and tool count, or
  the reason and the new log lines.
- **What it will stop**: only the process listening on the configured local
  port, and only if its command line contains
  `allotmint_pro.mcp_server.app:app`. On Windows the venv launcher parent
  `python.exe` with the same command line is stopped too; a shell or
  `run-backend.ps1` that started it is not. A port held by anything else, or a
  non-localhost `MCP_SERVER_URL`, refuses the restart.
- **Platform differences**: the port owner is found with `Get-NetTCPConnection`
  / `Win32_Process` on Windows and `lsof` / `ps` elsewhere (`lsof` must be
  installed). Windows stops with `TerminateProcess`; elsewhere SIGTERM, then
  SIGKILL if the port is still held after 15 s.
- **Foreground terminals**: if the server was started with `run-mcp-server`
  in a terminal, restarting ends that terminal's server; the new one runs in
  the background. A server restarted from here is no longer tied to
  `run-backend.ps1` / `run-local-api.sh`, so it keeps running after the
  backend script exits.
- **Access**: same owner gate as **Update app**. See
  `backend/routes/mcp_server_admin.py`.

## Common Troubleshooting Steps
- Verify that Python (3.11+) and Node.js versions meet project requirements
  (CI/CD uses Python 3.12).
- Clear cached data under `data/cache/` if stale responses cause issues.
- Run `pytest` and `npm test` to check for failing tests before debugging.
  Sample account JSON files in `data/accounts/` allow these tests to run
  without extra setup.
- Ensure environment variables like `DATA_BUCKET` or API keys are correctly set.

## Log Locations
- Backend logs are written to `logs/backend.log` (JSON lines) as configured in
  `backend/logging.ini`. `scripts/run-backend.ps1` creates the `logs/` folder
  before starting the server.
- Frontend dev-server output is written to `logs/frontend.log` by
  `scripts/run-frontend.ps1`, in addition to streaming to the console.
- The `run_with_error_summary.py` helper records errors in `error_summary.log`.
- A root-level `logging.ini` exists only to tune third-party loggers like `yfinance`.
- On AWS, the Support page's Logs panel (`GET /logs`) reads recent output from
  the BackendLambda's CloudWatch log group instead of a local file — the
  Lambda filesystem has no `logs/backend.log`. See `backend/routes/logs.py`.

## Escalation Contacts
- **Primary**: steveleonard11@gmail.com
- **Backup**: stephen_leonard@hotmail.com
