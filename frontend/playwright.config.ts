import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  webServer: {
    command: 'npm run preview -- --host 0.0.0.0 --port 5173',
    url: 'http://localhost:5173',
    timeout: 2 * 60 * 1000,
    reuseExistingServer: !process.env.CI,
  },
});
