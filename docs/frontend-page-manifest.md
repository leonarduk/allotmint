# Frontend page manifest

The frontend route/menu registry now lives in `frontend/src/pageManifest.tsx`.

## What belongs in the manifest

Each page entry defines the ownership boundary for:

- the route segment used to derive the active mode,
- the canonical path builder used by navigation and redirects,
- the menu section/category used by the dropdown menu,
- the display order used when rendering menu items.

## Adding a page feature

1. Add the new mode to `frontend/src/modes.ts`.
2. Add a manifest entry in `frontend/src/pageManifest.tsx` with:
   - `mode`,
   - `routeSegment` if the page is not the group root route,
   - `path`,
   - `order`,
   - `menu` metadata if it should appear in the menu.
3. Render the page in the appropriate router/component (`frontend/src/main.tsx` for top-level routes or `frontend/src/App.tsx` for in-app modes).
4. Update or add tests, especially `frontend/tests/unit/pageManifest.test.tsx`, if the page changes routing or menu behavior.

## Retiring a page feature

1. Remove or disable its render path.
2. Remove the manifest entry.
3. Remove the mode from `frontend/src/modes.ts` if the mode is no longer used.
4. Update tests that depend on the route or menu item.

## Validation

Run the smallest relevant frontend checks after changing the manifest:

- `npm --prefix frontend run test -- --run frontend/tests/unit/pageManifest.test.tsx`
- `npm --prefix frontend run test -- --run frontend/tests/unit/components/Menu.test.tsx`
- `npm --prefix frontend run test -- --run frontend/tests/unit/hooks/useRouteMode.test.tsx`
The frontend now keeps page registration metadata in `frontend/src/pageManifest.ts`.
That manifest is the source of truth for:

- route segment to mode derivation,
- menu category placement,
- default navigation paths for each mode, and
- standalone lazy-loaded routes registered in `frontend/src/main.tsx`.

## Add a page

1. Add the new mode to `frontend/src/modes.ts` if the feature introduces a new route mode.
2. Add a `pageManifest` entry in `frontend/src/pageManifest.ts` with:
   - `mode`,
   - `routeSegment`,
   - `section`,
   - `menuCategory` when it should appear in the dropdown menu,
   - `priority` when it participates in ordered tab navigation,
   - `defaultPath`, and
   - `routePath` plus `lazyComponent` when the page is mounted directly from `main.tsx`.
3. If the page renders inside `App.tsx`, wire the mode's view there.
4. If the page has user-visible labels, ensure `app.modes.<mode>` and any related copy exist in translations.
5. Run `npm --prefix frontend run test -- --run`.

## Retire a page

1. Remove or disable its rendering logic.
2. Remove the matching manifest entry from `frontend/src/pageManifest.ts`.
3. Remove the mode from `frontend/src/modes.ts` and any stale translation keys.
4. Update or delete tests that covered the removed page.
5. Run `npm --prefix frontend run test -- --run` to confirm navigation metadata still matches the remaining pages.

## Guardrails

`frontend/tests/unit/pageManifest.test.ts` verifies that:

- every mode has exactly one manifest entry,
- route segments stay unique,
- menu metadata points at valid categories, and
- standalone lazy routes remain registered through the manifest.

## Build-time plugin pages

Pages can also come from build-time frontend plugins (#6836, see
[the ADR](decisions/6836-pro-frontend-plugin-packaging.md)). The public build
has none, so the manifest above is the whole app.

- `frontend/vite/allotmintPlugins.ts` resolves `virtual:allotmint-plugins`.
  With `ALLOTMINT_PLUGIN_ENTRIES` unset or empty it is
  `export const plugins = [];`. Otherwise it imports each listed entry file
  (separated by `:` on POSIX, `;` on Windows; relative paths resolve against
  the directory Vite runs in). A missing entry, or an entry declaring a
  `hostApiVersion` other than the host's, fails the build.
- Each entry's default export is an `AllotmintFrontendPlugin`
  (`frontend/src/plugin-host/contract.ts`), or an array of them. Plugins import
  host code only from `@allotmint/host` (`frontend/src/plugin-host/api.ts`).
  Bare imports such as `react` resolve against the host's `node_modules`.
- `frontend/src/plugin-host/registry.ts` is the only module allowed to import
  the virtual module (ESLint enforces this). It appends plugin `pages` to the
  manifest after the free entries and merges plugin `configDefaults.tabs`
  into ConfigContext's default tabs. A plugin page whose mode or route segment
  collides with a free one or another plugin's, or a plugin setting a tab
  default for a mode it does not own, throws when the app loads.

To try a plugin locally:

```bash
cd frontend
ALLOTMINT_PLUGIN_ENTRIES=/abs/path/to/plugin/index.ts npm run dev
```

Guardrails: `frontend/tests/unit/plugin-host/freeBuildSnapshot.test.tsx` pins
the free route table, nav order and default tabs;
`frontend/tests/unit/plugin-host/fixturePlugin.test.tsx` covers the
plugin-present path with a fixture; and CI's frontend smoke job runs
`frontend/scripts/verify-plugin-build.mjs`, which builds with the out-of-tree
fixture in `tests/frontend-plugin-fixture/` and checks the public build never
contains it.
