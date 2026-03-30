# UI behavior test plan (manual + AI-executable)

This runbook is a **single executable checklist** for validating frontend behavior end-to-end.

It is intended for:
- human testers,
- AI agents,
- release/triage workflows.

Related automation (complementary, not replaced):
- `docs/SMOKE_TESTS.md`
- `frontend/tests/smoke.spec.ts`

---

## 1) Environment setup

## 1.1 Required installs

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
npm install
npm --prefix frontend install
```

## 1.2 Start local stack

Terminal A (backend):

```bash
bash scripts/bash/run-local-api.sh
```

Terminal B (frontend):

```bash
npm --prefix frontend run dev
```

Use the Vite URL (normally `http://localhost:5173`).

## 1.3 Auth / identity assumptions

Run one of these modes:
1. **Local auth-disabled mode (preferred)**: backend config allows local login identity.
2. **Token mode**: set `SMOKE_AUTH_TOKEN` (or `TEST_ID_TOKEN`) if auth is enforced.

## 1.4 Seed data assumptions

Required baseline:
- `demo-owner` exists,
- `/config`, `/owners`, and portfolio endpoints are reachable.

## 1.5 Pre-flight gate (must pass before execution)

| Step ID | Check | Pass condition |
|---|---|---|
| 1.5.1 | Backend health | `/health` returns HTTP 200 |
| 1.5.2 | Frontend boot | root page renders (not blank) |
| 1.5.3 | Console sanity | no uncaught runtime errors on load |

If any pre-flight step fails:
1. mark run **BLOCKED**,
2. log bug,
3. skip dependent steps.

---

## 2) Execution rules

## 2.1 Status vocabulary (only these values)
- **PASS**: expected result observed.
- **FAIL**: expected result not observed.
- **BLOCKED**: prerequisite failed.
- **N/A**: intentionally skipped with reason.

## 2.2 Required evidence for every FAIL
- Step ID,
- URL,
- screenshot or short recording,
- console/network error excerpt (if present),
- expected vs actual behavior.

## 2.3 Evidence capture commands (optional but recommended)

Screenshot to deterministic path:

```bash
mkdir -p artifacts/ui-behavior/$RUN_ID/screenshots
# save browser screenshot manually as:
# artifacts/ui-behavior/$RUN_ID/screenshots/<step-id>.png
```

Console/network notes:

```bash
mkdir -p artifacts/ui-behavior/$RUN_ID/logs
# save extracted errors as:
# artifacts/ui-behavior/$RUN_ID/logs/console-errors.txt
# artifacts/ui-behavior/$RUN_ID/logs/network-errors.txt
```

## 2.4 Bug report template

```md
### UI behavior test failure
- Step ID: <id>
- Route: <path>
- Environment: <local/staging/prod + commit>
- Expected: <expected behavior>
- Actual: <observed behavior>
- Severity: <P1/P2/P3>
- Evidence: <artifact paths>
```

Severity guide:
- **P1**: crash, blank screen, corrupted primary flow.
- **P2**: functional mismatch with workaround.
- **P3**: minor UX/copy/layout issue.

---

## 3) Core navigation checks (smoke-level)

Run in order.

| Step ID | Route | Action | Expected visible result | Failure signals |
|---|---|---|---|---|
| 3.1 | `/` | open route | app shell renders, route is stable | blank page, crash loop |
| 3.2 | `/portfolio` | direct-load URL | portfolio/owner view visible | redirect loop, crash |
| 3.3 | `/performance` | direct-load URL | performance view visible | chart/runtime exception |
| 3.4 | `/transactions` | direct-load URL | transactions view visible | blank state + errors |
| 3.5 | `/trading` | direct-load URL | trading view visible | route bounce |
| 3.6 | `/reports` | direct-load URL | reports page visible | crash/empty shell |
| 3.7 | `/reports/new` | direct-load URL | heading `Create report template` | missing heading |
| 3.8 | `/pension/forecast` | direct-load URL | heading `Pension Forecast` | wrong route/mode |
| 3.9 | `/returns/compare` | direct-load URL | return comparison heading visible | render exception |
| 3.10 | `/compliance` | direct-load URL | heading `Compliance warnings` | missing heading |
| 3.11 | `/smoke-test` | direct-load URL | heading `Smoke test` | page crash |

For each step above, also validate:
1. URL does not oscillate after load.
2. Browser back/forward works.
3. No fatal console errors.

Optional extended sweep:
`/instrument`, `/screener`, `/settings`, `/timeseries`, `/watchlist`, `/market`, `/allocation`, `/rebalance`, `/movers`, `/instrumentadmin`, `/dataadmin`, `/tax-tools`, `/scenario`, `/research/AAA`, `/virtual`, `/support`, `/alerts`, `/alert-settings`, `/goals`, `/trail`, `/metrics-explained`, `/trade-compliance`.

