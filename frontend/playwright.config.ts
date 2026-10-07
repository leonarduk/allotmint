import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  // Only `*.spec.ts` files are Playwright specs. `tests/unit/**/*.test.ts(x)`
  // are Vitest files that Playwright's default testMatch would otherwise pick
  // up and fail to load, breaking a bare `playwright test` run (#7357).
  testMatch: '**/*.spec.ts',
  // Do not set a global `viewport` here: the overflow spec sets its own
  // per-test viewport sizes via `page.setViewportSize`. Setting a project
  // viewport would be overridden anyway, but leaving it unset avoids
  // confusion and keeps the config minimal.
  webServer: {
    command: 'npm run preview -- --host 0.0.0.0 --port 2568',
    url: 'http://localhost:2568',
    timeout: 2 * 60 * 1000,
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
