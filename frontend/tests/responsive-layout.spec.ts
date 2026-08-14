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

/**
 * Produce a deliberately long alphanumeric string with no hyphens,
 * spaces, or punctuation so the browser cannot break it across lines.
 * This forces the table column to expand beyond the scroll wrapper
 * width even at the widest test viewport (xl = 1280px, container ≈ 992px).
 */
const forceOverflow = (base: string, times = 4): string => {
  const token = base.replaceAll(/[^a-zA-Z0-9]/g, '');
  return Array.from({ length: times }, () => token).join('');
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
  // InstrumentAdmin: inputs default to size≈20 in most browsers, but the
  // table uses table-layout:auto — hyphenated strings with no spaces force
  // columns wider than the container, guaranteeing overflow at every
  // viewport.
  const instrumentAdminRows = [
    {
      ticker: 'AAAAAAA.L',
      exchange: 'LSE',
      name: forceOverflow('Very-Long-Instrument-Name-Number-One-Plc'),
      region: forceOverflow('United-Kingdom'),
      sector: forceOverflow('Technology-Hardware-and-Equipment'),
      grouping: 'ISA',
    },
    {
      ticker: 'BBBBBBB.N',
      exchange: 'NYSE',
      name: forceOverflow('Another-Excessively-Long-Instrument-Name-Two-Corp'),
      region: forceOverflow('United-States-of-America'),
      sector: forceOverflow('Financial-Services-and-Insurance'),
      grouping: 'GIA',
    },
    {
      ticker: 'CCCCCCC.L',
      exchange: 'LSE',
      name: forceOverflow('Third-Instrument-Very-Very-Long-Descriptive-Name-Three-Holdings-Ltd'),
      region: forceOverflow('European-Union'),
      sector: forceOverflow('Healthcare-and-Biotechnology-Research'),
      grouping: 'SIPP',
    },
    {
      ticker: 'DDDDDDD.N',
      exchange: 'NASDAQ',
      name: forceOverflow('Fourth-Instrument-Name-Also-Quite-Extensive-Four-REIT'),
      region: forceOverflow('Asia-Pacific-Region'),
      sector: forceOverflow('Real-Estate-Investment-Trust-Services'),
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
  // DataAdmin: text content wraps on spaces, so use hyphenated strings
  // (no spaces) for name, latest_source, and main_source. These are the
  // widest columns and the hyphenation prevents the browser from
  // compressing them, guaranteeing scrollWidth > clientWidth.
  const timeseriesAdminRows = [
    {
      ticker: 'AAAAAAA',
      exchange: 'LSE',
      name: forceOverflow('Very-Long-Instrument-Name-Number-One-Plc'),
      earliest: '2025-01-01',
      latest: '2026-01-15',
      completeness: 100,
      latest_source: forceOverflow('deterministic-feed-source-alpha-primary'),
      main_source: forceOverflow('deterministic-feed-source-alpha-primary'),
    },
    {
      ticker: 'BBBBBBB',
      exchange: 'NYSE',
      name: forceOverflow('Another-Excessively-Long-Instrument-Name-Two-Corporation'),
      earliest: '2024-06-01',
      latest: '2026-03-22',
      completeness: 98.5,
      latest_source: forceOverflow('streaming-provider-beta-live-channel'),
      main_source: forceOverflow('streaming-provider-beta-live-channel'),
    },
    {
      ticker: 'CCCCCCC',
      exchange: 'LSE',
      name: forceOverflow('Third-Instrument-Very-Very-Long-Descriptive-Name-Three-Holdings'),
      earliest: '2025-03-15',
      latest: '2026-05-10',
      completeness: 100,
      latest_source: forceOverflow('batch-ingestion-pipeline-gamma-workflow-engine'),
      main_source: forceOverflow('batch-ingestion-pipeline-gamma-workflow-engine'),
    },
    {
      ticker: 'DDDDDDD',
      exchange: 'NASDAQ',
      name: forceOverflow('Fourth-Instrument-Name-Also-Quite-Extensive-Four-Limited'),
      earliest: '2024-11-20',
      latest: '2026-07-01',
      completeness: 95.25,
      latest_source: forceOverflow('manual-import-delta-workflow-scheduled-runner'),
      main_source: forceOverflow('manual-import-delta-workflow-scheduled-runner'),
    },
    {
      ticker: 'EEEEEEE',
      exchange: 'NYSE',
      name: forceOverflow('Fifth-Instrument-Incredibly-Long-Descriptive-Name-Five-Fund'),
      earliest: '2025-07-10',
      latest: '2026-08-01',
      completeness: 97.8,
      latest_source: forceOverflow('automated-etl-pipeline-epsilon-batch-extraction'),
      main_source: forceOverflow('automated-etl-pipeline-epsilon-batch-extraction'),
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

test('mobile holdings keep native table layout while virtual rows scroll', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await preparePage(page);

  const holdings = Array.from({ length: 160 }, (_, index) => ({
    ticker: `MOB${index.toString().padStart(3, '0')}`,
    name: `Mobile holding ${index}`,
    units: index + 1,
    market_value_gbp: 100 + index,
    cost_basis_gbp: 80 + index,
    current_price_gbp: 10,
    currency: 'GBP',
    instrument_type: 'Equity',
    acquired_date: '2025-01-01',
  }));
  await page.route('**/portfolio-group/all*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...groupPortfolio,
        accounts: [{ ...groupPortfolio.accounts[0], holdings }],
      }),
    })
  );

  await page.goto(new URL('/', baseUrl).toString());
  // The dashboard now renders the owner summary table (wrapped in its own
  // scroll container) before the holdings table; target the holdings table
  // specifically via its virtualised rows.
  const table = page
    .getByRole('table')
    .filter({ has: page.locator('tbody tr[data-index]') });
  await expect(table).toBeVisible();
  await expect(table).toHaveCSS('display', 'table');

  const scrollContainer = table.locator('..');
  await scrollContainer.evaluate((element) => {
    element.scrollTop = element.scrollHeight / 2;
    element.dispatchEvent(new Event('scroll'));
  });

  await expect
    .poll(() =>
      scrollContainer.evaluate((element) => {
        const bounds = element.getBoundingClientRect();
        return Array.from(
          element.querySelectorAll('tbody tr[data-index]')
        ).some((row) => {
          const rowBounds = row.getBoundingClientRect();
          return rowBounds.bottom > bounds.top && rowBounds.top < bounds.bottom;
        });
      })
    )
    .toBe(true);
});

