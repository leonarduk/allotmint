# Menu Codex Task Backlog

This backlog translates the menu audit into concrete Codex-friendly engineering tasks. Items are ordered by strategic priority; each entry includes the recommended disposition and specific implementation steps for Codex to tackle.

## 1. Group — Keep & Invest (Rating: 5)
- [ ] Introduce reusable insight-card components surfaced on the Group dashboard.
- [ ] Extend analytics queries to expose alpha, tracking error, and sector/region deltas through a single API endpoint.
- [ ] Implement lazy loading for charts and movers tables to maintain responsiveness under high data volume.
- [ ] Add regression tests that verify drill-down navigation and chart rendering for large groups.

## 2. Performance — Keep & Invest (Rating: 5)
- [ ] Refine performance API to expose drawdown, volatility, and attribution series required for storytelling widgets.
- [ ] Build interactive comparison mode (benchmark vs. owner) with synchronized tooltips across charts.
- [ ] Add download/export hooks for summary analytics and narrative insights.
- [ ] Harden snapshot caching and write performance regression tests around long-range periods.

## 3. Portfolio (Owner) — Keep & Augment (Rating: 4)
- [ ] Port insight-card components from Performance to Portfolio views.
- [ ] Wire scenario shortcuts that deep-link to stress-testing flows.
- [ ] Introduce holdings-level drift indicators and inline rebalancing prompts.
- [ ] Cover new UI states with integration tests across desktop and mobile breakpoints.

## 4. Market — Keep (Rating: 4)
- [ ] Consolidate indices, sectors, and headlines into a single data fetch with caching headers.
- [ ] Add configurable watch presets for sector and factor views.
- [ ] Instrument telemetry for headline click-through and context card usage.
- [ ] Update smoke tests to ensure feeds degrade gracefully when third-party data is delayed.

## 5. Movers — Merge with Trading (Rating: 4)
- [ ] Build unified "Opportunities" list endpoint combining filters, signals, and pagination.
- [ ] Update frontend list components to support signal overlays, bulk actions, and infinite scroll.
- [ ] Implement detail drawer pattern that links to Instrument Research and trading tickets.
- [ ] Add contract tests for combined filtering logic.

## 6. Screener — Keep & Augment (Rating: 4)
- [ ] Add saved-screen CRUD endpoints and wire to UI state management.
- [ ] Overlay watchlist performance metrics within results grid.
- [ ] Implement shareable screener links with permission checks.
- [ ] Expand unit tests for filter combinations and saved query persistence.

## 7. Watchlist — Keep & Augment (Rating: 4)
- [ ] Integrate market status alerts that reuse consolidated notification services.
- [ ] Provide contextual link-outs to Screener and Research flows.
- [ ] Optimise auto-refresh intervals with websocket fallbacks.
- [ ] Add E2E coverage validating alert creation and cross-navigation.

## 8. Allocation — Keep (Rating: 4)
- [ ] Align chart rendering with insight modules from Group/Performance.
- [ ] Ensure account selectors support multi-account aggregation.
- [ ] Add export to PDF/CSV for allocation breakdowns.
- [ ] Expand regression tests for toggle states (asset, sector, region).

## 9. Scenario — Keep & Augment (Rating: 4)
- [ ] Implement scenario templates seeded from common market events.
- [ ] Provide export pipeline that writes scenario results into the Reports service.
- [ ] Add guided prompts and inline education modals.
- [ ] Validate calculations against historical scenarios via automated tests.

## 10. Reports — Keep & Augment (Rating: 3)
- [ ] Surface preview metrics and thumbnails before download.
- [ ] Add schedule builder allowing recurring PDF/CSV reports.
- [ ] Ensure exports pick up new scenario and tax outputs.
- [ ] Expand smoke tests covering long-running export jobs.

## 11. Transactions — Keep & Augment (Rating: 3)
- [ ] Integrate inline trade drill-down panels with compliance notes.
- [ ] Provide advanced filters (instrument type, status, advisor) backed by indexed queries.
- [ ] Enable CSV export with timezone-safe timestamps.
- [ ] Add tests for pagination, filtering, and export accuracy.

## 12. Trading — Merge into Movers (Rating: 3)
- [ ] Deprecate standalone Trading routes and redirect legacy links to Opportunities.
- [ ] Move signal-generation logic into the shared Opportunities service.
- [ ] Clean up unused UI components and update navigation configuration.
- [ ] Verify migration scripts preserve existing user bookmarks.

