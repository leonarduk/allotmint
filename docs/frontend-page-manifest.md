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
