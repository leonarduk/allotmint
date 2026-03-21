# Frontend page manifest

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
