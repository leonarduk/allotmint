# Codebase Review: Proposed GitHub Issues

## Review Scope

This review covered the backend FastAPI service, the React/Vite frontend, test and CI entry points, and the main contributor documentation. The findings below prioritise issues that materially affect correctness, maintainability, operational safety, or delivery speed.

## Suggested Labels

Use the following label dimensions on each issue:

- **area**: `backend`, `frontend`, `pipeline`, `infra`, `docs`, `testing`
- **type**: `bug`, `design`, `performance`, `maintainability`, `devex`
- **priority**: `critical`, `high`, `medium`, `low`
- **milestone bucket**: `v1-blocker` or `post-v1`

---

## V1 Blockers

### 1) Split monolithic portfolio backend into smaller services and route adapters
- **Area:** backend
- **Type:** design, maintainability
- **Priority:** high
- **Milestone bucket:** v1-blocker

**Problem description**

`backend/common/portfolio_utils.py` and `backend/routes/portfolio.py` are both very large, high-responsibility modules. The shared route file mixes HTTP concerns, pricing date resolution, owner/group lookup, portfolio assembly, movers logic, and compatibility shims. The utility module is even larger and appears to carry core domain logic, snapshot handling, and portfolio calculations in one place.

This creates high change risk: small portfolio changes are likely to produce regressions in unrelated endpoints because there is no clear boundary between orchestration, domain calculations, and transport concerns.

**Impact**

- Slows feature delivery on the most business-critical user flows.
- Makes debugging and code review expensive.
- Increases regression risk for owner/group/performance endpoints.
- Prevents more targeted unit testing around pricing, aggregation, and filtering logic.

**Proposed solution**

Refactor the portfolio stack into smaller modules with explicit responsibilities, for example:

- `portfolio_service` for orchestration
- `portfolio_pricing` for pricing-date and quote resolution
- `portfolio_aggregation` for owner/group rollups
- `portfolio_serializers` for API response shaping
- thin route handlers that validate input and delegate to services

Do this incrementally behind existing API contracts.

**Acceptance criteria**

- Portfolio route handlers no longer contain business logic beyond request validation and response translation.
- Core portfolio logic is split into focused modules with clear ownership.
- New unit tests cover the extracted services directly.
- Existing API behaviour remains unchanged or is explicitly versioned.

---

### 2) Consolidate frontend route-mode parsing into a single source of truth
- **Area:** frontend
- **Type:** bug, maintainability
- **Priority:** high
- **Milestone bucket:** v1-blocker

**Problem description**

Route-to-mode resolution is duplicated in multiple places. `frontend/src/main.tsx` contains `deriveModeFromPathname`, while `frontend/src/App.tsx` separately computes `initialMode` using another hard-coded path mapping. There is also a dedicated `useRouteMode` hook elsewhere in the frontend.

This duplication is likely to drift over time. Adding, renaming, or deprecating routes requires updates in several files, and any missed update can produce inconsistent active tabs, route markers, or page bootstrap state.

**Impact**

- Incorrect navigation highlighting or bootstrap markers.
- Hard-to-diagnose bugs that only appear on first load or deep links.
- Increased cost for menu and routing changes.

**Proposed solution**

Create one shared route registry that maps pathname segments to app modes and exports helper functions for:

- initial mode derivation
- active route marker computation
- mode-to-path generation
- unsupported route fallback behaviour

Refactor `main.tsx`, `App.tsx`, and any route hooks to consume the shared helper.

**Acceptance criteria**

- Only one module owns route segment ↔ mode mapping.
- Deep-link bootstrap and in-app navigation use the same route logic.
- Regression tests cover all supported primary routes and fallback paths.
- Adding a new route requires updating one mapping only.

---

### 3) Replace broad exception swallowing with typed failures and structured logging
- **Area:** backend
- **Type:** bug, maintainability
- **Priority:** high
- **Milestone bucket:** v1-blocker

**Problem description**

The backend contains a large number of bare or overly broad `except Exception` handlers across core modules and routes. Many of these fall back silently, return degraded output, or only log minimal context. This pattern appears in portfolio loading, support, alerts, auth, instruments, timeseries, and startup code.

Broad exception swallowing hides real production failures and makes it difficult to distinguish expected fallback paths from genuine defects.

**Impact**

- Silent data corruption or incomplete API responses.
- Slow incident diagnosis because root causes are suppressed.
- Behavioural inconsistency between local runs, tests, and production.
- Increased risk that bad external data is treated as success.

**Proposed solution**

Introduce domain-specific exception types and a stricter failure policy:

- catch only expected exceptions close to the source
- include structured log context such as owner, route, ticker, provider, and file path
- return explicit degraded-state metadata where fallbacks are intentional
- surface unexpected exceptions to central error handling

Start with the highest-traffic routes and data-loading paths.

**Acceptance criteria**

- High-traffic modules no longer use generic `except Exception` for normal control flow.
- Intentional fallbacks emit structured logs with enough diagnostic context.
- Unexpected failures return consistent error responses.
- Tests cover both expected fallback cases and hard-failure cases.

