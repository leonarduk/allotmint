import { expect, test, type Page, type Route } from '@playwright/test';

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

type ModeAssertion = { kind: 'mode'; mode: string };
type HeadingAssertion = {
  kind: 'heading';
  name: string | RegExp;
  level?: number;
};
type TextAssertion = { kind: 'text'; value: string };
type TestIdAssertion = { kind: 'testId'; value: string };

type RouteConfig = {
  path: string;
  assertion: ModeAssertion | HeadingAssertion | TextAssertion | TestIdAssertion;
};

const ROUTES: RouteConfig[] = [
  { path: '/', assertion: { kind: 'mode', mode: 'group' } },
  { path: '/portfolio', assertion: { kind: 'mode', mode: 'owner' } },
  { path: '/portfolio/demo-owner', assertion: { kind: 'mode', mode: 'owner' } },
  { path: '/performance', assertion: { kind: 'mode', mode: 'performance' } },
  {
    path: '/performance/demo-owner',
    assertion: { kind: 'mode', mode: 'performance' },
  },
  { path: '/instrument', assertion: { kind: 'mode', mode: 'instrument' } },
  { path: '/transactions', assertion: { kind: 'mode', mode: 'transactions' } },
  { path: '/trading', assertion: { kind: 'mode', mode: 'trading' } },
  { path: '/screener', assertion: { kind: 'mode', mode: 'screener' } },
  { path: '/timeseries', assertion: { kind: 'mode', mode: 'timeseries' } },
  { path: '/watchlist', assertion: { kind: 'mode', mode: 'watchlist' } },
  { path: '/market', assertion: { kind: 'mode', mode: 'market' } },
  { path: '/allocation', assertion: { kind: 'mode', mode: 'allocation' } },
  { path: '/rebalance', assertion: { kind: 'mode', mode: 'rebalance' } },
  { path: '/movers', assertion: { kind: 'mode', mode: 'movers' } },
  {
    path: '/instrumentadmin',
    assertion: { kind: 'mode', mode: 'instrumentadmin' },
  },
  { path: '/dataadmin', assertion: { kind: 'mode', mode: 'dataadmin' } },
  { path: '/reports', assertion: { kind: 'mode', mode: 'reports' } },
  { path: '/tax-tools', assertion: { kind: 'mode', mode: 'taxtools' } },
  { path: '/scenario', assertion: { kind: 'mode', mode: 'scenario' } },
  { path: '/pension/forecast', assertion: { kind: 'mode', mode: 'pension' } },
  { path: '/research/AAA', assertion: { kind: 'mode', mode: 'research' } },
  { path: '/virtual', assertion: { kind: 'heading', name: 'Virtual Portfolios' } },
  { path: '/support', assertion: { kind: 'heading', name: 'Support' } },
  { path: '/alerts', assertion: { kind: 'testId', value: 'alerts-page-marker' } },
  { path: '/alert-settings', assertion: { kind: 'heading', name: 'Alert Settings' } },
  { path: '/goals', assertion: { kind: 'heading', name: 'Goals' } },
  { path: '/trail', assertion: { kind: 'heading', name: 'Trail progress' } },
  { path: '/smoke-test', assertion: { kind: 'heading', name: 'Smoke test' } },
  {
    path: '/metrics-explained',
    assertion: { kind: 'heading', name: 'Performance Metrics Explained' },
  },
  {
    path: '/returns/compare',
    assertion: { kind: 'heading', name: /Return Comparison/ },
  },
  {
    path: '/returns/compare?owner=demo-owner',
    assertion: { kind: 'heading', name: 'Return Comparison – demo-owner' },
  },
  {
    path: '/performance/demo-owner/diagnostics',
    assertion: { kind: 'heading', name: 'Performance Diagnostics – demo-owner' },
  },
  {
    path: '/trade-compliance',
    assertion: { kind: 'heading', name: 'Trade compliance' },
  },
  {
    path: '/trade-compliance/demo-owner',
    assertion: { kind: 'heading', name: 'Trade compliance' },
  },
  {
    path: '/compliance',
    assertion: { kind: 'heading', name: 'Compliance warnings' },
  },
  {
    path: '/compliance/demo-owner',
    assertion: { kind: 'heading', name: 'Compliance warnings' },
  },
];

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

test.describe('public route smoke coverage', () => {
  for (const route of ROUTES) {
    test(`renders ${route.path}`, async ({ page }) => {
      const target = new URL(route.path, baseUrl);
      const pageErrors: Error[] = [];
      page.on('pageerror', (error) => {
        pageErrors.push(error);
      });

      await applyAuth(page);

      await page.goto(target.href);
      await expect(page).toHaveURL(target.href);

      if (route.assertion.kind === 'mode') {
        const marker = page.getByTestId('active-route-marker');
        await expect(marker).toHaveAttribute('data-mode', route.assertion.mode);
        await expect(marker).toHaveAttribute('data-pathname', target.pathname);
      } else if (route.assertion.kind === 'heading') {
        await expect(
          page.getByRole('heading', {
            name: route.assertion.name,
            level: route.assertion.level ?? 1,
          }),
        ).toBeVisible();
      } else if (route.assertion.kind === 'testId') {
        await expect(page.getByTestId(route.assertion.value)).toHaveCount(1);
      } else {
        await expect(
          page.getByText(route.assertion.value, { exact: true }),
        ).toBeVisible();
      }

      expect(pageErrors).toHaveLength(0);
    });
  }
});

test.describe('config bootstrap', () => {
  test('renders the route marker after retrying config load', async ({ page }) => {
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