## 13. Instrument (Research) — Keep & Augment (Rating: 3)
- [ ] Simplify metadata editing forms with grouped inputs and validation.
- [ ] Surface saved research notes inline with quote data.
- [ ] Add contextual navigation from Opportunities detail drawer.
- [ ] Write regression tests for editing workflows and note persistence.

## 14. Timeseries — Keep & Augment (Rating: 3)
- [ ] Add schema validation before accepting CSV uploads.
- [ ] Implement preview charts that render sample of edited series.
- [ ] Provide diff view for proposed vs. current series before publishing.
- [ ] Add backend tests covering validation failures and preview generation.

## 15. Data Admin — Keep (Rating: 3)
- [ ] Build alert hooks that notify operators about stale feeds without manual polling.
- [ ] Add highlighting and filtering for critical feeds.
- [ ] Integrate with observability dashboards for unified status reporting.
- [ ] Create smoke tests simulating delayed vendor updates.

## 16. Instrument Admin — Keep (Rating: 3)
- [ ] Align filters and list components with Data Admin to avoid duplication.
- [ ] Implement bulk edit workflows for instrument metadata.
- [ ] Ensure audit logs capture admin changes with attribution.
- [ ] Add unit tests for permission boundaries and bulk operations.

## 17. User Settings — Keep & Merge Alerts (Rating: 3)
- [ ] Incorporate alert threshold controls from legacy Alert Settings page.
- [ ] Redesign layout to include profile, notifications, and approvals tabs.
- [ ] Update API contract to store notification preferences centrally.
- [ ] Run integration tests confirming parity between UI and backend records.

## 18. Support — Keep & Streamline (Rating: 3)
- [ ] Remove redundant alert toggles once consolidated in User Settings.
- [ ] Enhance diagnostics panels with automated health checks.
- [ ] Add context-sensitive help linking to updated documentation.
- [ ] Expand operator E2E tests to cover revised workflows.

## 19. Allocation → Rebalance — Augment Heavily (Rating: 2)
- [ ] Connect to live portfolio data with proper entitlements.
- [ ] Implement suggested-trade generation engine with compliance awareness.
- [ ] Add UI for editable trade recommendations and validation errors.
- [ ] Cover workflow with integration tests from allocation selection through compliance hand-off.

## 20. Tax Tools — Augment Heavily (Rating: 2)
- [ ] Auto-populate inputs via Transactions and Allowances APIs.
- [ ] Provide narrative output summarising recommended actions.
- [ ] Enable export to Reports with jurisdiction metadata.
- [ ] Add regression tests for jurisdiction-specific calculations.

## 21. Pension — Augment Heavily (Rating: 2)
- [ ] Integrate data ingestion similar to Tax Tools for contribution history.
- [ ] Enhance scenario storytelling with charts and next-step guidance.
- [ ] Link recommended actions to planning resources.
- [ ] Test pension flows across supported jurisdictions.

## 22. Trail — Consider Archiving (Rating: 2)
- [ ] Instrument detailed usage analytics to confirm low adoption.
- [ ] If sunsetting, implement feature flags and remove navigation entry once metrics confirm.
- [ ] Provide migration messaging and archive historical progress data.
- [ ] Validate that removing Trail does not break onboarding sequences.

## 23. Virtual Portfolio — Consider Pausing (Rating: 2)
- [ ] Capture usage analytics similar to Trail.
- [ ] Evaluate component reuse opportunities (e.g., sandbox trade table) and document findings.
- [ ] If pausing, disable creation flows while preserving read-only access for existing data.
- [ ] Add regression tests ensuring core portfolio views remain unaffected.

## 24. Alert Settings — Merge into User Settings (Rating: 1)
- [ ] Move alert-specific UI components into the consolidated User Settings tabs.
- [ ] Retire redundant routes and update navigation to point to new location.
- [ ] Update API to treat legacy alert preferences as aliases to the unified schema.
- [ ] Add migration tests verifying historical alert configurations are preserved.

## 25. Trade Compliance — Keep & Augment (Rating: 3)
- [ ] Surface policy summaries and outstanding exceptions in a concise overview.
- [ ] Link compliance entries to Transactions and Rebalance workflows for context.
- [ ] Provide export hooks for audit packages.
- [ ] Expand automated tests to cover exception resolution paths.
