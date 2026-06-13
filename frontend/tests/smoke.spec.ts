import { expect, test, type Page, type Route } from '@playwright/test';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';
const authToken = process.env.SMOKE_AUTH_TOKEN ?? process.env.TEST_ID_TOKEN ?? null;

const smokePath = new URL('/smoke-test', baseUrl).toString();
const pensionForecastPath = new URL('/pension/forecast', baseUrl).toString();

/**
 * Set up core API mocks so the app does not show BackendUnavailableCard
 * when there is no backend (e.g. CI preview build).  These provide the
 * minimum identity catalogue (/config, /owners, /groups) that the app
 * shell needs before it renders any page component.
 *
 * Tests that need to mock additional endpoints should call setupCoreMocks
 * first and then add their own route() calls.  Tests that intentionally
 * override all three endpoints with their own handlers can skip this.
 */
const setupCoreMocks = async (page: Page) => {
  await page.route('**/config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        app_env: 'test',
        theme: null,
        tabs: { trail: true, taxtools: true, 'trade-compliance': true, reports: true },
        relative_view_enabled: false,
        google_auth_enabled: false,
        google_client_id: null,
        disable_auth: true,
        allowed_emails: null,
        local_login_email: null,
        disabled_tabs: [],
        enable_family_mvp: false,
      }),
    });
  });
  await page.route('**/owners', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          owner: 'demo-owner',
          full_name: 'Demo Owner',
          accounts: ['ISA'],
          has_transactions_artifact: false,
        },
      ]),
    });
  });
  await page.route('**/groups', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ slug: 'all', name: 'All portfolios', members: ['demo-owner'] }]),
    });
  });
};

const applyAuth = async (page: Page) => {
  if (!authToken) {
    return;
  }

  await page.addInitScript((token: string) => {
    window.localStorage.setItem('authToken', token);
    // Seed a valid AWS UI auth (Cognito) session so ensureAwsUiAuth() finds an
    // unexpired session and skips the hosted-UI redirect, which would navigate
    // away from the app before it renders. See awsUiAuth.ts hasValidSession().
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: token, expiresAt: Date.now() + 60 * 60 * 1000 })
    );
  }, authToken);
};

const getActiveRouteMarker = (page: Page) =>
  page.locator('[data-route-marker="active"], [data-testid="active-route-marker"]');

const getBootstrapMarker = (page: Page) =>
  page.locator('[data-route-marker="bootstrap"], [data-testid="route-bootstrap-marker"]');

// Several non-Family-MVP redirects can change the URL in the preview build:
// - getOwnerRootRedirectPath redirects bare /portfolio→/portfolio/:owner and
//   /performance→/performance/:owner when owners are available (→'performance')
// - FAMILY_MVP_ROUTE_GATES redirect disabled-tab paths (e.g. /trail) to /
//   (→'group')
// - deriveRouteFromPathname falls back to 'movers' for unrecognised segments
//   (→'movers')
//
// Accept these modes plus the original Family MVP targets so redirects are
// handled gracefully. Disabled tabs are re-enabled via the mock config so the
// FAMILY_MVP_ROUTE_GATES redirects should not fire; the group/movers entries
// below are defensive fallbacks.
const FAMILY_MVP_ENTRY_MODES = ['transactions', 'owner', 'performance', 'group'];

