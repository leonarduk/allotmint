import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
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
