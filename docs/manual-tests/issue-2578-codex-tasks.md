# Issue #2578 — Codex Implementation Tasks

This checklist turns issue #2578 into execution-ready tasks with explicit validation criteria and AGENTS.md workflow compliance.

## Task 0 — Scope lock and dependency gate

- [ ] Confirm dependency issue/PR #2572 is merged before finalizing VaR behavior.
- [ ] Confirm scope is limited to report sections 1–4 only (exclude section 5 key findings).
- [ ] Record whether ETF overlap/scenario outputs are intentionally out of scope for #2578.

**Definition of done**
- Scope and dependency status are documented in the issue/PR notes.

---

## Task 1 — Build acceptance-criteria traceability matrix

- [ ] Create a matrix with columns: AC item, code location, test case(s), command, pass condition.
- [ ] Seed matrix with `audit-report` template sections and report route ordering.

**Definition of done**
- Every acceptance criterion has at least one linked test and pass condition.

---

## Task 2 — Gap audit of current implementation

- [ ] Verify `audit-report` template section order and sources:
  - `portfolio.overview`
  - `portfolio.sectors`
  - `portfolio.regions`
  - `portfolio.concentration`
  - `portfolio.var`
- [ ] Verify builder wiring for all required portfolio report sources.
- [ ] Mark each AC row as pass/fail before changing code.

**Definition of done**
- A concise "gaps to fix" checklist exists.

---

## Task 3 — Implement targeted backend changes for failing AC rows

- [ ] Update `backend/reports.py` only where AC failures require changes.
- [ ] Ensure output rows for overview/sector/region/concentration/var are stable and deterministic for demo fixture inputs.
- [ ] Keep error handling explicit (no silent swallow patterns).

**Definition of done**
- All failing AC rows from Task 2 are resolved with minimal, focused diffs.

---

## Task 4 — Add or refine tests for AC completeness

- [ ] Add/update report data tests (`tests/test_reports.py`) for section payload shape and plausible values.
- [ ] Add/update route tests (`tests/test_reports_route.py`) for JSON section order and PDF response contract.
- [ ] Add/update PDF/report regression checks (`tests/test_reports_pdf.py` / `tests/test_reports_additional.py`) where needed.
- [ ] Add explicit checks for:
  - non-empty or expected-empty behavior,
  - concentration ordering and summary metrics,
  - VaR/Sharpe availability fallback behavior,
  - no regressions to existing built-in templates.

**Definition of done**
- AC matrix rows are all covered by deterministic tests.

---

## Task 5 — Validation run sequence

- [ ] Run targeted report test commands first:
  - `pytest tests/test_reports.py tests/test_reports_route.py tests/test_reports_pdf.py`
- [ ] Run additional related suites if touched:
  - `pytest tests/test_reports_additional.py tests/test_reports_validation.py`
- [ ] Run lint gate with zero warnings:
  - `make lint`

**Definition of done**
- Commands pass and results are captured in PR notes.

---

## Task 6 — Branch and PR hygiene (AGENTS.md)

- [ ] Work from non-main branch named with issue number (e.g., `feat/issue-2578-audit-report-pipeline`).
- [ ] Use focused commit messages.
- [ ] PR description includes:
  - what changed,
  - why it changed,
  - validation performed,
  - follow-ups/risks.

**Definition of done**
- Branch and PR satisfy repository branch/PR policy.

---

## Suggested execution order

1. Task 0
2. Task 1
3. Task 2
4. Task 3
5. Task 4
6. Task 5
7. Task 6
