import { expect, test, type Locator, type Page } from '@playwright/test';
import { applyAuth, setupCoreMocks } from './support/smokeFixtures';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';
const authToken =
  process.env.SMOKE_AUTH_TOKEN ?? process.env.TEST_ID_TOKEN ?? null;

const VIEWPORTS = [
  { name: 'sm', width: 640 },
  { name: 'md', width: 768 },
  { name: 'lg', width: 1024 },
  { name: 'xl', width: 1280 },
] as const;

const portfolio = {
  owner: 'demo-owner',
  as_of: '2026-01-02',
  trades_this_month: 0,
  trades_remaining: 10,
  total_value_estimate_gbp: 0,
  accounts: [],
};

const groupPortfolio = {
  slug: 'all',
  name: 'All portfolios',
  as_of: '2026-01-02',
  members: ['demo-owner'],
  total_value_estimate_gbp: 100,
  accounts: [
    {
      owner: 'demo-owner',
      account_type: 'ISA',
      currency: 'GBP',
      value_estimate_gbp: 100,
      holdings: [],
    },
  ],
};

const assertNoPageOverflow = async (page: Page) => {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
};

const assertScrollableTable = async (table: Locator) => {
  const wrapper = table.locator('..');
  await expect(wrapper).toHaveClass(/(?:^|\s)overflow-x-auto(?:\s|$)/);
  const dimensions = await wrapper.evaluate((element) => ({
    clientWidth: element.clientWidth,
    overflowX: getComputedStyle(element).overflowX,
    scrollWidth: element.scrollWidth,
  }));
  expect(dimensions.overflowX).toBe('auto');
  expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);
};

const preparePage = async (page: Page) => {
  await applyAuth(page, authToken);
  await setupCoreMocks(page);
  await page.route('**/portfolio/demo-owner*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(portfolio),
    })
  );
  await page.route('**/portfolio/demo-owner/sectors*', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  );
  await page.route('**/portfolio-group/all*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(groupPortfolio),
    })
  );
  await page.route('**/instrument/admin', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          ticker: 'RESP.L',
          exchange: 'L',
          name: 'Responsive Layout Instrument',
          region: 'UK',
          sector: 'Technology',
          grouping: 'ISA',
        },
      ]),
    })
  );
  await page.route('**/timeseries/admin', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          ticker: 'RESP',
          exchange: 'L',
          name: 'Responsive Layout Instrument',
          earliest: '2025-01-01',
          latest: '2026-01-02',
          completeness: 100,
          latest_source: 'Deterministic feed',
          main_source: 'Deterministic feed',
        },
      ]),
    })
  );
  await page.route('**/quotes*', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  );
};

for (const viewport of VIEWPORTS) {
  test.describe(`${viewport.name} (${viewport.width}px)`, () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: 900 });
      await preparePage(page);
    });

    test('portfolio grid uses the responsive column count without page overflow', async ({
      page,
    }) => {
      await page.goto(new URL('/portfolio/demo-owner', baseUrl).toString());
      const grid = page
        .locator('div.grid.grid-cols-1')
        .filter({ has: page.getByText('As of', { exact: true }) });
      await expect(grid).toBeVisible();
      await expect(grid).toHaveClass(
        /xl:grid-cols-\[minmax\(0,3fr\)_minmax\(0,2fr\)\]/
      );
      const columns = await grid.evaluate(
        (element) =>
          getComputedStyle(element).gridTemplateColumns.split(' ').length
      );
      expect(columns).toBe(viewport.width < 1280 ? 1 : 2);
      await assertNoPageOverflow(page);
    });

    test('admin tables keep overflow inside their scroll wrappers', async ({
      page,
    }) => {
      for (const path of ['/instrumentadmin', '/dataadmin']) {
        await page.goto(new URL(path, baseUrl).toString());
        const table = page.locator('table');
        await expect(table).toBeVisible();
        await assertScrollableTable(table);
        await assertNoPageOverflow(page);
      }
    });

    test('allocation and watchlist control rows retain wrapping and gaps', async ({
      page,
    }) => {
      await page.goto(new URL('/allocation', baseUrl).toString());
      const allocationControls = page
        .getByRole('button', { name: 'Instrument Types' })
        .locator('..');
      await expect(allocationControls).toHaveClass(/(?:^|\s)flex-wrap(?:\s|$)/);
      await expect(allocationControls).toHaveCSS('flex-wrap', 'wrap');
      await expect(allocationControls).toHaveCSS('gap', '8px');
      await assertNoPageOverflow(page);

      await page.goto(new URL('/watchlist', baseUrl).toString());
      const watchlistControls = page
        .getByRole('button', { name: 'Refresh' })
        .locator('..');
      await expect(watchlistControls).toHaveClass(/(?:^|\s)flex-wrap(?:\s|$)/);
      await expect(watchlistControls).toHaveCSS('flex-wrap', 'wrap');
      await expect(watchlistControls).toHaveCSS('gap', '8px');
      await assertNoPageOverflow(page);
    });
  });
}