test('issue 6675: dashboard, instrument and trading wide tables stay inside their scroll wrappers', async ({
  page,
}) => {
  // Deliberately unbreakable long strings force every table to exceed the
  // container at mobile/tablet widths (see forceOverflow), reproducing the
  // page-level horizontal scroll reported in #6675.
  const longName = forceOverflow(
    'Extremely-Long-Unbreakable-Instrument-Name-For-Overflow-Check'
  );
  const holdings = Array.from({ length: 20 }, (_, index) => ({
    ticker: `WIDE${index.toString().padStart(3, '0')}`,
    name: `${longName}${index}`,
    units: index + 1,
    market_value_gbp: 100 + index,
    cost_basis_gbp: 80 + index,
    current_price_gbp: 10,
    currency: 'GBP',
    instrument_type: 'Equity',
    acquired_date: '2025-01-01',
  }));
  const instruments = holdings.map((h) => ({
    ticker: h.ticker,
    name: h.name,
    exchange: 'LSE',
    currency: 'GBP',
    units: h.units,
    market_value_gbp: h.market_value_gbp,
    gain_gbp: 5,
    instrument_type: 'Equity',
    gain_pct: 2.5,
  }));
  const signals = Array.from({ length: 10 }, (_, index) => ({
    ticker: `SIG${index}`,
    action: 'buy' as const,
    reason: `${longName}${index}`,
    confidence: 80,
    factors: [longName, forceOverflow('Secondary-Factor-Also-Very-Long')],
  }));
  const settings = {
    rsi_buy: 30,
    rsi_sell: 70,
    rsi_window: 14,
    ma_short_window: 20,
    ma_long_window: 50,
    pe_max: null,
    de_max: null,
    min_sharpe: null,
    max_volatility: null,
  };

  await applyAuth(page, authToken);
  await setupCoreMocks(page);
  // Generic group-portfolio mock with holdings so both the owner summary
  // table and the (wrapped) holdings table render on `/`.
  await page.route('**/portfolio-group/all*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...groupPortfolio,
        accounts: [{ ...groupPortfolio.accounts[0], holdings }],
      }),
    })
  );
  // More specific mock for the /instrument catalogue; registered after the
  // generic pattern above so it takes precedence.
  await page.route('**/portfolio-group/all/instruments', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(instruments),
    })
  );
  await page.route('**/trading-agent/signals', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(signals),
    })
  );
  await page.route('**/trading-agent/settings', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(settings),
    })
  );
  await page.route('**/quotes*', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  );

  const viewports = [
    { name: 'mobile', width: 375, height: 812 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'desktop', width: 1280, height: 800 },
  ] as const;

  for (const viewport of viewports) {
    for (const path of ['/', '/instrument', '/trading']) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(new URL(path, baseUrl).toString());

      // Wait until the route's real table(s) render (and the loading
      // skeleton, whose parent is not a scroll wrapper, is gone).
      const expectedTables = path === '/' ? 2 : 1;
      await expect(page.getByRole('table')).toHaveCount(expectedTables);

      await assertNoPageOverflow(page);

      const tables = await page.getByRole('table').all();
      expect(tables.length).toBeGreaterThan(0);
      for (const table of tables) {
        // Every wide table must live inside a clipping wrapper.
        await expect(table.locator('..')).toHaveCSS('overflow-x', 'auto');
      }
    }
  }
});

