# UI behavior test plan (manual + AI-executable)

This test plan provides deterministic, step-by-step validation for the AllotMint frontend UI.

It is designed for:
- human testers running acceptance checks,
- AI agents running guided browser checks,
- triage after frontend routing or behavior changes.

It complements (does not replace) automated smoke coverage in:
- `docs/SMOKE_TESTS.md`
- `frontend/tests/smoke.spec.ts`

---

## 1) Scope and goals

### In scope
- App boot and route stability.
- Navigation coverage for high-value pages.
- Priority user journeys (portfolio + reporting).
- Evidence capture suitable for issue filing and regression tracking.

### Out of scope
- Pixel-perfect visual QA across all breakpoints.
- Replacing Playwright/Vitest automation.
- Exhaustive validation of every API edge case.

---

## 2) Pre-flight: environment setup

> Execute this section in order. Do not continue if any prerequisite fails.

### 2.1 Required software
1. Python and dependencies installed for backend.
2. Node.js/npm dependencies installed for root + frontend.

Reference install commands:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
npm install
npm --prefix frontend install
```

### 2.2 Start local services
1. Start backend:

```bash
bash scripts/bash/run-local-api.sh
```

2. Start frontend in another terminal:

```bash
npm --prefix frontend run dev
```

3. Open the frontend URL shown by Vite (usually `http://localhost:5173`).

### 2.3 Auth and identity assumptions
Use one of these setups:

- **A. Auth disabled/local login path** (preferred for local deterministic checks): backend config returns `disable_auth: true` and local identity values.
- **B. Token-based path**: provide `SMOKE_AUTH_TOKEN` or `TEST_ID_TOKEN` if your backend enforces auth.

### 2.4 Seed/data assumptions
- `demo-owner` data exists and is usable for owner-specific routes.
- Config, owners, and portfolio endpoints are reachable.
- If local data was reset, seed before continuing.

### 2.5 Pre-flight gate
Pass only if all are true:
1. Backend health endpoint returns HTTP 200.
2. Frontend root page loads without blank screen.
3. Browser console has no uncaught runtime errors during initial load.

If any fail, mark run **BLOCKED** and log a bug before continuing.

---

## 3) Execution rules (strict)

### 3.1 Result status vocabulary
Use only:
- **PASS**: observed behavior matches expected result exactly.
- **FAIL**: behavior differs from expected result.
- **BLOCKED**: prerequisite failed; step not executable.
- **N/A**: step intentionally skipped with documented reason.

### 3.2 Evidence required for each FAIL
For every failed step, capture:
1. Exact step ID (for example, `4.3.2`).
2. Actual URL.
3. Screenshot (or short screen recording for transient bugs).
4. Console/network error excerpt (if present).
5. Expected result vs actual result.

### 3.3 If a prerequisite fails
1. Mark dependent steps as **BLOCKED**.
2. File/append bug immediately.
3. Continue only with independent steps.

### 3.4 Bug logging template
Use this structure in GitHub issues/comments:

```md
### UI behavior test failure
- Step ID: <id>
- Route: <path>
- Environment: local/staging/prod + commit hash
- Expected: <expected behavior>
- Actual: <observed behavior>
- Severity: P1/P2/P3
- Evidence: <screenshot path + console excerpt>
```

Suggested severity:
- **P1**: crash, blank page, data corruption, blocked core journey.
- **P2**: functional mismatch with workaround.
- **P3**: minor UX/copy/layout issue.

---

## 4) Core navigation checks

> Goal: verify app bootstrap and route transitions are stable before deep behavior checks.

### 4.1 App bootstrap
1. Navigate to `/`.
2. Wait for initial loading to settle.
3. Confirm no white-screen crash.

Expected:
- App shell renders.
- Active route marker/mode indicates group/root mode.
- No uncaught console errors.

Failure signals:
- Infinite spinner.
- Blank viewport.
- Error boundary or red stack trace in console.

### 4.2 Route stability sweep
For each path below, open URL directly in browser and verify the expected visible marker:

| Route | Expected visible result |
|---|---|
| `/portfolio` | Owner/portfolio view renders |
| `/performance` | Performance view renders |
| `/transactions` | Transactions view renders |
| `/trading` | Trading view renders |
| `/reports` | Reports view renders |
| `/reports/new` | Heading “Create report template” visible |
| `/pension/forecast` | Heading “Pension Forecast” visible |
| `/returns/compare` | Return comparison page heading visible |
| `/compliance` | Heading “Compliance warnings” visible |
| `/smoke-test` | Heading “Smoke test” visible |

For each route, also verify:
1. URL remains stable after initial load (no unexpected redirect loop).
2. Back/forward browser navigation works.
3. No fatal console errors appear.

### 4.3 Optional extended route sweep
Run this when validating broader regressions:

`/instrument`, `/screener`, `/settings`, `/timeseries`, `/watchlist`, `/market`, `/allocation`, `/rebalance`, `/movers`, `/instrumentadmin`, `/dataadmin`, `/tax-tools`, `/scenario`, `/research/AAA`, `/virtual`, `/support`, `/alerts`, `/alert-settings`, `/goals`, `/trail`, `/metrics-explained`, `/trade-compliance`.

---

## 5) Page-level behavior checks (deterministic cases)

Use this structure for each route: prerequisite state → action → expected result → obvious failure signals.

### 5.1 Portfolio page (`/portfolio`)
- Prerequisite: owner data available (for example `demo-owner`).
- Action: open `/portfolio` then switch owner (if selector exists).
- Expected:
  1. Portfolio view remains active.
  2. Key summary and holdings sections render.
  3. Owner change updates visible data without route break.
