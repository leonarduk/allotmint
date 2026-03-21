# Codebase Review

## Scope and review notes

This review traces the current AllotMint backend, frontend, data-loading, and testing paths with emphasis on correctness risks, maintainability, developer experience, and pre-v1 hardening work.

### Code paths reviewed

- Backend app bootstrap, lifecycle, and route registration in `backend/app.py`.
- Portfolio/data discovery and account loading flows in `backend/common/data_loader.py` and `backend/routes/portfolio.py`.
- Frontend bootstrap and routing state derivation in `frontend/src/main.tsx` and `frontend/src/App.tsx`.
- Representative large UI surfaces and route-driven pages under `frontend/src/components/` and `frontend/src/pages/`.
- Existing automated coverage shape under `tests/` and `frontend/tests/unit/`.

### Observations driving prioritisation

- The backend and frontend both contain several very large, multi-responsibility modules that are now acting as integration hubs rather than narrow features.
- There are multiple places where failures are intentionally swallowed and replaced with defaults, which improves resilience but also hides data-quality and configuration defects.
- Some critical frontend route state is duplicated between entrypoints.
- The project has strong unit-test breadth, but there are still important contract, integration, and failure-mode gaps across bootstrap and data-provider boundaries.

---

## v1 blockers

### 1) Split backend bootstrap into explicit startup services and add lifecycle tests
- **Area:** backend / infra
- **Type:** design / maintainability
- **Priority:** high
- **Stage:** v1 blocker
- **Problem description:** `backend/app.py` owns configuration override preservation, snapshot warming, background task registration, accounts-root isolation for tests, reconciliation side effects, CORS setup, rate limiting, exception handlers, and router registration in one large factory. This increases the chance that unrelated changes break app startup, test setup, or shutdown cleanup.
- **Impact:** Startup regressions are likely to be discovered late because the behavior is coupled together. Failures in one concern can mask another, and onboarding contributors must understand too much global state before changing a single part of app creation.
- **Proposed solution:** Extract bootstrap concerns into small modules/services such as config loading, startup warmers, filesystem/test isolation, middleware registration, and router registration. Introduce an integration test matrix for `create_app()` covering production-like startup, test isolation mode, disabled snapshot warming, and shutdown cleanup.
- **Acceptance criteria:**
  - `backend/app.py` becomes an orchestration layer rather than the implementation home for all startup logic.
  - Bootstrap responsibilities are moved behind named functions or service objects with focused tests.
  - Integration tests assert snapshot warm behavior, background task registration/cancellation, and accounts-root isolation behavior.
  - Failures in warm/reconcile paths are surfaced with structured logging and deterministic assertions.

### 2) Replace silent loader fallbacks with explicit provider boundaries and structured failure reporting
- **Area:** backend / pipeline
- **Type:** bug / maintainability
- **Priority:** high
- **Stage:** v1 blocker
- **Problem description:** `backend/common/data_loader.py` mixes local filesystem discovery, S3 discovery, demo-owner logic, metadata parsing, virtual portfolios, and fallback behavior in a single module. Several provider failures are converted into empty results or local fallbacks without distinguishing transient provider failure from genuine “no data” outcomes.
- **Impact:** Production incidents can present as missing owners/accounts instead of actionable errors. This makes debugging difficult and risks serving incomplete portfolios or metadata without a clear operator signal.
- **Proposed solution:** Introduce explicit data-provider abstractions for local and AWS-backed storage, with typed result objects or domain exceptions for “missing data”, “provider unavailable”, and “invalid payload”. Preserve graceful degradation only where the API contract explicitly allows it, and emit structured metrics/logging for each fallback path.
- **Acceptance criteria:**
  - Local and AWS account discovery/loading are separated into distinct provider modules.
  - Provider methods return typed models or raise well-defined exceptions instead of broad empty fallbacks.
  - API routes can distinguish missing data from provider outages and return different responses/logging.
  - Tests cover S3 error, malformed JSON, empty payload, and fallback-to-local behavior with explicit assertions.

### 3) Introduce typed domain models for owner/account metadata instead of pervasive `dict[str, Any]`
- **Area:** backend
- **Type:** design / maintainability
- **Priority:** high
- **Stage:** v1 blocker
- **Problem description:** Core account and owner flows rely heavily on ad hoc dictionaries through discovery, metadata loading, and route responses. The code repeatedly normalises and conditionally inspects keys like `full_name`, `email`, `viewers`, and account names instead of validating them once at the boundary.
- **Impact:** Schema drift and partial payload bugs are easy to introduce. Small data-shape changes require defensive programming everywhere, increasing complexity and reducing confidence in downstream behavior.
- **Proposed solution:** Define Pydantic models (or equivalent typed structures) for owner summaries, person metadata, account records, and provider response envelopes. Validate external JSON at load time and only pass typed objects through route/business logic.
- **Acceptance criteria:**
  - Shared typed models exist for owner summaries, person metadata, and account documents.
  - JSON loading validates against those models before business logic runs.
  - Route code is simplified to use typed attributes instead of repeated string-key checks.
  - Tests cover invalid/missing fields and verify the emitted API error or fallback behavior.