test('research tab bar and settings Add form fit on a 375px viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await preparePage(page);

  // Minimal instrument detail so the research page renders cleanly. The
  // detail URL carries a query string (/instrument/?ticker=...), so match it
  // with a regex to avoid shadowing the /instrument/admin mock registered in
  // preparePage.
  await page.route(/\/instrument\/\?ticker=/, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ticker: 'VWRL.L',
        prices: [],
        positions: [],
        mini: {},
        name: 'Vanguard FTSE All-World UCITS ETF',
        currency: 'GBP',
        instrument_type: 'ETF',
        rows: 0,
        from: null,
        to: null,
        base_currency: 'GBP',
      }),
    })
  );
  await page.route(/\/news\?ticker=/, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  );

  await page.goto(new URL('/research/VWRL.L', baseUrl).toString());
  const tabRow = page
    .getByRole('button', { name: 'Overview', exact: true })
    .locator('..');
  await expect(tabRow).toHaveClass(/(?:^|\s)flex-wrap(?:\s|$)/);
  await expect(tabRow).toHaveCSS('flex-wrap', 'wrap');
  for (const name of [
    'Overview',
    'Timeseries',
    'Positions',
    'Fundamentals',
    'News',
  ]) {
    const tab = page.getByRole('button', { name, exact: true });
    await expect(tab).toBeVisible();
    const box = await tab.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.x + box.width).toBeLessThanOrEqual(375);
    }
  }
  // News is the rightmost tab; clicking it proves it is tappable without
  // horizontal page scroll.
  await page.getByRole('button', { name: 'News', exact: true }).click();
  await expect(page.getByText('No news available')).toBeVisible();
  await assertNoPageOverflow(page);

  // Desktop keeps the single-line nowrap row (constraint: only mobile
  // behavior changes).
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(tabRow).toHaveCSS('flex-wrap', 'nowrap');
  await assertNoPageOverflow(page);

  // Settings: the Add form wraps so the Add button stays inside the viewport.
  await page.route('**/user-config/demo-owner', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  );
  await page.route('**/accounts/demo-owner/approvals', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ approvals: [] }),
    })
  );
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(new URL('/settings', baseUrl).toString());
  // The approvals section (with the Add form) only renders once an owner is
  // selected.
  await page.getByRole('combobox').selectOption('demo-owner');
  const addButton = page.getByRole('button', { name: 'Add', exact: true });
  await expect(addButton).toBeVisible();
  const addBox = await addButton.boundingBox();
  expect(addBox).not.toBeNull();
  if (addBox) {
    expect(addBox.x + addBox.width).toBeLessThanOrEqual(375);
  }
  await assertNoPageOverflow(page);
});