---

### 4) Define a stable configuration schema and remove config-shape drift
- **Area:** backend
- **Type:** design, maintainability
- **Priority:** high
- **Milestone bucket:** v1-blocker

**Problem description**

Configuration handling is spread across dataclasses, env parsing, YAML flattening, config serialisation, and API-side shape normalisation. The implementation already shows signs of drift, including repeated imports and multiple transformation layers between persisted config, runtime config, and `/config` route payloads.

This makes config changes risky and increases the chance of inconsistent behaviour between local, tests, and deployed environments.

**Impact**

- Easy to introduce config regressions when adding new settings.
- Difficult to reason about precedence between YAML and environment variables.
- Harder to validate config updates from the frontend.

**Proposed solution**

Define one canonical config schema with explicit nested sections and typed validation. Use that schema for:

- file loading
- env overrides
- `/config` serialisation
- `/config` updates
- generated documentation/examples

Add a small matrix of tests for precedence and invalid values.

**Acceptance criteria**

- One canonical config model defines persisted and runtime shape.
- Config route payloads and file structure are documented and validated consistently.
- Tests cover precedence rules, boolean parsing, missing required values, and invalid tabs.
- Incidental cleanup items such as duplicate imports are removed as part of the refactor.

---

### 5) Bring contributor documentation and runnable commands back in sync with the repo
- **Area:** docs
- **Type:** devex, maintainability
- **Priority:** high
- **Milestone bucket:** v1-blocker

**Problem description**

The documentation and automation entry points are inconsistent. For example, `docs/README.md` still references `uvicorn app:app`, root-level `requirements.txt`, and standalone `black`/`ruff` usage, while the repository actually uses `backend.app:create_app`, `backend/requirements.txt`, and a backend-only `Makefile` lint target. Repo guidance also expects frontend linting, but `make lint` does not include it.

New contributors can easily follow outdated commands and conclude the project is broken.

**Impact**

- Slower onboarding and more avoidable setup failures.
- Confusion about the canonical local development workflow.
- Higher support burden for routine environment setup.

**Proposed solution**

Create a single contributor workflow document and align all docs/scripts with it. At minimum, update:

- backend startup command
- dependency installation commands
- formatting/lint/test commands
- frontend lint/test expectations
- smoke test prerequisites

Prefer documenting the repo-supported commands rather than individual tool invocations.

**Acceptance criteria**

- README/docs commands are runnable from a clean checkout.
- Backend and frontend workflows are both documented in one coherent path.
- `make lint` and documented quality gates match reviewer expectations.
- A new contributor can complete setup without discovering hidden command variants.

---

## Post-v1 Improvements

### 6) Break up the main frontend shell to reduce state coupling and rerender risk
- **Area:** frontend
- **Type:** design, maintainability
- **Priority:** medium
- **Milestone bucket:** post-v1

**Problem description**

`frontend/src/App.tsx` acts as a large shell responsible for route bootstrapping, owner/group selection, page composition, and significant cross-page state. The file is large enough that unrelated changes are likely to collide, and the component is difficult to reason about as a pure view.

**Impact**

- Harder to add features without side effects.
- Unclear ownership of selection state versus route state.
- Greater rerender risk when high-level state changes.

**Proposed solution**

Split the shell into:

- route/bootstrap container
- app layout container
- page-specific loaders/controllers
- shared context for owner/group selection only where justified

**Acceptance criteria**

- `App.tsx` becomes a thin composition root.
- Route handling, selection state, and feature rendering live in separate modules.
- Key page flows have focused tests at the container level.

---

### 7) Add contract tests for backend ↔ frontend API payload compatibility
- **Area:** testing
- **Type:** bug, maintainability
- **Priority:** medium
- **Milestone bucket:** post-v1

**Problem description**

The frontend consumes a large number of API shapes, but there is no obvious contract-test layer that validates backend payloads against frontend expectations. Given the amount of handwritten transformation code and optional fields, the system is vulnerable to shape drift.

**Impact**

- Backend changes can break the frontend without failing backend tests.
- Frontend defensive code accumulates around inconsistent payloads.
- Regressions are discovered late in smoke tests or manual QA.

**Proposed solution**

Introduce schema-backed contract fixtures for core endpoints such as:

- owners/groups
- portfolio
- movers/opportunities
- config
- transactions
- reports metadata

Validate both backend responses and frontend parsing against the same fixtures/schemas.

**Acceptance criteria**

- Shared fixtures or generated schemas exist for high-value endpoints.
- Contract tests fail when required fields, enums, or route semantics drift.
- Frontend parsing logic is exercised against realistic backend payloads.

---

### 8) Add observability for degraded data paths and external-provider failures
- **Area:** pipeline
- **Type:** maintainability, performance
- **Priority:** medium
- **Milestone bucket:** post-v1

**Problem description**