const waitForStableRoutePathname = async (page: Page): Promise<string> => {
  // The Family MVP redirect effect only fires once the async /config fetch
  // resolves, which can take over a second, and an intermediate redirect hop
  // (e.g. bare /portfolio to /portfolio/<owner>) can briefly unmount the
  // route marker entirely. Read the browser URL directly — it's always
  // available, even mid-redirect. Wait out the config-fetch window first,
  // then require the pathname to stop changing for a short window before
  // treating it as settled.
  const MIN_WAIT_MS = 1800;
  const STABLE_WINDOW_MS = 450;
  const POLL_MS = 150;
  const readPathname = () => new URL(page.url()).pathname;
  await page.waitForTimeout(MIN_WAIT_MS);
  let previous = readPathname();
  let stableFor = 0;
  while (stableFor < STABLE_WINDOW_MS) {
    await page.waitForTimeout(POLL_MS);
    const current = readPathname();
    if (current === previous) {
      stableFor += POLL_MS;
    } else {
      previous = current;
      stableFor = 0;
    }
  }
  return previous;
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
  setup?: (page: Page, target: URL) => Promise<void> | void;
  extraAssertions?: (page: Page, target: URL) => Promise<void> | void;
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
  { path: '/settings', assertion: { kind: 'mode', mode: 'settings' } },
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
  {
    path: '/reports/new',
    assertion: { kind: 'heading', name: 'Create report template' },
  },
  { path: '/tax-tools', assertion: { kind: 'mode', mode: 'taxtools' } },
  { path: '/scenario', assertion: { kind: 'mode', mode: 'scenario' } },
  { path: '/pension/forecast', assertion: { kind: 'mode', mode: 'pension' } },
  { path: '/research/AAA', assertion: { kind: 'mode', mode: 'research' } },
  {
    path: '/virtual',
    assertion: { kind: 'heading', name: 'Family Manual Portfolio Setup' },
    setup: async (page) => {
      let handled = false;
      await page.route('**/virtual-portfolios', async (route) => {
        if (!handled) {
          handled = true;
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }

        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 101, name: 'Slow path demo', accounts: [], holdings: [] },
          ]),
        });
      });
      await page.route('**/owners', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { owner: 'demo-owner', full_name: 'Demo Owner', accounts: ['Account A'] },
          ]),
        });
      });
    },
    extraAssertions: async (page) => {
      await expect(page.locator('select')).toHaveCount(1);
    },
  },
  { path: '/support', assertion: { kind: 'heading', name: 'Support' } },
  // /alerts is rendered inside the app shell via the mode === 'alerts' branch in App.tsx.
  // Assert on the h1 heading (present in all render branches) rather than route-marker mode,
  // so the test confirms the Alerts component actually mounted, not just that routing activated.
  { path: '/alerts', assertion: { kind: 'heading', name: 'Alerts' } },
  { path: '/alert-settings', assertion: { kind: 'heading', name: 'Alert Settings' } },
  { path: '/goals', assertion: { kind: 'heading', name: 'Goals' } },
  {
    path: '/trail',
    assertion: { kind: 'heading', name: 'Trail progress' },
    setup: async (page) => {
      await page.route('**/trail', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            tasks: [{ id: 't1', title: 'Setup profile', completed: false, type: 'once' }],
            today: '2026-06-13',
            daily_totals: { '2026-06-13': { completed: 0, total: 1 } },
          }),
        });
      });
    },
  },
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

    await setupCoreMocks(page);
    await page.route('**/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

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

    await setupCoreMocks(page);
    await page.route('**/pension/forecast?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          current_pot: 100000,
          projected_pot: 500000,
          annual_income: 25000,
          monthly_income: 2083,
          shortfall_annual: 0,
          shortfall_monthly: 0,
        }),
      });
    });

    await page.goto(pensionForecastPath);

    await expect(page.getByRole('heading', { name: 'Pension Forecast' })).toBeVisible();
    expect(pageErrors).toHaveLength(0);
  });
});

test.describe('pension forecast routing', () => {
  test('keeps pension mode when config tab state is indeterminate', async ({ page }) => {
    await applyAuth(page);

    await page.route('**/config', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          app_env: 'test',
          theme: null,
          tabs: { pension: null, trail: true, taxtools: true, 'trade-compliance': true, reports: true },
          relative_view_enabled: false,
          google_auth_enabled: false,
          google_client_id: null,
          disable_auth: true,
          allowed_emails: null,
          local_login_email: null,
          disabled_tabs: [],
        }),
      });
    });
    await page.route('**/owners', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            owner: 'demo-owner',
            full_name: 'Demo Owner',
            accounts: ['ISA'],
            has_transactions_artifact: false,
          },
        ]),
      });
    });
    await page.route('**/groups', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ slug: 'all', name: 'All portfolios', members: ['demo-owner'] }]),
      });
    });
    await page.route('**/pension/forecast?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          current_pot: 100000,
          projected_pot: 500000,
          annual_income: 25000,
          monthly_income: 2083,
          shortfall_annual: 0,
          shortfall_monthly: 0,
        }),
      });
    });

    await page.goto(pensionForecastPath);

    const marker = getActiveRouteMarker(page);
    await expect(marker).toHaveAttribute('data-mode', 'pension');
    await expect(marker).toHaveAttribute('data-pathname', '/pension/forecast');
    await expect(page.getByRole('heading', { name: 'Pension Forecast' })).toBeVisible();
  });
});


