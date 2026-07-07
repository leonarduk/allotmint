import { expect, test, type Page } from '@playwright/test';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';

const COGNITO_DOMAIN = 'https://cognito-test.example.com';
const CLIENT_ID = 'test-client-id';
const PKCE_STATE = 'test-pkce-state';
const PKCE_VERIFIER = 'test-pkce-verifier';
const AUTH_CODE = 'test-auth-code';
const COGNITO_ID_TOKEN = 'cognito-id-token';
const COGNITO_ACCESS_TOKEN = 'cognito-access-token';

type TokenRequest = { url: string; body: string };
type ConfigRequest = { authorization: string | undefined };

/**
 * Seed the PKCE state/verifier that awsUiAuth.ts writes before redirecting to
 * the hosted UI, so the simulated callback (?code=...&state=...) is accepted
 * by exchangeCode() instead of being rejected as an invalid callback state.
 */
const seedPkceState = async (page: Page) => {
  await page.addInitScript(
    ({ stateKey, verifierKey, state, verifier }) => {
      window.sessionStorage.setItem(stateKey, state);
      window.sessionStorage.setItem(verifierKey, verifier);
    },
    {
      stateKey: 'awsUiAuthState',
      verifierKey: 'awsUiAuthCodeVerifier',
      state: PKCE_STATE,
      verifier: PKCE_VERIFIER,
    },
  );
};

const mockRuntimeConfig = async (page: Page) => {
  await page.route('**/config.json', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        awsUiAuth: {
          enabled: true,
          domain: COGNITO_DOMAIN,
          clientId: CLIENT_ID,
          redirectPath: '/',
        },
      }),
    });
  });
};

const mockAppApiEndpoints = async (page: Page) => {
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

const mockCognitoTokenEndpoint = async (page: Page, tokenRequests: TokenRequest[]) => {
  await page.route(`${COGNITO_DOMAIN}/oauth2/token`, async (route) => {
    tokenRequests.push({
      url: route.request().url(),
      body: route.request().postData() ?? '',
    });
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id_token: COGNITO_ID_TOKEN,
        access_token: COGNITO_ACCESS_TOKEN,
        refresh_token: 'cognito-refresh-token',
        expires_in: 3600,
      }),
    });
  });
};

/**
 * Records any hit to the deprecated /token/cognito backend exchange so the test
 * can assert it is never called — the frontend now sends the Cognito ID token
 * directly (#4256). Responds with 401 (not 200/empty) because API Gateway's
 * Cognito authorizer rejects this route for real — a 200 here would mask a
 * regression where the frontend starts calling it again (#4259).
 */
const trackBackendTokenExchange = async (page: Page, hits: string[]) => {
  await page.route('**/token/cognito', async (route) => {
    hits.push(route.request().url());
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Unauthorized' }),
    });
  });
};

const mockConfigEndpoint = async (page: Page, configRequests: ConfigRequest[]) => {
  await page.route('**/config', async (route) => {
    configRequests.push({ authorization: route.request().headers()['authorization'] });
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
        disable_auth: false,
        allowed_emails: null,
        local_login_email: null,
        disabled_tabs: [],
        enable_family_mvp: false,
      }),
    });
  });
};

const navigateToCallback = async (page: Page) => {
  const callbackUrl = new URL('/', baseUrl);
  callbackUrl.searchParams.set('code', AUTH_CODE);
  callbackUrl.searchParams.set('state', PKCE_STATE);
  await page.goto(callbackUrl.href);
};

/**
 * The Cognito hosted UI token endpoint was called with the authorization
 * code and PKCE verifier from the simulated callback.
 */
const assertCognitoTokenRequest = (tokenRequests: TokenRequest[]) => {
  expect(tokenRequests).toHaveLength(1);
  expect(tokenRequests[0].body).toContain(`code=${AUTH_CODE}`);
  expect(tokenRequests[0].body).toContain(`code_verifier=${PKCE_VERIFIER}`);
};

/**
 * The Cognito ID token is stored and reused as the Bearer credential for
 * subsequent API calls (the API Gateway authorizer validates its `aud` claim),
 * and the one-time authorization code/state are stripped from the URL (#4256).
 */
const assertIdTokenIsReused = async (page: Page, configRequests: ConfigRequest[]) => {
  await expect
    .poll(() => page.evaluate(() => window.localStorage.getItem('authToken')))
    .toBe(COGNITO_ID_TOKEN);
  await expect.poll(() => configRequests.length).toBeGreaterThan(0);
  expect(configRequests[0].authorization).toBe(`Bearer ${COGNITO_ID_TOKEN}`);
  await expect.poll(() => new URL(page.url()).search).toBe('');
};

test.describe('Cognito hosted UI authentication', () => {
  test('uses the Cognito ID token from the hosted UI callback for API calls', async ({
    page,
  }) => {
    await seedPkceState(page);
    await mockRuntimeConfig(page);
    await mockAppApiEndpoints(page);

    const tokenRequests: TokenRequest[] = [];
    const backendExchangeHits: string[] = [];
    const configRequests: ConfigRequest[] = [];
    await mockCognitoTokenEndpoint(page, tokenRequests);
    await trackBackendTokenExchange(page, backendExchangeHits);
    await mockConfigEndpoint(page, configRequests);

    await navigateToCallback(page);

    // Wait until the ID token has been stored as the API auth token.
    await expect
      .poll(() => page.evaluate(() => window.localStorage.getItem('authToken')))
      .toBe(COGNITO_ID_TOKEN);

    assertCognitoTokenRequest(tokenRequests);
    await assertIdTokenIsReused(page, configRequests);
    // The deprecated backend HS256 exchange must never be called (#4256).
    expect(backendExchangeHits).toHaveLength(0);
  });

  test('recovers by redirecting to the hosted UI when sessionStorage has a corrupted Cognito session (#4258)', async ({
    page,
  }) => {
    // Simulates a session entry that failed to round-trip through JSON (e.g.
    // truncated by a storage quota error). loadSession() in awsUiAuth.ts must
    // discard it rather than throwing, so applyCognitoIdToken() sees no stored
    // ID token and the app falls through to a normal hosted-UI redirect
    // instead of getting stuck on a bootstrap error screen.
    await page.addInitScript(() => {
      window.sessionStorage.setItem('awsUiAuthSession', 'not-valid-json');
    });
    await mockRuntimeConfig(page);
    await page.route(`${COGNITO_DOMAIN}/oauth2/authorize**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<html><body>hosted ui</body></html>',
      });
    });

    await page.goto(baseUrl);

    await expect.poll(() => new URL(page.url()).origin).toBe(new URL(COGNITO_DOMAIN).origin);
    // The unreadable entry is discarded rather than left behind to re-trigger
    // the same failure on the next load.
    expect(
      await page.evaluate(() => window.sessionStorage.getItem('awsUiAuthSession')),
    ).toBeNull();
  });
});