The application relies on multiple external data sources and fallbacks, but there is limited evidence of a consistent degraded-state reporting strategy. Silent retries and suppressed exceptions make it difficult to know when the app is serving stale or partial data.

**Impact**

- Operators may not notice stale prices, missing news, or partial enrichments.
- Troubleshooting third-party outages becomes manual and slow.
- Users receive inconsistent results without clear explanation.

**Proposed solution**

Add explicit health/degradation metrics and operator-facing diagnostics for:

- snapshot warm success/failure
- provider-specific fetch failures
- stale cache age
- fallback provider usage rate
- partial-response markers on affected endpoints

**Acceptance criteria**

- Key provider paths emit observable success/failure signals.
- Support/admin surfaces can show stale or degraded data conditions.
- Alert thresholds are defined for repeated provider failures.

---

### 9) Rationalise overlapping admin/support/settings surfaces before they diverge further
- **Area:** frontend
- **Type:** design, maintainability
- **Priority:** medium
- **Milestone bucket:** post-v1

**Problem description**

The product includes multiple adjacent operational/configuration surfaces such as support, data admin, instrument admin, alert settings, and user settings. The navigation backlog already suggests merging or reshaping some of these areas, which indicates current ownership boundaries are weak.

**Impact**

- Duplicated UI patterns and repeated fetch logic.
- Confusing navigation for operators and advanced users.
- Harder to evolve permissions and page-level responsibilities cleanly.

**Proposed solution**

Create a navigation and responsibility map for operator/admin/configuration pages, then consolidate shared patterns and retire overlapping routes where appropriate.

**Acceptance criteria**

- Each operational/settings page has a documented responsibility.
- Overlapping routes are merged, redirected, or formally separated.
- Shared admin UI patterns are extracted into reusable components.

---

### 10) Introduce performance budgets for the heaviest frontend views
- **Area:** frontend
- **Type:** performance
- **Priority:** medium
- **Milestone bucket:** post-v1

**Problem description**

Large table- and dashboard-oriented pages such as instrument research, group portfolio, transactions, and scenario views are among the biggest files in the frontend and likely to render significant datasets. There is no visible performance budget or profiling harness attached to these pages.

**Impact**

- Gradual UX degradation as more columns, charts, and filters are added.
- Hard to detect when a refactor meaningfully worsens render time.
- Mobile and lower-powered devices are most at risk.

**Proposed solution**

Set measurable budgets for initial render, interaction latency, and row-count handling on the heaviest pages. Add lightweight profiling or benchmark checks for list-heavy components.

**Acceptance criteria**

- A shortlist of high-risk views has agreed performance budgets.
- Virtualisation/lazy-loading strategy is documented per heavy page.
- Regressions are detectable in automated checks or repeatable profiling scripts.

---

### 11) Create a formal deprecation path for legacy/experimental routes and tabs
- **Area:** frontend
- **Type:** design, devex
- **Priority:** low
- **Milestone bucket:** post-v1

**Problem description**

The route and tab surface area is broad, with several features that appear transitional or earmarked for merging/retirement. Without a deprecation policy, route sprawl will keep increasing and stale code paths will remain indefinitely.

**Impact**

- Higher maintenance burden for low-value features.
- More route-specific conditionals across the app shell and menu.
- Reduced confidence when renaming or removing tabs.

**Proposed solution**

Adopt a lightweight deprecation process covering feature flags, redirects, removal windows, and test cleanup.

**Acceptance criteria**

- Deprecated routes/tabs are tracked explicitly.
- Redirect and removal timelines are documented.
- Tests and menu configuration no longer keep obsolete routes alive indefinitely.

---

### 12) Add repository-level task runners that enforce both backend and frontend quality gates
- **Area:** infra
- **Type:** devex, maintainability
- **Priority:** low
- **Milestone bucket:** post-v1

**Problem description**

The repository has split quality commands: backend checks are centralised in `make lint`, while frontend linting/testing live elsewhere. CI covers both, but the local developer entry point does not. This increases the gap between “it passes locally” and “it passes in CI”.

**Impact**

- More avoidable CI failures.
- Inconsistent reviewer expectations about what was run locally.
- Harder to teach a single happy path for contributors.

**Proposed solution**

Add repo-level targets such as:

- `make lint` → backend + frontend lint checks
- `make test` → backend + frontend tests
- `make smoke` → optional integrated smoke path

Keep backend-specific targets as subcommands if needed.

**Acceptance criteria**

- One documented command runs the expected local quality gate.
- Repo-level commands mirror CI stages closely.
- Contributor docs and PR templates reference the same commands.

---

## Recommended Sequencing

1. Issue 5 — fix docs and contributor workflow drift.
2. Issue 2 — centralise routing logic before more tabs/routes are added.
3. Issue 3 — remove exception swallowing from high-traffic paths.
4. Issue 4 — stabilise config shape and precedence.
5. Issue 1 — extract portfolio services incrementally.
6. Issues 6–12 — continue modularisation, contract coverage, and observability.
