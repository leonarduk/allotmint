import { expect, test, type Locator, type Page } from '@playwright/test';
import { applyAuth, setupCoreMocks } from './support/smokeFixtures';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';
const authToken =
  process.env.SMOKE_AUTH_TOKEN ?? process.env.TEST_ID_TOKEN ?? null;
const BREAKPOINTS = [640, 768, 1024, 1280] as const;
const VIEWPORT_HEIGHT = 900;

const portfolio = {
  owner: 'demo-owner',
  as_of: '2026-01-01',
  trades_this_month: 0,
  trades_remaining: 12,
  total_value_estimate_gbp: 1000,
  accounts: [
    {
      account_type: 'ISA',
      currency: 'GBP',
      value_estimate_gbp: 1000,
      holdings: [
        {
          ticker: 'AAA',
          name: 'Alpha Fund',
          units: 10,
          market_value_gbp: 1000,
          gain_gbp: 50,
          gain_pct: 5,
          instrument_type: 'Fund',
          sector: 'Technology',
          region: 'United Kingdom',
        },
      ],
    },
  ],
};

const mockResponsivePageData = async (page: Page) => {
  await setupCoreMocks(page);
  const jsonRoute = async (pattern: string, body: unknown) => {
    await page.route(pattern, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })
    );
  };

  await jsonRoute('**/portfolio/demo-owner', portfolio);
  await jsonRoute('**/portfolio-group/all', {
    ...portfolio,
    slug: 'all',
    name: 'All portfolios',
    members: ['demo-owner'],
  });
  await jsonRoute('**/instrument/admin', [
    {
      ticker: 'AAA.L',
      exchange: 'L',
      name: 'Alpha Fund With A Deliberately Long Name',
      region: 'United Kingdom',
      sector: 'Technology',
      grouping: 'Long-term investments',
    },
  ]);
  await jsonRoute('**/timeseries/admin', [
    {
      ticker: 'AAA',
      exchange: 'L',
      name: 'Alpha Fund With A Deliberately Long Name',
      earliest: '2024-01-01',
      latest: '2026-01-01',
      completeness: 100,
      latest_source: 'Deterministic test feed',
      main_source: 'Deterministic test feed',
    },
  ]);
  await page.route('**/api/quotes?**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  );
};

const openPage = async (page: Page, path: string) => {
  await page.goto(new URL(path, baseUrl).toString());
  await expect(page.locator('[data-route-marker="active"]')).toBeVisible();
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

const expectWrappingControls = async (controls: Locator) => {
  await expect(controls).toBeVisible();
  await expect(controls).toHaveClass(/\bflex-wrap\b/);
  await expect(controls).toHaveCSS('flex-wrap', 'wrap');
};

test.beforeEach(async ({ page }) => {
  await applyAuth(page, authToken);
  await mockResponsivePageData(page);
});

for (const width of BREAKPOINTS) {
  test(`responsive layouts remain contained at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: VIEWPORT_HEIGHT });

    await openPage(page, '/portfolio/demo-owner');
    const portfolioGrid = page
      .getByText(/Approx Total:/)
      .locator('..')
      .locator('..');
    await expect(portfolioGrid).toBeVisible();
    await expect(portfolioGrid).toHaveClass(
      /\bgrid-cols-1\b.*\bxl:grid-cols-\[minmax\(0,3fr\)_minmax\(0,2fr\)\]/
    );
    const expectedColumns = width < 1280 ? 1 : 2;
    await expect
      .poll(() =>
        portfolioGrid.evaluate(
          (element) =>
            getComputedStyle(element).gridTemplateColumns.split(' ').length
        )
      )
      .toBe(expectedColumns);
    await expectNoPageOverflow(page);

    await openPage(page, '/allocation');
    await expectWrappingControls(
      page.getByRole('button', { name: 'Instrument Types' }).locator('..')
    );
    await expectNoPageOverflow(page);

    await openPage(page, '/watchlist');
    await expectWrappingControls(
      page.getByText('Auto-refresh').locator('..').locator('..')
    );
    await expectNoPageOverflow(page);
  });
}

for (const adminPage of [
  { path: '/instrumentadmin', heading: 'Instrument admin' },
  { path: '/dataadmin', heading: 'Data admin' },
]) {
  test(`${adminPage.path} keeps wide tables in a horizontal scroller`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 640, height: VIEWPORT_HEIGHT });
    await openPage(page, adminPage.path);

    const heading = page.getByRole('heading', { name: adminPage.heading });
    await expect(heading).toBeVisible();
    const scroller = heading.locator('..').locator('.overflow-x-auto');
    await expect(scroller).toHaveCSS('overflow-x', 'auto');
    await expect
      .poll(() =>
        scroller.evaluate(
          (element) => element.scrollWidth > element.clientWidth
        )
      )
      .toBe(true);
    await expectNoPageOverflow(page);
  });
}
