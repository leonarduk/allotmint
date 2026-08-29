import { expect, test, type Page } from '@playwright/test';
import {
  applyAuth as applyAuthToken,
  setupCoreMocks,
} from './support/smokeFixtures';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';
const authToken = process.env.SMOKE_AUTH_TOKEN ?? process.env.TEST_ID_TOKEN ?? null;

const applyAuth = (page: Page) => applyAuthToken(page, authToken);

/**
 * Regression test for #6505: React "duplicate key" console warnings when the
 * same ticker exists under multiple exchanges (e.g. CASH/GBP + CASH/L).
 *
 * Each page is served duplicate-ticker fixtures via mocked API routes and we
 * assert zero `Encountered two children with the same key` console messages.
 * (The page-level duplicate-key warning fires through console.error even in a
 * production/preview build, so this works against the preview server.)
 */
const DUPLICATE_KEY_MESSAGE = /same key/i;

const collectDuplicateKeyWarnings = (page: Page) => {
  const warnings: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' && DUPLICATE_KEY_MESSAGE.test(msg.text())) {
      warnings.push(msg.text().slice(0, 200));
    }
  });
  return warnings;
};

test.describe('issue 6505: no duplicate-key warnings for same-ticker rows', () => {
  test('data-quality page renders same ticker under two exchanges without warnings', async ({
    page,
  }) => {
    const warnings = collectDuplicateKeyWarnings(page);
    await applyAuth(page);
    await setupCoreMocks(page);
    await page.route('**/data-quality/timeseries', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          count: 4,
          positions: [
            {
              ticker: 'CASH',
              exchange: 'GBP',
              total_points: 100,
              first_date: '2026-01-01',
              last_date: '2026-06-01',
              gap_count: 0,
              gaps: [],
              duplicate_dates: [],
              outliers: [],
            },
            {
              ticker: 'CASH',
              exchange: 'L',
              total_points: 90,
              first_date: '2026-01-01',
              last_date: '2026-06-01',
              gap_count: 0,
              gaps: [],
              duplicate_dates: [],
              outliers: [],
            },
            {
              ticker: 'PFE',
              exchange: 'N',
              total_points: 80,
              first_date: '2026-01-01',
              last_date: '2026-06-01',
              gap_count: 0,
              gaps: [],
              duplicate_dates: [],
              outliers: [],
            },
            {
              ticker: 'PFE',
              exchange: 'L',
              total_points: 70,
              first_date: '2026-01-01',
              last_date: '2026-06-01',
              gap_count: 0,
              gaps: [],
              duplicate_dates: [],
              outliers: [],
            },
          ],
        }),
      });
    });

    await page.goto(`${baseUrl}/data-quality`);
    // The timeseries quality data now lives under the "Series" tab (the page
    // defaults to "Issues"); switch tabs before asserting on its contents.
    await page.getByRole('tab', { name: 'Series' }).click();
    // Both CASH and PFE entries (one per exchange) must render.
    await expect(page.getByText('CASH', { exact: true })).toHaveCount(2);
    await expect(page.getByText('PFE', { exact: true })).toHaveCount(2);
    expect(warnings).toEqual([]);
  });

  test('movers page renders duplicate tickers without warnings', async ({ page }) => {
    const warnings = collectDuplicateKeyWarnings(page);
    await applyAuth(page);
    await setupCoreMocks(page);
    await page.route('**/opportunities**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          entries: [
            { ticker: 'CASH', name: 'Cash GBP', change_pct: 5, side: 'gainers' },
            { ticker: 'CASH', name: 'Cash L', change_pct: 3, side: 'gainers' },
            { ticker: 'PFE', name: 'Pfizer N', change_pct: -2, side: 'losers' },
            { ticker: 'PFE', name: 'Pfizer L', change_pct: -4, side: 'losers' },
          ],
          signals: [],
          context: { source: 'group', group: 'all', days: 1, anomalies: [] },
        }),
      });
    });
    await page.route('**/portfolio-group/all/instruments**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { ticker: 'CASH', name: 'Cash GBP', market_value_gbp: 10 },
          { ticker: 'PFE', name: 'Pfizer', market_value_gbp: 20 },
        ]),
      });
    });

    await page.goto(`${baseUrl}/movers`);
    // Both duplicate entries must render before we can trust the warning check.
    await expect(page.getByText('CASH', { exact: true })).toHaveCount(2);
    await expect(page.getByText('PFE', { exact: true })).toHaveCount(2);
    expect(warnings).toEqual([]);
  });

  test('trading page renders duplicate signal tickers without warnings', async ({ page }) => {
    const warnings = collectDuplicateKeyWarnings(page);
    await applyAuth(page);
    await setupCoreMocks(page);
    await page.route('**/trading-agent/signals', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { ticker: 'CASH', name: 'Cash GBP', action: 'buy', reason: 'a' },
          { ticker: 'CASH', name: 'Cash L', action: 'sell', reason: 'b' },
          { ticker: 'PFE', name: 'Pfizer N', action: 'buy', reason: 'c' },
          { ticker: 'PFE', name: 'Pfizer L', action: 'sell', reason: 'd' },
        ]),
      });
    });
    await page.route('**/trading-agent/settings', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rsi_buy: 30,
          rsi_sell: 70,
          rsi_window: 14,
          ma_short_window: 20,
          ma_long_window: 50,
        }),
      });
    });

    await page.goto(`${baseUrl}/trading`);
    // Both duplicate signal rows must render before we can trust the warning check.
    await expect(page.getByText('CASH', { exact: true })).toHaveCount(2);
    await expect(page.getByText('PFE', { exact: true })).toHaveCount(2);
    expect(warnings).toEqual([]);
  });

  test('screener page renders duplicate ticker rows without warnings', async ({ page }) => {
    const warnings = collectDuplicateKeyWarnings(page);
    await applyAuth(page);
    await setupCoreMocks(page);
    // /screener renders ScreenerQuery which embeds the Screener component;
    // the embedded form calls getScreener -> /screener?<criteria>.
    await page.route('**://localhost:8000/custom-query/saved**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    });
    await page.route('**://localhost:8000/screener**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { rank: 1, ticker: 'CASH', name: 'Cash GBP', peg_ratio: null, pe_ratio: null, de_ratio: null, lt_de_ratio: null, interest_coverage: null, current_ratio: null, quick_ratio: null, fcf: null, eps: null, gross_margin: null, operating_margin: null, net_margin: null, ebitda_margin: null, roa: null, roe: null, roi: null, dividend_yield: null, dividend_payout_ratio: null, beta: null, shares_outstanding: null, float_shares: null, market_cap: null, high_52w: null, low_52w: null, avg_volume: null },
          { rank: 2, ticker: 'CASH', name: 'Cash L', peg_ratio: null, pe_ratio: null, de_ratio: null, lt_de_ratio: null, interest_coverage: null, current_ratio: null, quick_ratio: null, fcf: null, eps: null, gross_margin: null, operating_margin: null, net_margin: null, ebitda_margin: null, roa: null, roe: null, roi: null, dividend_yield: null, dividend_payout_ratio: null, beta: null, shares_outstanding: null, float_shares: null, market_cap: null, high_52w: null, low_52w: null, avg_volume: null },
        ]),
      });
    });

    await page.goto(`${baseUrl}/screener`);
    // The embedded Screener form (first "Run" button, before the custom-query
    // form's Run) renders duplicate rows via getScreener.
    const tickersInput = page.getByLabel(/Tickers/i);
    await tickersInput.fill('CASH');
    await page.getByRole('button', { name: 'Run' }).nth(0).click();
    // Both duplicate rows must render before we can trust the warning check.
    await expect(page.getByText('CASH', { exact: true })).toHaveCount(2);
    expect(warnings).toEqual([]);
  });

  test('settings page renders duplicate approvals without warnings', async ({ page }) => {
    const warnings = collectDuplicateKeyWarnings(page);
    await applyAuth(page);
    await setupCoreMocks(page);
    await page.route('**://localhost:8000/accounts/**/approvals**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          approvals: [
            { ticker: 'PFE', approved_on: '2026-01-01' },
            { ticker: 'PFE', approved_on: '2026-01-01' },
          ],
        }),
      });
    });

    await page.goto(`${baseUrl}/settings`);
    // The owner select is unlabeled (placeholder "Select owner"); choose the
    // mocked owner so the approvals fetch fires.
    const ownerSelect = page.locator('select').first();
    await ownerSelect.selectOption({ label: 'Demo Owner' });
    // Both duplicate approval rows must render before we can trust the warning check.
    await expect(page.getByText('PFE', { exact: true })).toHaveCount(2);
    expect(warnings).toEqual([]);
  });

  test('rebalance page renders aggregated duplicate holdings without warnings', async ({ page }) => {
    const warnings = collectDuplicateKeyWarnings(page);
    await applyAuth(page);
    await setupCoreMocks(page);
    await page.route('**://localhost:8000/portfolio/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          owner: 'demo-owner',
          as_of: '2026-01-01',
          trades_this_month: 0,
          trades_remaining: 10,
          total_value_estimate_gbp: 3,
          accounts: [
            {
              account_type: 'ISA',
              currency: 'GBP',
              value_estimate_gbp: 3,
              holdings: [
                { ticker: 'CASH', name: 'Cash GBP', units: 2, market_value_gbp: 2 },
                { ticker: 'CASH', name: 'Cash L', units: 1, market_value_gbp: 1 },
              ],
            },
          ],
        }),
      });
    });
    await page.route('**://localhost:8000/rebalance', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { ticker: 'CASH', action: 'sell', amount: 10 },
          { ticker: 'PFE', action: 'buy', amount: 10 },
        ]),
      });
    });

    await page.goto(`${baseUrl}/rebalance`);
    // Input rows aggregate by ticker; expect exactly one CASH input row.
    await expect(page.getByLabel(/Target weight \(%\) for CASH/)).toHaveCount(1);
    expect(warnings).toEqual([]);
  });

  test('research page search renders duplicate suggestions without warnings', async ({
    page,
  }) => {
    const warnings = collectDuplicateKeyWarnings(page);
    await applyAuth(page);
    await setupCoreMocks(page);
    // The instrument search bar (InstrumentSearchBar) renders suggestions keyed
    // by ticker+index; duplicate tickers must not produce duplicate-key
    // warnings. The header and embedded instances are the same component, so
    // driving either exercises the same keyed render path.
    await page.route('**/instrument/search**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { ticker: 'CASH', name: 'Cash GBP' },
          { ticker: 'CASH', name: 'Cash L' },
          { ticker: 'PFE', name: 'Pfizer N' },
          { ticker: 'PFE', name: 'Pfizer L' },
        ]),
      });
    });

    await page.goto(`${baseUrl}/research`);
    // /research with no ticker now embeds its own search bar (#7223), so type
    // straight into it. Do not open the header toggle as well — that mounts a
    // second input with the same label and trips Playwright strict mode.
    await page.getByLabel('Search instruments').fill('CA');
    // Both duplicate suggestions must render before we can trust the warning check.
    await expect(page.getByText('CASH — Cash GBP', { exact: true })).toBeVisible();
    await expect(page.getByText('CASH — Cash L', { exact: true })).toBeVisible();
    expect(warnings).toEqual([]);
  });
});