---

## 4) Page-level behavior checks (deeper)

## 4.1 Portfolio flow (`/portfolio`)
- Prerequisite: owner data available (e.g. `demo-owner`).
- Action: open route, then change owner if selector exists.
- Expected:
  1. portfolio mode remains active,
  2. summary/holdings render or explicit empty-state,
  3. owner switch updates data without route break.
- Failure signals: empty selector unexpectedly, stale data, mode switch to unrelated page.

## 4.2 Performance flow (`/performance` or `/performance/demo-owner`)
- Prerequisite: performance data endpoint reachable.
- Action: open page and interact with primary controls (owner/date).
- Expected: page remains stable, data panel/chart/table renders (or explicit empty-state), no uncaught errors.
- Failure signals: NaN/undefined-heavy UI, endless spinner, control interaction crash.

## 4.3 Reporting flow (`/reports` + `/reports/new`)
- Prerequisite: report routes reachable.
- Action:
  1. open `/reports`,
  2. open `/reports/new`,
  3. attempt minimal create/preview action.
- Expected: deterministic heading on new page, actionable validation on invalid input, no silent no-op.
- Failure signals: form submit does nothing, unexpected route bounce, silent failure.

## 4.4 Returns compare (`/returns/compare`, `/returns/compare?owner=demo-owner`)
- Prerequisite: returns compare endpoint reachable.
- Action: load both routes and modify compare controls.
- Expected: owner-qualified route reflects owner context; controls update comparison without crash.
- Failure signals: query ignored, heading/state mismatch, control-driven crash.

## 4.5 Pension forecast (`/pension/forecast`)
- Prerequisite: pension tab/config available.
- Action: open page and use main controls.
- Expected:
  1. heading `Pension Forecast` visible,
  2. pathname stays `/pension/forecast`,
  3. pension mode remains active.
- Failure signals: redirect to wrong page, missing heading, wrong mode marker.

## 4.6 Virtual portfolios (`/virtual`)
- Prerequisite: virtual portfolio endpoint reachable.
- Action: open route and wait for load cycle.
- Expected: heading visible; loader appears then clears; selector/list becomes interactive.
- Failure signals: loader never clears, selector absent after successful response, uncaught fetch/render errors.

---

## 5) Priority journeys (run first)

| Priority | Journey | Required steps |
|---|---|---|
| P1 | Bootstrap → Portfolio readiness | 3.1 → 3.2 → 4.1 |
| P1 | Reporting | 3.6 → 3.7 → 4.3 |
| P2 | Performance + Returns coherence | 3.3 → 3.9 → 4.2 → 4.4 |
| P2 | Pension + Compliance gate | 3.8 → 3.10 → 4.5 |

Pass rule for each journey: no crash/blank/error boundary and expected headings/modes remain stable.

---

## 6) Run output format (required)

Create one run folder:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "artifacts/ui-behavior/$RUN_ID"
```

Store a summary file at:
`artifacts/ui-behavior/<RUN_ID>/ui-behavior-results.md`

Template:

```md
# UI behavior run result
- Date (UTC): <timestamp>
- Commit: <git sha>
- Base URL: <url>
- Tester: <human or agent>

## Summary
- PASS: <count>
- FAIL: <count>
- BLOCKED: <count>
- N/A: <count>

## Step results
- [PASS] 3.1 Root boot
- [FAIL] 4.3 Reporting create action
- [BLOCKED] 4.6 Virtual portfolios (endpoint unavailable)

## Evidence
- screenshots/<step-id>.png
- logs/console-errors.txt
- logs/network-errors.txt
```

---

## 7) Relationship to automated smoke tests

Use this plan **with** automation:
1. run smoke automation first,
2. run this manual/AI behavior plan,
3. file regressions referencing step IDs from this document.

Automation references:
- route/assertion smoke coverage: `frontend/tests/smoke.spec.ts`
- combined smoke command: `npm run smoke:test:all`
- frontend smoke command: `npm --prefix frontend run smoke:frontend`

---

## 8) Maintenance guidance

Update this file when any of these change:
1. routes, headings, or mode markers,
2. startup/auth requirements,
3. priority journeys (especially portfolio/reporting),
4. expected failure signals.

Maintenance checklist:
1. verify route/heading assertions against `frontend/tests/smoke.spec.ts`,
2. keep deterministic step IDs stable,
3. keep expected outputs explicit,
4. verify referenced commands still exist.
