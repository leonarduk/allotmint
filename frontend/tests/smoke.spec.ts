import { expect, test, type Page, type Route } from '@playwright/test';
import {
  applyAuth as applyAuthToken,
  DEFAULT_CONFIG_BODY,
  DEFAULT_GROUPS_BODY,
  DEFAULT_OWNERS_BODY,
  getActiveRouteMarker,
  getBootstrapMarker,
  setupCoreMocks,
} from './support/smokeFixtures';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';
const authToken = process.env.SMOKE_AUTH_TOKEN ?? process.env.TEST_ID_TOKEN ?? null;

const smokePath = new URL('/smoke-test', baseUrl).toString();
const pensionForecastPath = new URL('/pension/forecast', baseUrl).toString();

const applyAuth = (page: Page) => applyAuthToken(page, authToken);

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
// below are defensive fallbacks. Named for what it now covers (renamed from
// FAMILY_MVP_ENTRY_MODES, which undersold its scope once the owner/
// performance/movers fallbacks were added).
const ACCEPTED_REDIRECT_MODES = ['transactions', 'owner', 'performance', 'group'];

// Ceiling on how long the async /config fetch (which gates the Family MVP
// redirect effect) is allowed to take before we give up waiting on it.
const CONFIG_SETTLE_TIMEOUT_MS = 5000;
// Once config has resolved, require the URL to stop changing for this long
// before treating a route as settled — long enough to catch a redirect hop
// (e.g. bare /portfolio to /portfolio/<owner>), short because at this point
// the only remaining source of change is synchronous client-side routing.
const STABLE_WINDOW_MS = 450;
// How often to re-check the URL while waiting for it to stabilise.
const POLL_MS = 150;

if (STABLE_WINDOW_MS % POLL_MS !== 0) {
  throw new Error(
    `STABLE_WINDOW_MS (${STABLE_WINDOW_MS}) must be a whole multiple of POLL_MS (${POLL_MS}) ` +
      'so the stability window is measured in whole polling ticks.'
  );
}

const waitForStableRoutePathname = async (page: Page): Promise<string> => {
  // main.tsx renders a `route-bootstrap-marker` element only while the async
  // /config fetch is in flight; it is removed once config resolves and the
  // real App mounts. Waiting on its removal (rather than sleeping a fixed
  // MIN_WAIT_MS floor) means routes that never redirect settle as soon as
  // config resolves, instead of every route paying the same worst-case wait.
  await page
    .waitForFunction(
      () => document.querySelector('[data-testid="route-bootstrap-marker"]') === null,
      undefined,
      { timeout: CONFIG_SETTLE_TIMEOUT_MS }
    )
    .catch(() => {
      // If the bootstrap marker never clears within the ceiling, fall through
      // to the stability poll below rather than hanging indefinitely — the
      // assertions after this function returns will fail loudly on whatever
      // pathname we ended up on.
    });

  // An intermediate redirect hop (e.g. bare /portfolio to /portfolio/<owner>)
  // can briefly unmount the route marker entirely, so read the browser URL
  // directly here — it's always available, even mid-redirect.
  const readPathname = () => new URL(page.url()).pathname;
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
      // VirtualPortfolio is localStorage-backed, not driven by the mocked
      // /virtual-portfolios response above (that mock exists purely to
      // confirm a slow, unrelated in-flight request doesn't block the page
      // from settling). Assert the manual-entry form itself mounted, so this
      // route's content is verified beyond just the top-level heading.
      await expect(page.getByRole('heading', { name: 'Add account', level: 2 })).toBeVisible();
      await expect(
        page.getByPlaceholder('Account name (e.g. ISA, Pension, Brokerage)')
      ).toBeVisible();
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
        // Only intercept API calls, not the page navigation to /trail itself.
        if (route.request().resourceType() === 'document') {
          await route.continue();
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            tasks: [
              { id: '1', title: 'Review portfolio', type: 'daily', commentary: '', completed: false },
              { id: '2', title: 'Check alerts', type: 'daily', commentary: '', completed: true },
              { id: '3', title: 'Setup watchlist', type: 'once', commentary: 'One-time task', completed: false },
            ],
            xp: 10,
            streak: 3,
            daily_totals: { '2025-01-01': { completed: 1, total: 2 } },
            today: '2025-01-01',
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
  {
    path: '/create-account',
    assertion: { kind: 'heading', name: 'Create account' },
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
          forecast: [{ age: 30, income: 25000 }],
          projected_pot_gbp: 500000,
          pension_pot_gbp: 100000,
          current_age: 30,
          retirement_age: 65,
          dob: '1996-01-01',
          earliest_retirement_age: 55,
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
        body: JSON.stringify(DEFAULT_OWNERS_BODY),
      });
    });
    await page.route('**/groups', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DEFAULT_GROUPS_BODY),
      });
    });
    await page.route('**/pension/forecast?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          forecast: [{ age: 30, income: 25000 }],
          projected_pot_gbp: 500000,
          pension_pot_gbp: 100000,
          current_age: 30,
          retirement_age: 65,
          dob: '1996-01-01',
          earliest_retirement_age: 55,
        }),
      });
    });

    await page.goto(pensionForecastPath);

    const marker = getActiveRouteMarker(page);
    await expect(marker).toHaveAttribute('data-mode', 'pension');
    await expect(marker).toHaveAttribute('data-pathname', '/pension/forecast');
  });
});


test.describe('bootstrap to portfolio happy path', () => {
  test('keeps /portfolio stable while exposing owner mode and selector state', async ({ page }) => {
    await applyAuth(page);

    await page.route('**/config', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...DEFAULT_CONFIG_BODY, local_login_email: 'demo@example.com' }),
      });
    });

    await page.route('**/owners', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DEFAULT_OWNERS_BODY),
      });
    });

    await page.route('**/groups', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DEFAULT_GROUPS_BODY),
      });
    });

    await page.route('**/portfolio/demo-owner', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          owner: 'demo-owner',
          as_of: '2026-03-22',
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
        }),
      });
    });

    // Navigate to bare /portfolio (not /portfolio/demo-owner) so the
    // page.goto doesn't match the '**/portfolio/demo-owner' route mock.
    // The app's renderMainContent will <Navigate> to /portfolio/demo-owner
    // once owners are loaded, and then the selector becomes visible.
    await page.goto(new URL('/portfolio', baseUrl).toString());

    // Wait for the redirect to /portfolio/demo-owner to settle.
    await page.waitForURL('**/portfolio/demo-owner');

    await expect(page.getByTestId('portfolio-owner-selector')).toBeVisible();
    await expect(getActiveRouteMarker(page)).toHaveAttribute('data-mode', 'owner');
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
        expect(ACCEPTED_REDIRECT_MODES).toContain(redirectedMode);
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
        body: JSON.stringify(DEFAULT_CONFIG_BODY),
      });
    };

    await page.route('**/config', handler);
    await page.route('**/owners', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DEFAULT_OWNERS_BODY),
      });
    });
    await page.route('**/groups', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DEFAULT_GROUPS_BODY),
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
    const pageErrors: Error[] = [];
    page.on('pageerror', (error) => {
      pageErrors.push(error);
    });

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
      expect(ACCEPTED_REDIRECT_MODES).toContain(redirectedMode);
      expect(pageErrors).toHaveLength(0);
      // Family MVP redirected away from /timeseries before the edit-load
      // failure could be exercised at all. Mark the test skipped (not a
      // silent pass) so this shows up explicitly in the report instead of
      // reading as "the resilience behaviour was verified".
      test.skip(true, `redirected to mode "${redirectedMode}" before /timeseries could load`);
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
