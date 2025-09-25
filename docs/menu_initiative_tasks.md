# Menu Initiative Implementation Plan

This document breaks the six priority initiatives into actionable tasks. Each initiative includes a summary, key outcomes, and an ordered task list covering discovery, design, implementation, and rollout activities.

## 1. Unify "Opportunities" Experience (Movers + Trading)
- **Goal:** Deliver a single Opportunities surface that merges Movers analytics with Trading signals and seamless research drill-downs.
- **Success Metrics:** Increased signal engagement, reduced bounce between Movers/Trading, faster drill-down to Instrument Research.
- **Tasks:**
  1. Audit current Movers and Trading usage, data feeds, and technical dependencies.
  2. Define combined data contract (filters, signals, pagination) and document API requirements.
  3. Align UX with product/design on unified list + detail flow; capture wireframes and interaction notes.
  4. Update backend services to expose merged endpoints and shared filtering logic.
  5. Refactor frontend components to consume merged data and consolidate filters/signal overlays.
  6. Implement cross-navigation from Opportunities entries to Instrument Research and Watchlists.
  7. Update regression and performance test suites to cover new endpoints and virtual scrolling.
  8. Coordinate UAT with advisors; capture feedback and iterate on usability issues.
  9. Publish release notes and training snippets for advisors/sales.

## 2. Consolidate Personal Settings & Alerts
- **Goal:** Provide a unified personalisation hub by folding Alert Settings into User Settings and simplifying Support overlaps.
- **Success Metrics:** Single entry point for notification preferences, decreased support tickets for alert configuration, parity between UI and backend records.
- **Tasks:**
  1. Inventory existing settings surfaces (User, Alert Settings, Support) and map ownership of each control.
  2. Design target IA/wireframes for consolidated Settings tabs with profile, alerts, notifications, approvals.
  3. Update backend schema/endpoints to persist alert thresholds and notification channels within the user settings service.
  4. Refactor frontend settings modules to new layout; remove redundant routes and shared components.
  5. Migrate existing user preferences and backfill data to the new unified structure.
  6. Update Support tooling to rely on the unified settings APIs and remove duplicated UI.
  7. Validate end-to-end persistence with automated and manual tests across web/mobile clients.
  8. Communicate changes via in-app banners and support documentation updates.

## 3. Productise Rebalance Workflow
- **Goal:** Make Rebalance a production-ready workflow connected to live portfolios with actionable suggestions.
- **Success Metrics:** Advisors complete live rebalances without exports, improved compliance hand-off, higher adoption.
- **Tasks:**
  1. Connect Rebalance view to live portfolio and holdings data sources with proper access controls.
  2. Define and implement suggested-trade algorithm factoring targets, drift, and compliance constraints.
  3. Build UI for recommended trades with inline adjustments, validation, and summary deltas.
  4. Integrate Trade Compliance checks, presenting policy flags and remediation options.
  5. Add error handling for incomplete or stale data, including retry/refresh mechanisms.
  6. Extend automated test coverage for calculations, compliance integration, and UI states.
  7. Run advisor pilot, collect feedback, and refine algorithm parameters.
  8. Document workflow updates in playbooks and release notes.

## 4. Level-up Tax & Pension Tools
- **Goal:** Increase automation and guidance across Tax and Pension planning flows.
- **Success Metrics:** Higher completion rates, reduced manual data entry, better narrative outputs.
- **Tasks:**
  1. Integrate Transactions and Allowances APIs to auto-populate tax and pension inputs.
  2. Add templated scenarios and guided prompts for common planning situations.
  3. Create narrative output components summarising recommendations, risks, and next steps.
  4. Implement export workflows (PDF/CSV) into Reports, including scheduling options.
  5. Validate jurisdiction-specific calculations with regression test data.
  6. Update help articles and in-product guidance modals to reflect new capabilities.

## 5. Assess Trail & Virtual Portfolio Usage
- **Goal:** Make data-driven decision to archive, repurpose, or invest in Trail and Virtual Portfolio tabs.
- **Success Metrics:** Clear recommendation with supporting analytics, actionable next steps.
- **Tasks:**
  1. Instrument detailed usage tracking (events, funnels) for Trail and Virtual Portfolio interactions.
  2. Compile retention/adoption metrics and compare against benchmarks for core features.
  3. Conduct user interviews or surveys with current adopters to assess value.
  4. Draft recommendation memo outlining archive vs. repurpose options.
  5. If archiving, define deprecation timeline, user comms, and data retention plan.
  6. If repurposing, outline future use cases, required features, and resourcing needs.
  7. Update product roadmap and share decision with stakeholders.

## 6. Enhance Core Portfolio Views
- **Goal:** Align Portfolio and Allocation experiences with the storytelling depth of the Performance dashboard.
- **Success Metrics:** Increased engagement with insight cards, higher click-through to scenarios and analytics.
- **Tasks:**
  1. Audit existing Portfolio and Allocation screens, identifying insight gaps vs. Performance.
  2. Ideate and prioritise new insight cards, scenario shortcuts, and visual upgrades with design.
  3. Implement reusable insight modules and updated chart components across both views.
  4. Link relevant insights to deeper analytics pages and scenario launchers.
  5. Ensure accessibility and responsiveness across devices with cross-browser testing.
  6. Update onboarding materials, release notes, and customer training assets.
