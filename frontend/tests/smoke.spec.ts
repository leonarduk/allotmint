import { expect, test, type Page } from '@playwright/test';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';
const authToken = process.env.SMOKE_AUTH_TOKEN ?? process.env.TEST_ID_TOKEN ?? null;

const smokePath = new URL('/smoke-test', baseUrl).toString();
const pensionForecastPath = new URL('/pension/forecast', baseUrl).toString();

const applyAuth = async (page: Page) => {
  if (!authToken) {
    return;
  }

  await page.addInitScript((token: string) => {
    window.localStorage.setItem('authToken', token);
  }, authToken);
};

test.describe('smoke test page', () => {
  test('reports ok for every backend check', async ({ page }) => {
    await applyAuth(page);

    await page.goto(smokePath);

    const list = page.getByRole('list', { name: 'Smoke test results' });
    await expect(list).toBeVisible();

    const items = list.getByRole('listitem');
    await expect(items.first()).toBeVisible();

    const count = await items.count();
    expect(count).toBeGreaterThan(0);

    for (let index = 0; index < count; index += 1) {
      await expect(items.nth(index)).toContainText('ok');
    }
  });
});

test.describe('pension forecast page', () => {
  test('renders the pension forecast heading without errors', async ({ page }) => {
    const pageErrors: Error[] = [];
    page.on('pageerror', (error) => {
      pageErrors.push(error);
    });

    await applyAuth(page);

    await page.goto(pensionForecastPath);

    await expect(page.getByRole('heading', { name: 'Pension Forecast' })).toBeVisible();
    expect(pageErrors).toHaveLength(0);
  });
});
