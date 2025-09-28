import { expect, test, type Page, type Route } from '@playwright/test';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';
const authToken = process.env.SMOKE_AUTH_TOKEN ?? process.env.TEST_ID_TOKEN ?? null;

const applyAuth = async (page: Page) => {
  if (!authToken) {
    return;
  }

  await page.addInitScript((token: string) => {
    window.localStorage.setItem('authToken', token);
  }, authToken);
};

test.describe('config bootstrap regression', () => {
  test('shows the route marker after retrying config load', async ({ page }) => {
    await applyAuth(page);

    const rootUrl = new URL('/', baseUrl).toString();
    let attempt = 0;

    const handler = async (route: Route) => {
      attempt += 1;
      if (attempt === 1) {
        await route.abort('failed');
        return;
      }

      await page.unroute('**/config', handler);
      await route.continue();
    };

    await page.route('**/config', handler);

    await page.goto(rootUrl);

    await expect.poll(() => attempt).toBeGreaterThan(1);

    const marker = page.getByTestId('active-route-marker');
    await expect(marker).toHaveAttribute('data-mode', 'group');
    await expect(marker).toHaveAttribute('data-pathname', '/');
  });
});
