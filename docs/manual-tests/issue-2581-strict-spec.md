# Issue #2581 Strict Execution Spec (Reproducible)

This runbook is the canonical strict manual/integrated execution guide for [Issue #2581](https://github.com/leonarduk/allotmint/issues/2581).

## Scope

This document is intentionally strict:
- No subjective pass criteria except where explicitly allowed.
- No PASS without full evidence artifacts.
- Any missing required artifact is an automatic FAIL.

## Inputs (must be defined before running)

- `OWNER`: portfolio owner slug used for endpoint calls.
- `GROUP_SLUG`: portfolio-group slug for regions endpoint.
- `API_BASE`: backend base URL (default: `http://localhost:8001`).
- `SNAPSHOT_TIME_UTC`: execution snapshot reference (ISO-8601 UTC).
- `BROKER_SNAPSHOT_TIME_UTC`: broker valuation timestamp (ISO-8601 UTC).
- `SYSTEM_FETCH_TIME_UTC`: system data fetch timestamp (ISO-8601 UTC).
- `FRONTEND_SCREENSHOT_PATH`: path to Step 1 screenshot evidence file.
- `STARTUP_LOG_PATH`: path to startup log captured during local stack startup.
- `BROKER_SNAPSHOT_PATH`: JSON broker snapshot file used for strict Step 2 reconciliation.
- `DEMO_PRODUCT_GATE_RESULT`: must be `YES` to satisfy Step 6 product gate.

## Artifact directory convention

Create one run directory per execution:

```bash
RUN_DIR="artifacts/issue-2581/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_DIR"
```

All outputs for this run must live under `RUN_DIR`.

## Durable evidence workflow (required for review/closure)

After each strict run, preserve evidence in `RUN_DIR` and use the generated summary artifacts as the canonical review payload.

### Canonical persisted path

- Local durable storage path: `artifacts/issue-2581/<timestamp>/`
- Use the timestamp format shown above: `YYYYMMDDTHHMMSSZ`
- Do not move files out of this run directory; append new runs as sibling timestamped folders.

### What must be attached/linked on GitHub issue #2581

Attach these artifacts directly to the issue comment (or link to a durable internal artifact store containing the same files):

- `summary.json`
- `summary_for_issue.md`
- `environment_lock.txt`
- `evidence_manifest.txt`
- `audit_report.pdf`
- `demo_report.pdf`

The issue closure comment must include links or attachments to these exact artifacts.
The runner writes these files into `RUN_DIR`; attaching or linking them on GitHub is a required manual closure step.

### What remains local by default

Keep these under `RUN_DIR` for deeper review, and attach them when requested:

- Step 1 local evidence (`frontend_screenshot.png`, `startup_log.txt`)
- Raw endpoint payloads (`portfolio_response.json`, `sectors.json`, `regions.json`, `var.json`)
- Manual external validation input (`broker_snapshot.txt`)
- Health, timing, and transport logs (`backend_health.json`, `backend_health.timing`, `*.stderr`, `*.status`, `*.check.log`)

### Runner-produced closure helper

`scripts/qa/run_issue_2581_strict.sh` writes:

- `summary.json` (machine-readable verdict)
- `summary_for_issue.md` (paste-ready markdown for GitHub comment)
- `evidence_manifest.txt` (explicit evidence inventory)

Use `summary_for_issue.md` as the starting point for the closure comment template.
`evidence_manifest.txt` is a plain-text inventory grouped into `Required issue attachments` and `Required local durable evidence`.

## 0) Global rules

### 0.1 Evidence requirement
A step cannot be PASS unless all required artifacts are present:
- Raw JSON response (saved file)
- Exact command executed
- UTC timestamp
- Screenshot or PDF where applicable

If any required artifact is missing: **AUTO FAIL**.

### 0.2 Data consistency rule
All validations must use a single snapshot window:
- Record `SNAPSHOT_TIME_UTC`, `BROKER_SNAPSHOT_TIME_UTC`, `SYSTEM_FETCH_TIME_UTC`
- Max allowed drift: `±5 minutes`

If violated: **STOP execution (invalid test run)**.

### 0.3 Environment lock
Record before Step 1:
- Git commit hash
- Docker image versions
- Python version
- Data sources (Yahoo / FT / etc.)

If environment changes mid-run: **INVALID RUN**.

### 0.4 Failure classification
- **P1** = incorrect financial output
- **P2** = missing/incorrect data
- **P3** = formatting / UX issue

Issue cannot close with any open P1/P2.

## Step 0) Negative tests (run before all other steps)

### 0.1 Empty portfolio
- Expect graceful response
- No crash

### 0.2 Single holding
- All endpoints still valid

### 0.3 Missing `key_findings.md`
- PDF still renders (section omitted)

### 0.4 Malformed `key_findings.md`
- No crash

Any failure: **P1**.

## Step 1) Local stack startup

Command:

```bash
make local-up
```

Required checks:
- Backend HTTP 200 at `/health`
- Frontend page loads without console errors

Required artifacts:
- `backend_health.json`
- `frontend_screenshot.png`
- `startup_log.txt`

Pass criteria (all required):
- Backend responds in `< 2s` **and** returns HTTP 200
- Frontend renders without visible error
- No crash logs in startup log

Else: FAIL and block all further steps.

## Step 2) Portfolio validation (strict)

Command:

```bash
curl -sS "$API_BASE/portfolio/$OWNER" -o "$RUN_DIR/portfolio_response.json"
```

Required external input:
- Same-day broker snapshot JSON provided at `BROKER_SNAPSHOT_PATH` (the runner copies it to `$RUN_DIR/broker_snapshot.txt`).
- Minimum broker snapshot fields:
  - portfolio-level numeric total (`total_value`, `portfolio_value`, or `total`)
  - holdings list entries with symbol (`ticker`/`symbol`) and numeric value (`market_value`/`value`/`position_value`/`current_value`/`amount`)
- If a non-JSON broker snapshot is provided, the runner records a P2 and skips automated Step 2 reconciliation (manual review required).

Rules:
1. Holdings integrity (hard fail/P1)
2. GBX scaling check (hard fail/P1): prices for instruments traded in GBX (pence sterling) must be divided by 100 before display in GBP. Any holding whose raw `price` field exceeds 10,000 and is displayed without the `/100` normalisation is a P1 fail. Verify the top 5 holdings by value against the broker snapshot; flag any price discrepancy > 1% that is consistent with a missing GBX-to-GBP conversion.
3. Total value delta thresholds:
   - `<= 1%` PASS
   - `> 1% and <= 2%` P2 warning
   - `> 2%` P1 fail
4. Top 10 holdings each within 1% of broker (else P1)

## Step 3) Sector/Region validation

Commands:

```bash
curl -sS "$API_BASE/portfolio/$OWNER/sectors" -o "$RUN_DIR/sectors.json"
curl -sS "$API_BASE/portfolio-group/$GROUP_SLUG/regions" -o "$RUN_DIR/regions.json"
```

Rules:
1. Structural hard fail:
   - no null values
   - no negative weights
   - sum(weights) = `100% ±1%`
2. ETF plausibility:
   - e.g. VWRL US weight in 50–70% (note: this range reflects approximate US weight as of 2025; verify against current fund factsheet before treating as a hard gate)
   - global ETF has at least 3 regions
3. Overlap visibility:
   - if VWRL and VUSA both present, US overlap should not be naively double-counted

## Step 4) VaR validation

Command:

```bash
curl -sS "$API_BASE/var/$OWNER" -o "$RUN_DIR/var.json"
```

Rules:
1. Structural hard fail: no NaN/null; value > 0 (P1)
2. Weak range check: `0.1% <= VaR <= 5%` of portfolio value (outside => P2). Confirm whether the returned value is an absolute £ amount or a percentage before applying this gate; record the interpretation in the evidence artifact.
3. Directional mandatory checks:
   - Cash-heavy scenario => VaR decreases materially
   - Equity-heavy scenario => VaR increases materially
   - Wrong direction => P1 fail
4. Dependency logging required:
   - lookback window
   - confidence level
   - data points count
   - missing values => P2

## Step 5) PDF audit report validation

Command:

```bash
curl -sS "$API_BASE/reports/$OWNER/audit-report?format=pdf" -o "$RUN_DIR/audit_report.pdf"
```

Rules:
1. Structural hard fail:
   - PDF opens without error
   - Section titles/order match the current built-in `audit-report` contract:
     1. Portfolio overview
     2. Sector allocation
     3. Region allocation
     4. Top holdings concentration
     5. Portfolio risk *(optional; omitted when VaR inputs are unavailable)*
     6. Key Findings *(optional; omitted when `key_findings.md` is absent or yields no valid lines)*
   - Section-count rule derived from the same contract:
     - minimum 4 sections (always-on core)
     - maximum 6 sections (all optional sections present)
     - `Key Findings`, when present, must be the final section
2. Data reconciliation hard fail:
   - total value
   - VaR
   - top holding
   - region %
   - sector %
   All must match endpoint values within rounding tolerance.
   - The strict runner now performs an explicit reconciliation pass against the saved endpoint payloads and emits `audit_reconciliation.check.log`.
3. Formatting checks (P2):
   - `£` for currency
   - `%` for percentages
   - no raw floats
4. Layout checks (P2):
   - no clipping
   - no overlap

## Step 6) Demo report product gate

Setup — write key findings to a file before generating the report:

```bash
mkdir -p data/accounts/demo-owner
cat > data/accounts/demo-owner/key_findings.md << 'EOF'
## Key Findings

- Portfolio is well-diversified across 4 regions and 8 sectors.
- Largest single-stock concentration risk: top holding represents X% of total value.
- VaR at 95% confidence over 1-day horizon: £Y.
- Recommended action: review bond allocation given current rate environment.
EOF
```

Generate:

```bash
curl -sS "$API_BASE/reports/demo-owner/audit-report?format=pdf&watermark=SAMPLE" -o "$RUN_DIR/demo_report.pdf"
```

Checks:
1. Objective:
   - stranger can identify total value, top risks, and key findings
   - no internal IDs, no unexplained raw tickers
2. Subjective gate (allowed only here):
   - Would you send this for £39?
   - YES = pass; NO requires reason
   - Runner gate: set `DEMO_PRODUCT_GATE_RESULT=YES`; any other value is a strict fail

## Step 7) Strict closure criteria

Issue can close only if all are true:
- All steps executed with full evidence
- No open P1 issues
- No open P2 issues affecting correctness
- `demo_report.pdf` exists
- Step 6 answer is YES

Else: **DO NOT CLOSE**.