### 4) Eliminate duplicated frontend route-mode logic and create a single route registry
- **Area:** frontend
- **Type:** bug / design
- **Priority:** high
- **Stage:** v1 blocker
- **Problem description:** Frontend route-to-mode derivation exists in both `frontend/src/App.tsx` and `frontend/src/main.tsx`. The mappings are already not identical, which creates a real risk that bootstrapping state, route markers, menu highlighting, or analytics markers diverge for the same URL.
- **Impact:** Users can see mismatched active states or loading states for some routes, and contributors must update multiple files whenever a route is added or renamed.
- **Proposed solution:** Create a shared route registry that defines path segments, route metadata, mode mapping, and menu/plugin integration in one place. Both bootstrap and runtime components should import the same helper.
- **Acceptance criteria:**
  - One shared route registry or helper is the only source of truth for mode derivation.
  - Existing bootstrap and app-level routing consume the same implementation.
  - Tests cover every known route segment and assert identical output for bootstrap and runtime code paths.
  - Adding a new route requires editing one source file for mode mapping.

### 5) Add contract tests for the highest-value API responses consumed by the SPA
- **Area:** backend / frontend
- **Type:** bug / testing
- **Priority:** high
- **Stage:** v1 blocker
- **Problem description:** The application has broad unit coverage, but there is still limited protection against backend response-shape drift for the endpoints that power owner lists, portfolios, groups, transactions, and configuration bootstrap. The frontend performs substantial runtime normalization, which is often a sign that the contract itself is not tightly pinned down.
- **Impact:** Backend changes can silently break the SPA without a compile-time or CI signal. Regressions are likely to appear only in integrated manual testing.
- **Proposed solution:** Define schema-level API contracts for the core SPA endpoints and validate them in backend integration tests plus frontend mock-contract tests. Prefer snapshot/schema assertions over ad hoc field checks for these endpoints.
- **Acceptance criteria:**
  - Core SPA endpoints have versioned response schemas or central typed contracts.
  - Backend tests validate full response shapes for config, owners, groups, portfolio, and transactions endpoints.
  - Frontend tests consume the same contracts or generated fixtures.
  - CI fails when a contract-breaking field change is introduced without an intentional update.

### 6) Add failure-mode integration coverage for auth/config/bootstrap paths
- **Area:** frontend / backend
- **Type:** testing / maintainability
- **Priority:** high
- **Stage:** v1 blocker
- **Problem description:** The frontend bootstrap path coordinates config fetch, retry scheduling, auth state restoration, route markers, and login behavior, while backend startup controls auth mode, config values, and rate limiting. These cross-cutting flows are more complex than a normal page component but are not yet protected by a focused end-to-end or integration matrix.
- **Impact:** Authentication and first-load regressions can block the entire product even when individual page tests still pass.
- **Proposed solution:** Add integration tests for startup in both auth-enabled and auth-disabled modes, config fetch failure/retry, stale token restoration, and backend config permutations that change frontend behavior.
- **Acceptance criteria:**
  - Automated tests cover first-load behavior for auth-enabled, auth-disabled, and config-failure states.
  - Retry scheduling and cancellation are asserted, not just smoke-rendered.
  - Backend config route behavior is validated against the frontend assumptions it drives.
  - CI includes at least one end-to-end happy path from bootstrap to a portfolio screen.

---

## High-value post-v1 improvements

### 7) Decompose oversized UI shells and tables into feature hooks plus presentational components
- **Area:** frontend
- **Type:** maintainability / design
- **Priority:** medium
- **Stage:** post-v1
- **Problem description:** Several frontend modules are now extremely large (`App.tsx`, `GroupPortfolioView.tsx`, `InstrumentTable.tsx`, `TransactionsPage.tsx`, `InstrumentResearch.tsx`, and others). These files mix data fetching, URL state, formatting, business rules, and rendering in the same component.
- **Impact:** Bug fixes are slower, render regressions are harder to isolate, and tests become more expensive because each component has too many responsibilities.
- **Proposed solution:** Extract domain hooks for data acquisition and state transitions, move table configuration/formatting into dedicated modules, and reduce page components to orchestration + layout.
- **Acceptance criteria:**
  - Largest page/table components are broken into hooks, view models, and presentational sections.
  - New unit tests target extracted hooks and pure formatting helpers.
  - Page-level tests become smaller and less fixture-heavy.
  - File sizes and responsibility count are materially reduced for the targeted components.

