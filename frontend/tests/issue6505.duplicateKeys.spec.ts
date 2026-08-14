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
    await expect(page.getByText('CASH').first()).toBeVisible();
    await expect(page.getByText('CASH').nth(1)).toBeVisible();
    await expect(page.getByText('PFE').first()).toBeVisible();
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
    await expect(page.getByText('CASH').first()).toBeVisible();
    await expect(page.getByText('PFE').first()).toBeVisible();
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
    await expect(page.getByText('CASH').first()).toBeVisible();
    await expect(page.getByText('PFE').first()).toBeVisible();
    expect(warnings).toEqual([]);
  });
});
