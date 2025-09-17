import { expect, test } from '@playwright/test';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';
const authToken = process.env.SMOKE_AUTH_TOKEN ?? process.env.TEST_ID_TOKEN ?? null;

const smokePath = new URL('/smoke-test', baseUrl).toString();

test.describe('smoke test page', () => {
  test('reports ok for every backend check', async ({ page }) => {
    if (authToken) {
      await page.addInitScript((token: string) => {
        window.localStorage.setItem('authToken', token);
      }, authToken);
    }

    await page.goto(smokePath);
    await page.waitForSelector('ul li');

    const items = page.getByRole('listitem');
    const count = await items.count();
    expect(count).toBeGreaterThan(0);

    for (let index = 0; index < count; index += 1) {
      await expect(items.nth(index)).toContainText('ok');
    }
  });
});
