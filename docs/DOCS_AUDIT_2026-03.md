# Docs audit (March 2026)

Issue: https://github.com/leonarduk/allotmint/issues/2658

This audit reviewed files under `docs/` and categorized each as **keep**, **update**, or **remove**.

## Outcome summary

- Retained and indexed canonical docs that describe active contributor, deployment, support, and product workflows.
- Rewrote `docs/README.md` to be a true index of maintained documents.
- Removed stale planning/task artifacts and issue-specific manual execution specs.
- Removed checked-in `.base64` and `.url` asset payload/reference files that were not referenced by code or docs.

## File-by-file disposition

### Kept
- `docs/CONTRIBUTOR_RUNBOOK.md`
- `docs/DEPLOY.md`
- `docs/OBSERVABILITY.md`
- `docs/REPORT_WORKFLOW.md`
- `docs/SECURITY.md`
- `docs/SMOKE_TESTS.md`
- `docs/TECHNICAL_SUPPORT.md`
- `docs/USER_README.md`
- `docs/android-client.md`
- `docs/frontend-page-manifest.md`
- `docs/historical_scenario_schema.md`
- `docs/performance-caching.md`
- `docs/screener-builder.md`
- `docs/transactions.md`
- `docs/value_at_risk.md`
- `docs/assets/qa-screenshots/.gitkeep`
- `docs/assets/qa-screenshots/README.md`
- `docs/assets/siteplan/README.md`

### Updated
- `docs/README.md` (rewritten as canonical docs index)

### Removed

#### Planning/backlog/task-tracking docs
- `docs/MONTH1_PLAN.md`
- `docs/menu_codex_tasks.md`
- `docs/menu_initiative_tasks.md`
- `docs/issue-2588-codex-implementation-tasks.md`

#### Issue-specific manual test/checklist docs
- `docs/manual-tests/issue-2578-codex-tasks.md`
- `docs/manual-tests/issue-2581-strict-spec.md`
- `docs/manual-tests/ui-behavior-test-plan.md`

#### Checked-in asset payload/reference files
- `docs/assets/DejaVuSans.ttf.base64`
- `docs/assets/DejaVuSans.ttf.url`
- `docs/assets/default-avatar.base64`
- `docs/assets/default-avatar.url`
- `docs/assets/inter-subset.woff2.base64`
- `docs/assets/inter-subset.woff2.url`
- `docs/assets/menu_1.png.base64`
- `docs/assets/menu_1.png.url`

## Notes

Removed files remain recoverable via git history if any historical context is needed.
