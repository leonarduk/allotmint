/**
 * Shared timeout for Testing Library queries that wait on the app's
 * top-level Menu re-rendering (e.g. a toggle click opening a menu
 * category and exposing its menuitems).
 *
 * Testing Library's default `findBy*`/`waitFor` timeout is 1000ms. Tests
 * that mount the full Root app (AuthProvider + UserProvider + BrowserRouter)
 * around Menu — rather than rendering Menu standalone — do more work per
 * re-render, and under CI load that has been observed to occasionally
 * exceed the default even though the menu genuinely opens (#5734). Use
 * this constant instead of a bare `{ timeout: <number> }` so the value
 * stays consistent and any future retuning only happens in one place.
 */
export const MENU_INTERACTION_TIMEOUT_MS = 3000;
