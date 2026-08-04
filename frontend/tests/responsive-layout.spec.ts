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

const assertScrollableTable = async (table: Locator, viewportWidth: number) => {
  const wrapper = table.locator('..');
  await expect(wrapper).toHaveClass(/(?:^|\s)overflow-x-auto(?:\s|$)/);
  const dimensions = await wrapper.evaluate((element) => ({
    clientWidth: element.clientWidth,
    overflowX: getComputedStyle(element).overflowX,
    scrollWidth: element.scrollWidth,
  }));
  expect(dimensions.overflowX).toBe('auto');
  // At narrow viewports (≤768px) the table content is guaranteed to
  // overflow the wrapper — verify the scroll bar is actually needed.
  // At wider viewports the content may fit; still require
  // scrollWidth ≥ clientWidth to catch collapsed-layout regressions.
  if (viewportWidth <= 768) {
    expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);
  } else {
    expect(dimensions.scrollWidth).toBeGreaterThanOrEqual(
      dimensions.clientWidth
    );
  }
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
  // Provide enough rows with wide values that the admin tables are
  // guaranteed to overflow their scroll wrappers at every tested viewport
  // (especially lg and xl, where a single short row would fit without
  // scrolling and cause scrollWidth === clientWidth).
  const instrumentAdminRows = [
    {
      ticker: 'AAAAAAA.L',
      exchange: 'LSE',
      name: 'Very Long Instrument Name Number One Plc',
      region: 'United Kingdom',
      sector: 'Technology Hardware & Equipment',
      grouping: 'ISA',
    },
    {
      ticker: 'BBBBBBB.N',
      exchange: 'NYSE',
      name: 'Another Excessively Long Instrument Name Two Corporation',
      region: 'United States of America',
      sector: 'Financial Services & Insurance',
      grouping: 'GIA',
    },
    {
      ticker: 'CCCCCCC.L',
      exchange: 'LSE',
      name: 'Third Instrument With A Very Very Long Descriptive Name Three Holdings Ltd',
      region: 'European Union',
      sector: 'Healthcare & Biotechnology Research',
      grouping: 'SIPP',
    },
    {
      ticker: 'DDDDDDD.N',
      exchange: 'NASDAQ',
      name: 'Fourth Instrument Name Is Also Quite Extensive Four REIT',
      region: 'Asia Pacific Region',
      sector: 'Real Estate Investment Trust Services',
      grouping: 'ISA',
    },
  ];
  await page.route('**/instrument/admin', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(instrumentAdminRows),
    })
  );
  // These values must be long enough to push the table past its container
  // width at every viewport (especially lg=1024px where the container is
  // ~960px). The Actions column with three buttons also helps, but the
  // primary driver is wide name, source, and exchange string content.
  const timeseriesAdminRows = [
    {
      ticker: 'AAAAAAA',
      exchange: 'LSE',
      name: 'Very Long Instrument Name Number One Plc With Additional Words For Width Testing Purposes',
      earliest: '2025-01-01',
      latest: '2026-01-15',
      completeness: 100,
      latest_source: 'Deterministic feed source alpha channel primary backup mirror',
      main_source: 'Deterministic feed source alpha channel primary backup mirror',
    },
    {
      ticker: 'BBBBBBB',
      exchange: 'NYSE',
      name: 'Another Excessively Long Instrument Name Two Corporation International Holdings Group',
      earliest: '2024-06-01',
      latest: '2026-03-22',
      completeness: 98.5,
      latest_source: 'Streaming provider beta live channel realtime data subscription service',
      main_source: 'Streaming provider beta live channel realtime data subscription service',
    },
    {
      ticker: 'CCCCCCC',
      exchange: 'LSE',
      name: 'Third Instrument With A Very Very Long Descriptive Name Three Holdings And Investments Trust Plc',
      earliest: '2025-03-15',
      latest: '2026-05-10',
      completeness: 100,
      latest_source: 'Batch ingestion pipeline gamma workflow processing engine',
      main_source: 'Batch ingestion pipeline gamma workflow processing engine',
    },
    {
      ticker: 'DDDDDDD',
      exchange: 'NASDAQ',
      name: 'Fourth Instrument Name Is Also Quite Extensive Four Limited Company Registered',
      earliest: '2024-11-20',
      latest: '2026-07-01',
      completeness: 95.25,
      latest_source: 'Manual import delta workflow process scheduled job runner',
      main_source: 'Manual import delta workflow process scheduled job runner',
    },
    {
      ticker: 'EEEEEEE',
      exchange: 'NYSE',
      name: 'Fifth Instrument With An Incredibly Long Descriptive Name For Overflow Guarantee Five Fund LLC',
      earliest: '2025-07-10',
      latest: '2026-08-01',
      completeness: 97.8,
      latest_source: 'Automated ETL pipeline epsilon daily batch extraction layer',
      main_source: 'Automated ETL pipeline epsilon daily batch extraction layer',
    },
  ];
  await page.route('**/timeseries/admin', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(timeseriesAdminRows),
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
      // Navigate to bare /portfolio (not /portfolio/demo-owner) so the
      // page.goto doesn't match the '**/portfolio/demo-owner*' route mock.
      // The app's renderMainContent will <Navigate> to /portfolio/demo-owner
      // once owners are loaded, and then the grid becomes visible.
      await page.goto(new URL('/portfolio', baseUrl).toString());
      await page.waitForURL('**/portfolio/demo-owner');

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
        await assertScrollableTable(table, viewport.width);
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
