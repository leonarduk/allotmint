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

// Session that is still valid (> 60s out, so ensureAwsUiAuth accepts it) but
// inside the 5-minute refresh buffer, so scheduleCognitoRefresh fires a
// zero-delay timer on bootstrap.
const SESSION_DUE_FOR_REFRESH = JSON.stringify({
  idToken: 'cognito-id-token',
  accessToken: 'cognito-access-token',
  refreshToken: 'cognito-refresh-token',
  expiresAt: Date.now() + 4 * 60 * 1000,
});

const CONFIG_WITH_COGNITO = {
  awsUiAuth: {
    enabled: true,
    domain: 'https://auth.example.test',
    clientId: 'cognito-client-123',
  },
};

const flushMacrotasks = async (times = 4) => {
  for (let i = 0; i < times; i += 1) {
    await new Promise((r) => setTimeout(r, 0));
  }
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

  it('silently refreshes the ID token before it expires and re-applies it', async () => {
    sessionStorage.setItem('awsUiAuthSession', SESSION_DUE_FOR_REFRESH);
    document.body.innerHTML = '<div id="root"></div>';

    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (String(url).endsWith('/config.json')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(CONFIG_WITH_COGNITO),
          });
        }
        if (String(url).endsWith('/oauth2/token')) {
          // The hosted UI token endpoint must be called with a refresh grant.
          expect(String(init?.body)).toContain('grant_type=refresh_token');
          expect(String(init?.body)).toContain('refresh_token=cognito-refresh-token');
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                id_token: 'refreshed-id-token',
                access_token: 'refreshed-access-token',
                expires_in: 3600,
              }),
          });
        }
        return Promise.resolve({ ok: false });
      }),
    );

    await import('@/main');
    await flushMacrotasks();

    // The original token is applied at bootstrap, then the refreshed token once
    // the near-expiry timer fires.
    expect(setAuthToken).toHaveBeenCalledWith('cognito-id-token');
    expect(setAuthToken).toHaveBeenCalledWith('refreshed-id-token');
  });

  it('clears the session and logs out when a scheduled refresh fails', async () => {
    sessionStorage.setItem('awsUiAuthSession', SESSION_DUE_FOR_REFRESH);
    document.body.innerHTML = '<div id="root"></div>';
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (String(url).endsWith('/config.json')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(CONFIG_WITH_COGNITO),
          });
        }
        if (String(url).endsWith('/oauth2/token')) {
          return Promise.resolve({ ok: false, status: 400 });
        }
        return Promise.resolve({ ok: false });
      }),
    );

    await import('@/main');
    await flushMacrotasks();

    expect(logout).toHaveBeenCalled();
    expect(sessionStorage.getItem('awsUiAuthSession')).toBeNull();
    consoleError.mockRestore();
  });

  it('clears the session and logs out when applying the ID token throws', async () => {
    // setAuthToken can throw if storage is unavailable (e.g. quota exceeded);
    // the bootstrap must treat that as an auth failure rather than swallowing it.
    sessionStorage.setItem('awsUiAuthSession', VALID_COGNITO_SESSION);
    document.body.innerHTML = '<div id="root"></div>';
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    setAuthToken.mockImplementationOnce(() => {
      throw new Error('storage unavailable');
    });
    stubConfigOnlyFetch();

    await import('@/main');
    await flushMacrotasks();

    expect(consoleError).toHaveBeenCalledWith(
      'Cognito authentication failed — clearing session:',
      expect.any(Error),
    );
    expect(logout).toHaveBeenCalled();
    expect(sessionStorage.getItem('awsUiAuthSession')).toBeNull();
    consoleError.mockRestore();
  });
});
