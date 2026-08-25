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
 *
 * A fixed 3000ms still occasionally proved too tight on contended CI
 * runners even after #5734 (#6126), while the same test file reliably
 * passes locally. Rather than blindly raising the value for every
 * environment, scale it up only under CI (`process.env.CI`, set by GitHub
 * Actions and honored elsewhere in this repo, e.g. `playwright.config.ts`)
 * so local runs stay fast to fail while CI gets the extra headroom it
 * actually needs.
 *
 * INVARIANT: this must stay strictly below vitest's `testTimeout` in
 * `vite.config.ts`. A `waitFor` budget larger than the per-test ceiling is
 * unreachable — vitest aborts the whole test first, and the failure surfaces
 * as a bare "Test timed out in <testTimeout>ms" instead of a Testing Library
 * element-not-found error. That inversion silently defeated #6126 (this
 * constant was raised to 8000ms while `testTimeout` stayed at the 5000ms
 * default); see #6982. Raise `testTimeout` alongside any increase here.
 */
export const MENU_INTERACTION_TIMEOUT_MS = process.env.CI ? 8000 : 3000;
