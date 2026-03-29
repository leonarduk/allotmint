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

## Artifact directory convention

Create one run directory per execution:

```bash
RUN_DIR="artifacts/issue-2581/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_DIR"
```

All outputs for this run must live under `RUN_DIR`.

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

## 7) Negative tests (run before all other steps)

### 7.1 Empty portfolio
- Expect graceful response
- No crash

### 7.2 Single holding
- All endpoints still valid

### 7.3 Missing `key_findings.md`
- PDF still renders (section omitted)

### 7.4 Malformed `key_findings.md`
- No crash

Any failure: **P1**.

## 1) Local stack startup

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
- Backend responds in `< 2s`
- Frontend renders without visible error
- No crash logs in startup log

Else: FAIL and block all further steps.

## 2) Portfolio validation (strict)

Command:

```bash
curl -sS "$API_BASE/portfolio/$OWNER" -o "$RUN_DIR/portfolio_response.json"
```

Required external input:
- Same-day broker snapshot saved to `broker_snapshot.txt`

Rules:
1. Holdings integrity (hard fail/P1)
2. GBX scaling check (hard fail/P1)
3. Total value delta thresholds:
   - `<= 1%` PASS
   - `> 1% and <= 2%` P2 warning
   - `> 2%` P1 fail
4. Top 10 holdings each within 1% of broker (else P1)

## 3) Sector/Region validation

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
   - e.g. VWRL US weight in 50–70%
   - global ETF has at least 3 regions
3. Overlap visibility:
   - if VWRL and VUSA both present, US overlap should not be naively double-counted

## 4) VaR validation

Command:

```bash
curl -sS "$API_BASE/var/$OWNER" -o "$RUN_DIR/var.json"
```

Rules:
1. Structural hard fail: no NaN/null; value > 0 (P1)
2. Weak range check: `0.1% <= VaR <= 5%` (outside => P2)
3. Directional mandatory checks:
   - Cash-heavy scenario => VaR decreases materially
   - Equity-heavy scenario => VaR increases materially
   - Wrong direction => P1 fail
4. Dependency logging required:
   - lookback window
   - confidence level
   - data points count
   - missing values => P2

## 5) PDF audit report validation

Command:

```bash
curl -sS "$API_BASE/reports/$OWNER/audit-report?format=pdf" -o "$RUN_DIR/audit_report.pdf"
```

Rules:
1. Structural hard fail:
   - PDF opens
   - exactly 5 sections present
2. Data reconciliation hard fail:
   - total value
   - VaR
   - top holding
   - region %
   - sector %
   All must match endpoint values within rounding tolerance.
3. Formatting checks (P2):
   - `£` for currency
   - `%` for percentages
   - no raw floats
4. Layout checks (P2):
   - no clipping
   - no overlap

## 6) Demo report product gate

Setup:

```bash
mkdir -p data/accounts/demo-owner
$EDITOR data/accounts/demo-owner/key_findings.md
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

## 8) Strict closure criteria

Issue can close only if all are true:
- All steps executed with full evidence
- No open P1 issues
- No open P2 issues affecting correctness
- `demo_report.pdf` exists
- Step 6 answer is YES

Else: **DO NOT CLOSE**.
