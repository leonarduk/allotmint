# Report Workflow

This workflow explains how to produce a customer report with manually written Key Findings.

1. **Receive tickers**
   - Confirm the customer owner identifier and the ticker set that should be reviewed.

2. **Run analysis**
   - Prepare backend/frontend dependencies when setting up the environment or after dependency changes:
     - `python -m pip install -r requirements.txt -r requirements-dev.txt`
     - `npm install && npm --prefix frontend install`
   - Run backend locally for report-related checks:
     - `bash scripts/bash/run-local-api.sh`
   - Use existing smoke checks for confidence when required:
     - `npm run smoke:test`

3. **Create the key findings file**
   - Create this file for the owner:
     - `data/accounts/{owner}/key_findings.md`

4. **Write findings manually**
   - Findings are **NOT auto-generated**.
   - Write short, specific, numeric findings (one finding per line or bullet).
   - Accepted length constraint: each finding must be no more than 500 characters.
   - There is no minimum length requirement beyond non-empty text.
   - Prefer `- `, `* `, or `1. ` style bullets for readability.
   - Findings longer than 500 characters are skipped and logged as an error during report generation rather than failing the whole report.

5. **Generate report**
   - Generate the `audit-report` document/PDF using the existing report route or report generation workflow.

6. **Send report**
   - Send the final PDF report to the customer using the normal reporting channel.