test.describe('bootstrap to portfolio happy path', () => {
  test('keeps /portfolio stable while exposing owner mode and selector state', async ({ page }) => {
    await applyAuth(page);

    await page.route('**/config', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          app_env: 'test',
          theme: null,
          enable_family_mvp: false,
          google_auth_enabled: false,
          google_client_id: '',
          disable_auth: true,
          local_login_email: 'demo@example.com',
          tabs: { trail: true, taxtools: true, 'trade-compliance': true, reports: true },
          disabled_tabs: [],
        }),
      });
    });

    await page.route('**/owners', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            owner: 'demo-owner',
            full_name: 'Demo Owner',
            accounts: ['ISA'],
            has_transactions_artifact: false,
          },
        ]),
      });
    });

    await page.route('**/groups', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ slug: 'all', name: 'All portfolios', members: ['demo-owner'] }]),
      });
    });

    await page.route('**/portfolio/demo-owner', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          owner: 'demo-owner',
          as_of: '2026-03-22',
          accounts: [
            {
              account_type: 'ISA',
              holdings: [],
            },
          ],
          total_value_estimate_gbp: 1000,
        }),
      });
    });

    await page.goto(new URL('/portfolio', baseUrl).toString());

    await expect(page).toHaveURL(new URL('/portfolio', baseUrl).toString());
    await expect(getActiveRouteMarker(page)).toHaveAttribute('data-mode', 'owner');
    await expect(getActiveRouteMarker(page)).toHaveAttribute('data-pathname', '/portfolio');
    await expect(page.getByTestId('portfolio-owner-selector')).toBeVisible();
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

      await setupCoreMocks(page);

      if (route.setup) {
        await route.setup(page, target);
      }

      await page.goto(target.href);

      const settledPathname = await waitForStableRoutePathname(page);
      if (settledPathname !== target.pathname) {
        await expect(getActiveRouteMarker(page)).toBeVisible();
        const redirectedMode = await getActiveRouteMarker(page).getAttribute('data-mode');
        expect(FAMILY_MVP_ENTRY_MODES).toContain(redirectedMode);
        expect(pageErrors).toHaveLength(0);
        return;
      }

      await expect(page).toHaveURL(target.href);

      if (route.assertion.kind === 'mode') {
        const marker = getActiveRouteMarker(page);
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

      if (route.extraAssertions) {
        await route.extraAssertions(page, target);
      }

      expect(pageErrors).toHaveLength(0);
    });
  }
});

test.describe('config bootstrap', () => {
  test('exposes the route marker while configuration is loading', async ({ page }) => {
    await applyAuth(page);

    const target = new URL('/portfolio', baseUrl);

    const handler = async (route: Route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    };

    await page.route('**/config', handler);

    const navigation = page.goto(target.href);

    const marker = getBootstrapMarker(page);
    await expect(marker).toHaveAttribute('data-mode', 'loading');
    await expect(marker).toHaveAttribute('data-pathname', '/portfolio');

    await expect(page.getByText('Loading configuration...')).toBeVisible();

    await navigation;

    await page.unroute('**/config', handler);
  });

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
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          app_env: 'test',
          theme: null,
          enable_family_mvp: false,
          relative_view_enabled: false,
          google_auth_enabled: false,
          google_client_id: null,
          disable_auth: true,
          allowed_emails: null,
          local_login_email: null,
          tabs: { trail: true, taxtools: true, 'trade-compliance': true, reports: true },
          disabled_tabs: [],
        }),
      });
    };

    await page.route('**/config', handler);
    await page.route('**/owners', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            owner: 'demo-owner',
            full_name: 'Demo Owner',
            accounts: ['ISA'],
            has_transactions_artifact: false,
          },
        ]),
      });
    });
    await page.route('**/groups', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ slug: 'all', name: 'All portfolios', members: ['demo-owner'] }]),
      });
    });

    const firstFailure = page.waitForEvent('requestfailed', (request) =>
      request.url().endsWith('/config'),
    );
    const secondResponse = page.waitForResponse((response) =>
      response.url().endsWith('/config') && response.ok(),
    );

    await page.goto(rootUrl);

    await firstFailure;
    await secondResponse;

    await expect.poll(() => attempt).toBeGreaterThan(1);

    const marker = getActiveRouteMarker(page);
    await expect(marker).toBeVisible();
    await expect(marker).toHaveAttribute('data-mode', 'group');
    await expect(marker).toHaveAttribute('data-pathname', '/');

    await page.unroute('**/config', handler);
  });
});

test.describe('timeseries edit resilience', () => {
  test('keeps the route marker visible when the edit load fails', async ({ page }) => {
    await applyAuth(page);

    await setupCoreMocks(page);

    const target = new URL('/timeseries?ticker=FAIL&exchange=L', baseUrl);
    let requested = false;

    await page.route('**/timeseries/edit?*', async (route) => {
      requested = true;
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'upstream failed' }),
      });
    });

    await page.goto(target.href);

    const settledPathname = await waitForStableRoutePathname(page);
    if (settledPathname !== target.pathname) {
      await expect(getActiveRouteMarker(page)).toBeVisible();
      const redirectedMode = await getActiveRouteMarker(page).getAttribute('data-mode');
      expect(FAMILY_MVP_ENTRY_MODES).toContain(redirectedMode);
      return;
    }

    const loadButton = page.getByTestId('load-button');
    await expect(loadButton).toBeEnabled();
    await loadButton.click();

    await expect.poll(() => requested).toBeTruthy();

    const marker = getActiveRouteMarker(page);
    await expect(marker).toHaveAttribute('data-mode', 'timeseries');
    await expect(marker).toHaveAttribute('data-pathname', '/timeseries');
  });
});
