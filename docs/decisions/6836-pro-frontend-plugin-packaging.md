# Decision: package pro-only frontend features as build-time plugins (#6836)

Status: **Proposed**. This is the ADR spike that
[#6836](https://github.com/leonarduk/allotmint/issues/6836) asks for before any
code ("needs an ADR spike before any code", triage of 2026-08-22). It becomes
**Accepted** once the owner signs off on §4 in the PR that adds it. After that,
the implementation children cite this document by section number instead of
re-deciding anything here, as with
[6365-portfolio-consolidation.md](6365-portfolio-consolidation.md).

Date: 2026-11-02. Verified against `main` at `40bc40243`.

---

## 1. Context: what the code does today

All file and line references below were checked against the commit above. Some
corrections to the issue and its triage are in §1.2. They change which file the
work centres on, but not the problem.

### 1.1 Claims that hold

- **The free repo's config type hard-codes paid feature names.**
  `frontend/src/ConfigContext.tsx` declares `screener` (L31), `taxtools` (L52)
  and `'trade-compliance'` (L53) as named `TabsConfig` keys. Their defaults are
  at L113, L133 and L134. It also contains the Family-MVP rule that turns the
  compliance and tax tabs off unless `enable_compliance_workflows` is set
  (`disableTab("trade-compliance")` / `disableTab("taxtools")`, L216–219).
  Every new paid page today means editing this shared type.
- **Paid UI ships as public source in the public build.** About 2,850 lines:

  | Feature | Files |
  | --- | --- |
  | Compliance | `pages/TradeCompliance.tsx` (99), `pages/ComplianceWarnings.tsx` (104), `components/ComplianceWarnings.tsx` (129) |
  | Screener | `pages/Screener.tsx` (764), `components/ScreenerPage.tsx` (137), `hooks/useScreenerRiskReturn.ts` (84) |
  | Tax / allowances | `pages/TaxTools.tsx` (783), `pages/AllowanceTracker.tsx` (67), `components/AllowanceGuardianCard.tsx` (184) |
  | VaR | `components/ValueAtRisk.tsx` (198), `components/VarBreakdownModal.tsx` (177); `components/RightRail.tsx` (124) calls `getValueAtRisk` |

- **The backend already has the boundary we want to mirror.**
  `backend/common/core_optional.py` provides `missing_package()` and
  `require_core()`. They turn an absent `allotmint_pro` into a clean 402, which
  `frontend/src/api.ts` (~L1582–1635) and `hooks/useScreenerRiskReturn.ts`
  (L27–29) already read as "unavailable".

### 1.2 Corrections to the issue and triage

1. **`frontend/src/pluginRegistry.ts` is dead code.** Nothing in `src/` or any
   test imports it. Its static `registerTabPlugin()` calls for `compliance` and
   `trade-compliance` therefore never run, and it is not the mechanism to
   convert. Most of `frontend/src/plugins/*` is dead too: `plugins/index.ts`
   exports an empty array, and only `plugins/movers.ts` has an importer
   (`components/TopMoversSummary.tsx:8`). `pages/AllowanceTracker.tsx` is
   imported only by its own unit test, not by any route.
2. **The live extension point is `frontend/src/routes/registry.ts`.** This is
   the page manifest that `pageManifest.ts` / `tabPlugins.ts` re-export. Each
   entry carries `mode`, `routeSegment`, `section`, `menuCategory`, `priority`,
   `defaultPath`, and optionally `routePath` + `lazyComponent`. The paid entries
   are `screener` (L213–220), `taxtools` (L373–379) and `trade-compliance`
   (L381–389).
3. **"The paid code is always downloaded" is only partly true.** Two cases:
   - **Code-split, fetched only on navigation:**
     - `pages/TradeCompliance` (`registry.ts:388`)
     - `pages/ComplianceWarnings` (`main.tsx:102`)
   - **Statically imported by eagerly loaded modules, so in the `App` chunk
     every user downloads:**
     - `components/ComplianceWarnings` (`App.tsx:30`, rendered at L677)
     - `pages/TaxTools` (`App.tsx:53`, rendered at L784)
     - `ValueAtRisk` / `VarBreakdownModal` (`OwnerPortfolioActions.tsx:12`, rendered at L75)
     - `Screener` (`pages/Ideas.tsx:8`, used at L25)

   Either way, all of it is public source and present in every `dist/`.
   Lazy-loading alone would not meet the issue's Success criteria.
4. **Pro UI attaches in two ways, not one.** Some features are whole routes
   (trade-compliance, tax tools). Others are fragments inside free pages:
   - the compliance banner on the dashboard
   - the Screen tab inside Ideas
   - the VaR card in owner actions
   - VaR in the right rail

   So the plugin contract needs **named slots** as well as pages. The issue's
   `{ id, Component, configDefaults }` sketch covers only pages.

### 1.3 Who builds each artefact today (triage decision 2)

The key fact for this decision: **every artefact that contains `allotmint-pro`
is already built by a pipeline that has the pro source checked out.**

| Artefact | Built by | Has pro source? |
| --- | --- | --- |
| Lambda image (backend) | `deploy-lambda.yml`. It builds the pro wheel from the tag pinned in the `pro` extra (`scripts/pro_pin.py`, #11004) and checks out allotmint-pro into `.pro-src`. | Yes |
| Production static site (`frontend/dist` → `StaticSiteStack`) | The same workflow. It moves to `allotmint-pro`'s own `deploy-lambda.yml` under #6796 (#6806 / #6807), which checks out allotmint alongside. | Yes |
| Desktop installer | `allotmint-pro/electron/build.mjs`. It runs `vite build` on a `frontend/` junctioned from the sibling allotmint checkout. | Yes |
| Public build (allotmint CI, `docker-compose*.yml` self-hosting, contributors' `npm run dev`) | allotmint alone | No, and must not need it |

So no single static bundle has to serve both free and paid users. Each
pro-including deployment can build its own bundle. That is what collapses most
of the option space in §3.

## 2. Decision drivers

These come from #6836's Constraints and Success / Failure sections:

- **D1 — No paid source in the public build.** The free `dist/` contains no paid
  source, and no import path from free code (static or dynamic) reaches paid
  source unless the pro package is present.
- **D2 — Free behaviour unchanged.** The free tier builds and behaves exactly as
  it does today when the pro package is absent.
- **D3 — No paid names in free config.** New paid features need no edit to free
  config types or enums.
- **D4 — No mid-implementation design decisions.** Everything is decided here.
- **D5 — Absent-plugin path tested in OSS CI.** The "plugin absent" path is
  tested in OSS CI, and the "plugin present" path is tested somewhere that runs.
  This avoids the `pytest.importorskip('allotmint_pro')` trap noted on #6836 /
  #6857.
- **D6 — Small operational surface.** One person maintains both repos, so no new
  hosting, registry or auth path unless it is unavoidable.

## 3. Options considered

| | Mechanism | Free build has no paid code (D1) | Free behaviour unchanged (D2) | New infra (D6) | Version-skew risk | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| **A** | Module Federation (`@module-federation/vite`): a remote pro bundle loaded at runtime | Yes | Yes | A second build, hosting the remote, a shared-singleton config for React / react-router / i18next | **High**: host and remote built separately and bound at runtime | Rejected |
| **B** | Runtime `import()` of a pro ES module from a URL the deployment serves | Yes | Yes | Same as A without the federation runtime. Shared deps need import maps or globals; CSP needs extending. | **High**: same as A, with less tooling to catch it | Rejected |
| **C** | Pro frontend published to a private npm registry (GitHub Packages) as an `optionalDependency` of `frontend/package.json` | Only if the install fails cleanly for free users. `npm ci` with a lockfile entry for a package that can't be fetched is fragile, and the package name leaks into the public lockfile. | At risk | Registry, a publish workflow, an auth token in every pro build | Medium | Rejected |
| **D** | npm workspace link (`workspaces: ["frontend", "../allotmint-pro/frontend-plugins"]`) | No. A workspace is part of the root install, so the public repo would reference a private path. | At risk | No | Low | Rejected |
| **E** | **Build-time flavour.** A virtual module `virtual:allotmint-plugins` that a small Vite plugin resolves to the plugin entry points listed in an explicit env var, or to an empty list when unset. | **Yes, by construction**: with the var unset there is nothing to import. | **Yes**: the default resolution is a constant empty array, so the free bundle is identical. | None. It reuses the pro checkouts the three pipelines in §1.3 already do. | **Low**: host and plugin compile in one `vite build` / `tsc` pass, and mismatches fail the build | **Chosen** |

Why the triage's claim doesn't apply: the 2026-08-22 triage said runtime
dynamic import is "the only option that satisfies 'paid code is never downloaded
by free users' for a *public static* frontend build". That holds only if one
bundle serves both tiers. §1.3 shows none does. Once pro deployments build their
own bundle (decision 2 below), build-time composition meets D1 without A's or
B's runtime binding problems.

## 4. Decision

### 4.1 Who builds the deployed bundle (triage decision 2)

- **Pro deployments build their own frontend.** This covers the AWS deploy, the
  desktop installer, and any future pro-hosted environment. Each one builds
  allotmint's `frontend/` with the pro plugin entry on the plugin path.
- **The public build stays the default.** It is what allotmint CI,
  docker-compose self-hosting and `npm run dev` produce, and it has no plugins.

### 4.2 Delivery mechanism (triage decision 1): option E

1. **One Vite plugin, `frontend/vite/allotmintPlugins.ts`, in allotmint.**
   - It resolves the virtual id `virtual:allotmint-plugins` to a generated
     module.
   - The generated module imports each path listed in `ALLOTMINT_PLUGIN_ENTRIES`
     (a `path.delimiter`-separated list of absolute entry files) and exports
     them as `plugins: AllotmintFrontendPlugin[]`.
   - With the variable unset or empty, it emits
     `export const plugins = [];`. No auto-detection of a sibling
     `../allotmint-pro` checkout is allowed: what goes into a build must never
     depend on disk layout (D2).
   - A listed entry that doesn't exist is a **build error**, never a silent
     fallback. This mirrors the `ALLOTMINT_APP_ROOT` rule in #6801.
   - The plugin adds each entry's directory to `server.fs.allow`. It also
     resolves bare imports from those files against the host's `node_modules`,
     with `resolve.dedupe` for `react`, `react-dom`, `react-router-dom`,
     `i18next` and `react-i18next`. The pro package therefore has **no
     `node_modules` of its own and no runtime dependencies**: one React, one
     router, one i18n instance.
2. **The pro side is a directory, not a published package.** It lives at
   `allotmint-pro/frontend-plugins/`, with one entry file per plugin or a single
   `index.ts`. It is consumed only as source by pipelines that already check
   pro out. Nothing is published, so there is no registry and no token.
3. **The host imports `virtual:allotmint-plugins` in exactly one module,
   `frontend/src/plugin-host/registry.ts`.** No other file may import it, and
   an ESLint `no-restricted-imports` rule enforces this.

### 4.3 Plugin contract (triage decision 3)

The host owns the contract in `frontend/src/plugin-host/`. Plugins import host
code only through the `@allotmint/host` alias, which points at
`frontend/src/plugin-host/api.ts`. A lint rule in pro forbids deep imports into
`frontend/src/**`, so the public surface stays explicit and reviewable.

```ts
// frontend/src/plugin-host/contract.ts (allotmint)
export const HOST_API_VERSION = 1;

export interface AllotmintFrontendPlugin {
  /** Namespace for config, i18n keys and slot keys, e.g. "compliance". */
  id: string;
  /** Must equal HOST_API_VERSION; checked at build time (§4.4). */
  hostApiVersion: typeof HOST_API_VERSION;
  /** Whole pages: same shape as a routes/registry.ts entry, minus nothing. */
  pages?: PageManifestEntry[];
  /** Fragments mounted into named slots that free pages expose. */
  slots?: Partial<{ [S in SlotName]: ComponentType<SlotProps[S]> }>;
  /** Defaults merged into runtime config (§4.3.1). */
  configDefaults?: { tabs?: Record<string, boolean> };
  /**
   * Under Family MVP, the /config boolean that must be true for this plugin's
   * pages to stay enabled. This replaces the hard-coded disableTab() calls
   * in ConfigContext.tsx L216-219.
   */
  familyMvpFlag?: string;
  /** Per-language translation bundles, added under the `plugin.<id>.` key prefix. */
  locales?: Partial<Record<'en' | 'fr' | 'de' | 'es' | 'pt' | 'it', Record<string, unknown>>>;
}
```

The initial `SlotName`s are exactly the four sites from §1.2 item 4. More are
added only when a feature needs one.

| Slot | Mounted at | First user |
| --- | --- | --- |
| `dashboard.banner` | `App.tsx` ~L677 | compliance warnings |
| `ideas.tab` | `pages/Ideas.tsx` `TAB_CONTENT` | screener |
| `owner.actions` | `OwnerPortfolioActions.tsx` L75 | VaR card |
| `rightRail.section` | `RightRail.tsx` | VaR summary |

A slot with no contributors renders nothing and fetches nothing. That is the
frontend equivalent of `require_core()`: absence is a no-op, not an error.

#### 4.3.1 Config namespacing

- `TabsConfig` loses its paid literal keys (`screener`, `taxtools`,
  `'trade-compliance'`). It keeps the existing `[key: string]: boolean` index
  signature, which already carries `help` and `bots` (ConfigContext.tsx L143 and L146).
- `defaultTabs` is built by merging the free defaults with each plugin's
  `configDefaults.tabs`. A plugin may only set keys equal to its own pages'
  `mode`s. A collision with a free key or another plugin's key is a **build-time
  error**, raised by `registry.ts` on module load and covered by a unit test.
- The `/config` `tabs` overrides apply on top, exactly as today. Server-side
  config files (e.g. `config.yaml`'s `trade-compliance: false`) keep working
  unchanged, because the keys are the same strings.
- Plugin-specific settings beyond tab toggles go under
  `/config` → `plugins.<id>.*`. That is a later need, and only reserved here.

### 4.4 Version compatibility (triage decision 4)

- **Build-time check.** Host and plugin are type-checked and bundled together,
  so most API breaks are compile errors in pro's build, not runtime surprises.
- **Version constant.** `HOST_API_VERSION` is a plain integer. It is bumped
  whenever `@allotmint/host`'s exports or the contract change incompatibly. The
  Vite plugin imports each entry's `hostApiVersion` at build time and fails the
  build on a mismatch, with a message naming both versions.
- **Pinned allotmint SHA.** Pro already pins allotmint by SHA
  (`ALLOTMINT_PIN_SHA` in `allotmint-pro/.github/workflows/cdk-dry-run.yml`), so
  pro adopts host changes deliberately. A scheduled pro workflow that builds
  against allotmint `main` gives early warning. It also closes the
  `backend/**` / `frontend/**` trigger gap that #6805 recorded.

### 4.5 Test strategy (triage decision 5)

| Where | What | Runs in |
| --- | --- | --- |
| allotmint unit (Vitest) | `registry.ts` with **zero** plugins: the route table, `defaultTabs` and nav order equal today's (snapshot taken before the refactor), and every slot renders null. | OSS CI, always |
| allotmint unit (Vitest) | `registry.ts` with a **fixture plugin** in `frontend/src/plugin-host/__fixtures__/`. Checks page registration, slot mounting, `configDefaults` merge, collision error, `familyMvpFlag` gating and the `hostApiVersion` mismatch error. | OSS CI, always |
| allotmint unit (Vitest) | The Vite plugin's `resolveId` / `load`: unset, empty, a missing path (error), and two entries. | OSS CI, always |
| allotmint build guard | `vite build` with `ALLOTMINT_PLUGIN_ENTRIES` set to a fixture **outside `frontend/`** (e.g. `tests/frontend-plugin-fixture/`). This proves cross-directory resolution and dedupe work. A second, unset build is checked for the absence of the fixture's marker string. | OSS CI, always |
| allotmint Playwright smoke (existing) | No plugin: no request to compliance, screener, VaR or allowances endpoints from the dashboard, Ideas or owner pages. This replaces "hidden by flag" with "not present". | OSS CI, always |
| allotmint-pro CI | Build allotmint's frontend at the pinned SHA with pro's entries, run pro's plugin Vitest suite against `@allotmint/host`, and check that `dist/` contains each plugin's chunk. | Pro CI, on every PR |

Nothing in this table is skipped when pro is absent. The OSS side tests the
contract with a fixture instead of `importorskip`-ing the real thing.

## 5. Consequences

**Positive**

- The public `dist/` contains no paid UI (D1). New paid pages and fragments no
  longer touch free types (D3).
- No new hosting, registry, token or runtime loader (D6). It reuses the pro
  checkouts that the deploy and desktop pipelines already perform.
- One React, router and i18n instance. No runtime version skew between host and
  plugin.
- It mirrors the backend: optional at assembly time, a no-op when absent.

**Negative and accepted**

- **Separate public and pro bundles.** The public and pro bundles differ, so a
  bug report must say which one. `appVersion.ts` should append `+pro` when
  plugins are loaded; this is part of slice 2.
- **A new public API surface.** `@allotmint/host` must be curated. The ESLint
  restriction is what keeps it small.
- **Pro UI needs a pro checkout locally.** Contributors without allotmint-pro
  can't run the pro UI locally, which is the same as the backend today. Pro
  developers set one env var:
  `ALLOTMINT_PLUGIN_ENTRIES=../allotmint-pro/frontend-plugins/index.ts npm run dev`.
- **The production frontend build needs pro source.** That is already true for
  the backend image. Until #6807, allotmint's own `deploy-lambda.yml` passes
  `.pro-src/frontend-plugins/index.ts`, which it already checks out at the
  pinned tag. After #6807, allotmint-pro's `deploy-lambda.yml` does the same.
- **Ordering risk in the migration.** Removing a feature from allotmint before
  the pinned pro tag contains it would drop that UI from production. §6 orders
  the steps to prevent this.

**Not decided here (non-goals)**

- Changing the backend split, or exposing `pro_installed` on `/config`. A
  plugin-present frontend talking to a pro-less backend already degrades via
  402s.
- Removing the dead `pluginRegistry.ts` / `plugins/*` files. That is cleanup
  (slice 0) and independent of the mechanism.

## 6. Migration plan

Each step is one PR. None of them changes production until step 3.

0. **Cleanup (optional, independent).**
   - Delete the dead `frontend/src/pluginRegistry.ts`, the unreferenced
     `frontend/src/plugins/*` (keep `movers.ts` or inline it into
     `TopMoversSummary.tsx`), and the orphaned `pages/AllowanceTracker.tsx` with
     its unit test.
   - No behaviour change.
1. **Host extension point with zero plugins.** This is the first slice in §7.
   - Free behaviour is byte-identical, which the snapshot test proves.
2. **De-literalise config, and add slots.**
   - Move the `screener`, `taxtools` and `'trade-compliance'` defaults and the
     L216–219 MVP rule out of `ConfigContext.tsx`. For now they live in a
     host-internal "built-in" plugin that still lives in allotmint.
   - Add the four slots and route today's components through them.
   - Still no code leaves allotmint, and behaviour is unchanged.
   - This proves the contract against real features before any repo boundary is
     crossed.
3. **Per feature, in order: compliance → VaR → screener → tax tools.** Three
   coordinated PRs each:
   1. **allotmint-pro:** add `frontend-plugins/<feature>/` (moved source,
      rewritten to `@allotmint/host` imports) plus its tests, and cut a pro
      release tag.
   2. **allotmint:** bump the `pro` extra to that tag, set
      `ALLOTMINT_PLUGIN_ENTRIES` in `deploy-lambda.yml`'s frontend build (and in
      allotmint-pro's after #6807), and **only then** delete the feature from
      the built-in plugin and `frontend/src`.
   3. **Desktop:** `electron/build.mjs` in pro sets the same variable. This only
      needs doing once, with the first feature.

   Compliance goes first because it is the smallest (≈330 lines) and uses both a
   page and a slot. Tax tools goes last because it is the largest (783 lines)
   and its allowances UI may share helpers with free pages; extract those into
   `@allotmint/host` first.

   Rollback for each feature: revert the allotmint PR. The built-in copy comes
   back, and the pro plugin, if still configured, collides by `mode`. That
   collision is a build error, so a half-rollback can't ship two copies.
4. **Delete the built-in plugin.** Once it is empty, assert in a test that
   `TabsConfig` has no paid literal keys.

## 7. First slice (step 1), concrete

**Goal:** the mechanism exists and is exercised in OSS CI, with zero plugins
and zero behaviour change.

**Files (allotmint only):**

- **New:**
  - `frontend/vite/allotmintPlugins.ts`: the Vite plugin from §4.2, with its own
    tests.
  - `frontend/src/plugin-host/contract.ts`: `HOST_API_VERSION`,
    `AllotmintFrontendPlugin`, and the `SlotName` union. Only page support at
    first; slots come in step 2.
  - `frontend/src/plugin-host/registry.ts`: imports `virtual:allotmint-plugins`
    and exports `pluginPages`, `pluginTabDefaults` and
    `assertNoCollisions(freeModes)`.
  - `frontend/src/plugin-host/api.ts`: the initially near-empty
    `@allotmint/host` surface.
  - `frontend/src/plugin-host/__fixtures__/examplePlugin.tsx`, and
    `tests/frontend-plugin-fixture/index.tsx` (outside `frontend/`).
  - `frontend/src/virtual-allotmint-plugins.d.ts`: the module declaration.
- **Changed:**
  - `frontend/vite.config.ts`: register the plugin and the `@allotmint/host`
    alias.
  - `frontend/src/routes/registry.ts`: append `pluginPages` to the manifest
    after the free entries, and call `assertNoCollisions`.
  - `frontend/src/ConfigContext.tsx`: merge `pluginTabDefaults` into
    `defaultTabs`. The literal keys stay until step 2.
  - The frontend ESLint config: restrict `virtual:allotmint-plugins` to
    `plugin-host/registry.ts`.
  - `docs/frontend-page-manifest.md`: document the extension point.

**Done when:**

- `npm --prefix frontend run build` with `ALLOTMINT_PLUGIN_ENTRIES` unset emits
  the same route table and `defaultTabs` as before. A Vitest snapshot captured
  in the same PR before the change proves this.
- The fixture build (from outside `frontend/`) adds exactly one route and one
  default tab, and its marker string is absent from the unset build.
- A missing entry path and a `hostApiVersion` mismatch each fail the build with
  a clear message.
- `npm --prefix frontend run lint` and `npm --prefix frontend run test -- --run`
  are green, with zero new warnings.

**Explicitly not in this slice:** moving any paid component, slots, removing
`TabsConfig` keys, any pro-repo change, and any deploy workflow change.

## 8. References

- [#6836](https://github.com/leonarduk/allotmint/issues/6836): the parent
  issue. See its 2026-08-22 triage for the five questions answered in §4.
- [#6837](https://github.com/leonarduk/allotmint/pull/6837): the
  `ComplianceWarnings` flag fix, i.e. the symptom.
- [#6857](https://github.com/leonarduk/allotmint/issues/6857): the
  `importorskip` trap that §4.5 avoids.
- [#6796](https://github.com/leonarduk/allotmint/issues/6796): the deploy
  pipeline moving to allotmint-pro, which supplies the "who builds" answer.
- `backend/common/core_optional.py`: the backend pattern being mirrored.
