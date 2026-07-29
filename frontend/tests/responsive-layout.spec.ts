import { expect, test, type Locator, type Page } from '@playwright/test';
import { setupCoreMocks } from './support/smokeFixtures';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';
const viewports = [
  { name: 'sm', width: 640 },
  { name: 'md', width: 768 },
  { name: 'lg', width: 1024 },
  { name: 'xl', width: 1280 },
] as const;

const portfolio = {
  owner: 'demo-owner',
  as_of: '2026-07-29',
  trades_this_month: 0,
  trades_remaining: 10,
  total_value_estimate_gbp: 1000,
  accounts: [
    {
      account_type: 'ISA',
      currency: 'GBP',
      value_estimate_gbp: 1000,
      holdings: [],
    },
  ],
};

const openPage = async (page: Page, path: string) => {
  await setupCoreMocks(page);
  await page.route('**/portfolio/demo-owner*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(portfolio),
    });
  });
  await page.route('**/timeseries*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          ticker: 'RESPONSIVE-LAYOUT-LONG-TICKER',
          exchange: 'LONDON',
          name: 'Responsive layout regression fixture',
          earliest: '2025-01-01',
          latest: '2026-07-29',
          completeness: 100,
          latest_source: 'Deterministic fixture',
          main_source: 'Deterministic fixture',
        },
      ]),
    });
  });
  await page.route('**/instrument/admin', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          ticker: 'RESPONSIVE-LAYOUT-LONG-TICKER',
          exchange: 'LONDON',
          name: 'Responsive layout regression fixture',
          region: 'United Kingdom',
          sector: 'Technology',
          grouping: 'Equity',
        },
      ]),
    });
  });
  await page.route('**/quotes*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    });
  });

  await page.goto(new URL(path, baseUrl).toString());
};

const expectNoPageOverflow = async (page: Page) => {
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth
      )
    )
    .toBe(true);
};

const expectWrappingRow = async (row: Locator) => {
  await expect(row).toBeVisible();
  await expect(row).toHaveCSS('flex-wrap', 'wrap');
  await expect(row).toHaveClass(/\bgap-2\b/);
};

for (const viewport of viewports) {
  test.describe(`${viewport.name} (${viewport.width}px)`, () => {
    test.use({ viewport: { width: viewport.width, height: 900 } });

    test('keeps the portfolio grid responsive without page overflow', async ({
      page,
    }) => {
      await openPage(page, '/portfolio/demo-owner');

      const grid = page
        .getByText('Approx Total:', { exact: false })
        .locator('xpath=../..');
      await expect(grid).toBeVisible();
      await expect(grid).toHaveCSS(
        'grid-template-columns',
        viewport.width < 1280
          ? /^\d+(?:\.\d+)?px$/
          : /^\d+(?:\.\d+)?px \d+(?:\.\d+)?px$/
      );
      await expectNoPageOverflow(page);
    });

    test('contains both admin tables in horizontal scroll regions', async ({
      page,
    }) => {
      for (const path of ['/instrumentadmin', '/dataadmin']) {
        await openPage(page, path);

        const table = page.locator('table');
        const wrapper = table.locator('..');
        await expect(table).toBeVisible();
        await expect(wrapper).toHaveClass(/\boverflow-x-auto\b/);
        await expect(wrapper).toHaveCSS('overflow-x', 'auto');
        if (viewport.width <= 768) {
          await expect
            .poll(() =>
              wrapper.evaluate(
                (element) => element.scrollWidth > element.clientWidth
              )
            )
            .toBe(true);
        }
        await expectNoPageOverflow(page);
      }
    });

    test('allows allocation and watchlist control rows to wrap', async ({
      page,
    }) => {
      await openPage(page, '/allocation');
      await expectWrappingRow(
        page.getByRole('button', { name: 'Instrument Types' }).locator('..')
      );
      await expectNoPageOverflow(page);

      await openPage(page, '/watchlist');
      await expectWrappingRow(
        page.getByRole('button', { name: 'Refresh' }).locator('..')
      );
      await expectNoPageOverflow(page);
    });
  });
}