- Failure signals:
  - owner selector empty unexpectedly,
  - stale data after owner switch,
  - route mode switches to unrelated page.

### 5.2 Performance page (`/performance` or `/performance/demo-owner`)
- Prerequisite: performance API reachable.
- Action: open route and wait for chart/table load.
- Expected:
  1. Performance mode/page marker visible.
  2. Data panel renders or explicit empty-state messaging shown.
  3. No crash when changing owner/date controls.
- Failure signals:
  - chart render exceptions,
  - NaN/undefined-heavy UI,
  - endless loading without timeout message.

### 5.3 Reports list + report creation (`/reports`, `/reports/new`)
- Prerequisite: report routes reachable.
- Action:
  1. Open `/reports`.
  2. Navigate to `/reports/new`.
  3. Fill minimal required fields and attempt save/preview action (if available).
- Expected:
  1. Reports page loads with stable navigation.
  2. “Create report template” heading shown on `/reports/new`.
  3. Validation errors are explicit and actionable when input invalid.
- Failure signals:
  - form submit no-op,
  - silent failure/toast mismatch,
  - route bounce away from report flow.

### 5.4 Returns compare (`/returns/compare`, `/returns/compare?owner=demo-owner`)
- Prerequisite: returns endpoint reachable.
- Action: load base and owner-filtered route.
- Expected:
  1. Return comparison heading visible.
  2. Owner-qualified route reflects owner context in heading/state.
  3. Controls change comparison view without full-page crash.
- Failure signals:
  - owner route ignores query param,
  - heading mismatch,
  - control interaction causes uncaught errors.

### 5.5 Pension forecast (`/pension/forecast`)
- Prerequisite: pension mode enabled in tabs/config.
- Action: open page and interact with primary controls/tabs.
- Expected:
  1. “Pension Forecast” heading visible.
  2. Route remains `/pension/forecast`.
  3. Pension mode stays active even if config tab state is indeterminate.
- Failure signals:
  - redirected to unrelated route,
  - heading missing,
  - mode marker not pension.

### 5.6 Virtual portfolios (`/virtual`)
- Prerequisite: virtual portfolios endpoint reachable.
- Action: load page; observe initial loading state.
- Expected:
  1. “Virtual Portfolios” heading appears.
  2. Loader appears then clears.
  3. Portfolio selector/list becomes interactive.
- Failure signals:
  - loader never clears,
  - missing selector despite successful response,
  - uncaught fetch/render errors.

---

## 6) Priority flows (run in this order)

### Flow A (P1): bootstrap → portfolio readiness
1. `/` loads.
2. Navigate to `/portfolio`.
3. Verify owner-scoped portfolio content.
4. Change owner/context and confirm UI updates.

Pass condition: no crashes, stable route, visible data/empty-state messaging.

### Flow B (P1): reporting path
1. Open `/reports`.
2. Open `/reports/new`.
3. Attempt minimal template creation path.
4. Confirm either success state or explicit validation guidance.

Pass condition: deterministic heading and actionable form behavior.

### Flow C (P2): performance and returns coherence
1. Open `/performance`.
2. Open `/returns/compare` and owner-qualified compare route.
3. Confirm headings/controls match selected context.

Pass condition: pages render and interactions do not crash.

### Flow D (P2): pension + compliance gates
1. Open `/pension/forecast`.
2. Open `/compliance`.
3. Confirm both pages render expected headings and maintain route stability.

Pass condition: no unexpected redirect/blank/error states.

---

## 7) Suggested run output format

Record your run in a markdown file, for example:

`artifacts/ui-behavior/<YYYYMMDDTHHMMSSZ>/ui-behavior-results.md`

Template:

```md
# UI behavior run result
- Date (UTC): <timestamp>
- Commit: <git sha>
- Base URL: <url>
- Tester: <name or agent>

## Summary
- PASS: <count>
- FAIL: <count>
- BLOCKED: <count>
- N/A: <count>

## Step results
- [PASS] 4.1 App bootstrap
- [FAIL] 5.3 Reports creation (see bug #xxxx)
- [BLOCKED] 5.6 Virtual portfolios (endpoint unavailable)

## Evidence index
- screenshots/<file>.png
- logs/console-errors.txt
- logs/network-failures.txt
```

---

## 8) Relationship to automated smoke tests

Use this manual/AI plan with automation, not instead of it:
- Fast automated route/assertion coverage: `frontend/tests/smoke.spec.ts`
- Combined backend/frontend smoke orchestration: `npm run smoke:test:all`
- Frontend-only smoke command: `npm --prefix frontend run smoke:frontend`

Recommended sequence for release confidence:
1. Run automated smoke checks first.
2. Run this UI behavior plan for acceptance-quality validation.
3. File regressions with evidence tied to step IDs in this document.

---

## 9) Maintenance guidance

Update this file whenever one of these changes:
1. Route paths or page headings.
2. Auth prerequisites or environment startup commands.
3. Priority user journeys (especially portfolio/reporting).
4. Failure signals that are no longer representative.

Maintenance checklist:
1. Confirm routes against `frontend/tests/smoke.spec.ts` and frontend route registration.
2. Keep deterministic numbering intact (avoid renumber churn unless structure changes).
3. Preserve explicit expected outputs (headings/markers/URL state).
4. Ensure examples still match available npm/scripts commands.

When a route is added/retired:
- add/remove it from section 4 (navigation checks),
- add/update any relevant section 5 behavior block,
- adjust section 6 priority flows if user value changes.
