# Technical Support Guide

## Environment Setup
- **Python**: Install dependencies with `pip install -r requirements.txt`.
- **Frontend**: From `frontend`, install packages via `npm install`.
- **Configuration**: Review and adjust `config.yaml` for local or AWS environments.

## Common Troubleshooting Steps
- Verify that Python (3.12) and Node.js versions meet project requirements.
- Clear cached data under `data/cache/` if stale responses cause issues.
- Run `pytest` and `npm test` to check for failing tests before debugging.
- Ensure environment variables like `DATA_BUCKET` or API keys are correctly set.

## Log Locations
- Backend logs are written to `backend.log` as configured in `backend/logging.ini`.
- The `run_with_error_summary.py` helper records errors in `error_summary.log`.

## Escalation Contacts
- **Primary**: engineering@allotmint.example.com
- **Backup**: ops@allotmint.example.com
- **Emergency**: +44-20-0000-0000
