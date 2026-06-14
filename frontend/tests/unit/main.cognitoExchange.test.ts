import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-dom/client', () => ({
  createRoot: () => ({ render: vi.fn() }),
}));

const setAuthToken = vi.fn();
const getStoredAuthToken = vi.fn(() => null);
const getApiBase = vi.fn(() => 'http://localhost:8000');
const logout = vi.fn();

vi.mock('@/api', () => ({
  getConfig: vi.fn().mockResolvedValue({}),
  setAuthToken,
  getStoredAuthToken,
  getApiBase,
  setApiBase: vi.fn(),
  logout,
}));

const VALID_COGNITO_SESSION = JSON.stringify({
  idToken: 'cognito-id-token',
  accessToken: 'cognito-access-token',
  expiresAt: Date.now() + 3600 * 1000,
});

const CONFIG_WITH_COGNITO = {
  awsUiAuth: {
    enabled: true,
    domain: 'https://auth.example.test',
    clientId: 'cognito-client-123',
  },
};

const stubConfigOnlyFetch = () =>
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (String(url).endsWith('/config.json')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(CONFIG_WITH_COGNITO),
        });
      }
      return Promise.resolve({ ok: false });
    }),
  );

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  setAuthToken.mockClear();
  logout.mockClear();
  getStoredAuthToken.mockReturnValue(null);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('bootstrapRuntimeConfig — Cognito ID token wiring', () => {
  it('sends the stored Cognito ID token as the API auth token on bootstrap', async () => {
    // API Gateway's Cognito JWT authorizer validates the ID token's `aud` claim,
    // so the ID token must be sent verbatim — never exchanged for a backend JWT.
    sessionStorage.setItem('awsUiAuthSession', VALID_COGNITO_SESSION);
    document.body.innerHTML = '<div id="root"></div>';
    stubConfigOnlyFetch();

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    expect(setAuthToken).toHaveBeenCalledWith('cognito-id-token');
    // The deprecated backend exchange endpoint must no longer be called.
    const cognitoFetch = (fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url]: [string]) => String(url).endsWith('/token/cognito'),
    );
    expect(cognitoFetch).toBeUndefined();
    expect(logout).not.toHaveBeenCalled();
  });

  it('does not set an auth token when no Cognito session is stored', async () => {
    document.body.innerHTML = '<div id="root"></div>';
    stubConfigOnlyFetch();

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    // Without a valid session, ensureAwsUiAuth redirects to the hosted UI before
    // any token is applied, so setAuthToken is never invoked with an ID token.
    expect(setAuthToken).not.toHaveBeenCalled();
    const cognitoFetch = (fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url]: [string]) => String(url).endsWith('/token/cognito'),
    );
    expect(cognitoFetch).toBeUndefined();
  });

  it('re-applies the Cognito ID token on refresh even when a token is already stored', async () => {
    // The ID token is the source of truth; re-applying it on every bootstrap
    // keeps the Authorization header in sync with the (possibly refreshed)
    // Cognito session without any network round-trip.
    sessionStorage.setItem('awsUiAuthSession', VALID_COGNITO_SESSION);
    getStoredAuthToken.mockReturnValue('stale-token');
    document.body.innerHTML = '<div id="root"></div>';
    stubConfigOnlyFetch();

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    expect(setAuthToken).toHaveBeenCalledWith('cognito-id-token');
  });
});