### 8) Standardise error taxonomy and observability across routes and background services
- **Area:** backend / infra
- **Type:** maintainability / bug
- **Priority:** medium
- **Stage:** post-v1
- **Problem description:** Broad `except Exception` handlers appear across routes, loaders, alerts, timeseries, and support paths. Some are valid defensive guards, but many flatten distinct failure causes into the same log message or fallback behavior.
- **Impact:** Operators cannot easily distinguish bad input, provider outages, permission problems, malformed data, or internal code defects. This slows incident response and makes alerting noisy or incomplete.
- **Proposed solution:** Define domain-specific exceptions and map them to structured log fields, HTTP errors, and metrics. Reserve broad exception handling for top-level boundaries and always attach enough context for triage.
- **Acceptance criteria:**
  - Shared exception classes and response/logging helpers exist for common failure classes.
  - Core routes and background jobs stop using anonymous broad exception swallowing for business logic.
  - Structured logs or counters exist for provider failure, validation failure, and unexpected internal errors.
  - Tests assert both status code behavior and observability side effects for major failure paths.

### 9) Move expensive synchronous portfolio/data work off hot request paths
- **Area:** backend / performance
- **Type:** performance / design
- **Priority:** medium
- **Stage:** post-v1
- **Problem description:** The codebase still performs meaningful filesystem discovery, JSON loading, metadata lookups, reconciliation, and some provider calls in paths that influence request-time behavior. Even where snapshots exist, hot paths remain coupled to storage and network characteristics.
- **Impact:** Latency becomes more variable as data volume grows, and local vs AWS behavior will drift under load. This also limits horizontal scaling because every instance repeats similar work.
- **Proposed solution:** Identify the most expensive request-time portfolio/data operations, introduce cacheable read models or precomputed indexes, and move heavyweight reconciliation/aggregation to explicit background refresh jobs.
- **Acceptance criteria:**
  - A measured list of top request-time hotspots exists with baseline latency numbers.
  - At least the highest-cost discovery/aggregation path is backed by caching or a precomputed artifact.
  - Cache invalidation and refresh rules are documented and tested.
  - Performance regression checks exist for representative large datasets.

### 10) Tighten project onboarding and contributor workflows around supported run modes
- **Area:** infra / DevEx
- **Type:** maintainability
- **Priority:** medium
- **Stage:** post-v1
- **Problem description:** The repository spans backend, frontend, mobile, AWS/CDK, smoke tests, and multiple runtime modes. The code reflects this flexibility, but the contributor path for “run the app correctly with realistic data and tests” is still more implicit than explicit.
- **Impact:** New contributors will spend unnecessary time discovering required env vars, which test suites are authoritative, and how local, test, and AWS modes differ.
- **Proposed solution:** Publish a single opinionated contributor runbook for the common workflows: local API + frontend, auth-enabled local mode, test mode, smoke mode, and deployment-related checks. Link it from the main docs and keep commands copy/paste ready.
- **Acceptance criteria:**
  - A single contributor/onboarding doc exists and is linked from the primary README/docs index.
  - The doc explains required env vars, data directories, and mode-specific caveats.
  - Validation commands are grouped by common task rather than scattered across multiple docs.
  - A new contributor can complete setup using the documented path without tribal knowledge.

### 11) Add regression tests around data-provider parity between local and AWS modes
- **Area:** backend / testing
- **Type:** bug / testing
- **Priority:** medium
- **Stage:** post-v1
- **Problem description:** The same logical account/owner operations are implemented against both local files and S3-style storage paths. Because the behavior is partially intertwined, parity bugs are likely when one branch evolves faster than the other.
- **Impact:** Local development can appear healthy while AWS-backed deployments behave differently for casing, missing metadata, empty payloads, demo users, or permissions.
- **Proposed solution:** Build a provider-parity test suite that exercises identical fixtures through both local and mocked-AWS providers and compares normalized results.
- **Acceptance criteria:**
  - Shared fixtures exist for local and mocked AWS data-provider scenarios.
  - Listing owners, loading accounts, and loading person metadata produce equivalent normalized outcomes across providers.
  - Known intentional differences are documented explicitly.
  - CI runs parity tests as part of backend validation.

### 12) Define ownership boundaries between plugin navigation, route state, and page registration
- **Area:** frontend
- **Type:** design / maintainability
- **Priority:** low
- **Stage:** post-v1
- **Problem description:** Frontend navigation is spread across direct route checks, plugin ordering, menu behavior, and lazily imported page modules. The current model works, but ownership is diffuse and route additions require touching several conceptual layers.
- **Impact:** Product navigation changes become riskier over time and invite subtle inconsistencies between menu state, mode state, and page availability.
- **Proposed solution:** Formalize a page/plugin manifest that owns route segment, label, permissions, menu placement, and lazy module registration in one place.
- **Acceptance criteria:**
  - Page registration metadata lives in a central manifest.
  - Menu rendering, route mode derivation, and lazy page loading consume that manifest.
  - Tests verify that every registered page has consistent navigation metadata.
  - Documentation explains how to add or retire a page feature.

---

## Recommended execution order

1. Split backend bootstrap and add lifecycle coverage.
2. Refactor data-provider boundaries and typed domain models together.
3. Unify frontend route registry.
4. Add API contract tests and auth/bootstrap integration tests.
5. Tackle large frontend component decomposition.
6. Improve observability and request-path performance.
7. Finish provider-parity and onboarding/documentation work.
