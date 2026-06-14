import { expect, test, type Page } from '@playwright/test';

const baseUrl = process.env.SMOKE_URL ?? 'http://localhost:5173';

const COGNITO_DOMAIN = 'https://cognito-test.example.com';
const CLIENT_ID = 'test-client-id';
const PKCE_STATE = 'test-pkce-state';
const PKCE_VERIFIER = 'test-pkce-verifier';
const AUTH_CODE = 'test-auth-code';
const COGNITO_ID_TOKEN = 'cognito-id-token';
const COGNITO_ACCESS_TOKEN = 'cognito-access-token';
const BACKEND_ACCESS_TOKEN = 'backend-access-token';

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

test.describe('Cognito hosted UI to backend token exchange', () => {
  test('exchanges the hosted UI callback for a backend token and uses it for API calls', async ({
    page,
  }) => {
    await seedPkceState(page);
    await mockRuntimeConfig(page);
    await mockAppApiEndpoints(page);

    const tokenRequests: { url: string; body: string }[] = [];
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
          expires_in: 3600,
        }),
      });
    });

    const cognitoExchangeRequests: {
      authorization: string | undefined;
      body: { id_token?: string; client_id?: string };
    }[] = [];
    await page.route('**/token/cognito', async (route) => {
      const request = route.request();
      cognitoExchangeRequests.push({
        authorization: request.headers()['authorization'],
        body: JSON.parse(request.postData() ?? '{}'),
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: BACKEND_ACCESS_TOKEN }),
      });
    });

    const configRequests: { authorization: string | undefined }[] = [];
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

    const callbackUrl = new URL('/', baseUrl);
    callbackUrl.searchParams.set('code', AUTH_CODE);
    callbackUrl.searchParams.set('state', PKCE_STATE);

    await page.goto(callbackUrl.href);

    // Wait until the backend token exchange has completed.
    await expect.poll(() => cognitoExchangeRequests.length).toBeGreaterThan(0);

    // The Cognito hosted UI token endpoint was called with the authorization
    // code and PKCE verifier from the simulated callback.
    expect(tokenRequests).toHaveLength(1);
    expect(tokenRequests[0].body).toContain(`code=${AUTH_CODE}`);
    expect(tokenRequests[0].body).toContain(`code_verifier=${PKCE_VERIFIER}`);

    // The /token/cognito exchange carried the Cognito access token as a
    // Bearer header (regression coverage for #4238/#4239).
    expect(cognitoExchangeRequests[0].authorization).toBe(`Bearer ${COGNITO_ACCESS_TOKEN}`);
    expect(cognitoExchangeRequests[0].body.id_token).toBe(COGNITO_ID_TOKEN);
    expect(cognitoExchangeRequests[0].body.client_id).toBe(CLIENT_ID);

    // The exchanged backend token is stored and reused for subsequent API calls.
    await expect.poll(() => page.evaluate(() => window.localStorage.getItem('authToken'))).toBe(
      BACKEND_ACCESS_TOKEN,
    );
    await expect.poll(() => configRequests.length).toBeGreaterThan(0);
    expect(configRequests[0].authorization).toBe(`Bearer ${BACKEND_ACCESS_TOKEN}`);

    // The one-time authorization code/state are stripped from the URL after exchange.
    await expect.poll(() => new URL(page.url()).search).toBe('');
  });
});
