# Technical Support Guide

## Environment Setup
- **Python**: Install dependencies with `pip install -r requirements.txt`.
- **Frontend**: From `frontend`, install packages via `npm install`.
- **Configuration**: Copy `config.example.yaml` to `config.yaml` and `.env.example`
  to `.env` for local or AWS environments. Provide secrets via environment variables.

## Data Quality Admin
- **Screen**: `/data-quality` shows a tabbed admin surface (Issues / Series /
  Holdings / Metadata / Audit) when the `enable_data_quality_admin` config flag
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
- **Holding writes** go through the same accounts-store write path as manual
  holdings; the shared demo dataset under `data/accounts/` is read-only and
  must be copied to a writable root before fixes can be applied.

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
