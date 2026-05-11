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
  expiresAt: Date.now() + 3600 * 1000,
});

const CONFIG_WITH_COGNITO = {
  awsUiAuth: {
    enabled: true,
    domain: 'https://auth.example.test',
    clientId: 'cognito-client-123',
  },
};

/** Build a minimal base64url-encoded fake JWT with the given exp offset from now. */
const makeFakeJwt = (expOffsetMs: number) => {
  const exp = Math.floor((Date.now() + expOffsetMs) / 1000);
  const payload = btoa(JSON.stringify({ exp }))
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
  return `eyJhbGciOiJIUzI1NiJ9.${payload}.sig`;
};

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
});

describe('bootstrapRuntimeConfig — Cognito backend token exchange', () => {
  it('exchanges a stored Cognito ID token for a backend JWT on bootstrap', async () => {
    sessionStorage.setItem('awsUiAuthSession', VALID_COGNITO_SESSION);
    document.body.innerHTML = '<div id="root"></div>';

    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (String(url).endsWith('/config.json')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(CONFIG_WITH_COGNITO),
          });
        }
        if (String(url).endsWith('/token/cognito')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ access_token: 'backend-jwt' }),
          });
        }
        return Promise.resolve({ ok: false });
      }),
    );

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    const cognitoFetch = (fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url]: [string]) => String(url).endsWith('/token/cognito'),
    );
    expect(cognitoFetch).toBeDefined();
    const body = JSON.parse(cognitoFetch![1].body as string);
    expect(body.id_token).toBe('cognito-id-token');
    expect(body.client_id).toBe('cognito-client-123');
    expect(setAuthToken).toHaveBeenCalledWith('backend-jwt');
  });

  it('skips backend exchange when no Cognito session is stored', async () => {
    document.body.innerHTML = '<div id="root"></div>';

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

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    const cognitoFetch = (fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url]: [string]) => String(url).endsWith('/token/cognito'),
    );
    expect(cognitoFetch).toBeUndefined();
  });

  it('skips exchange when a non-expired backend JWT is already stored (page refresh)', async () => {
    sessionStorage.setItem('awsUiAuthSession', VALID_COGNITO_SESSION);
    getStoredAuthToken.mockReturnValue(makeFakeJwt(3600 * 1000));
    document.body.innerHTML = '<div id="root"></div>';

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

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    const cognitoFetch = (fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url]: [string]) => String(url).endsWith('/token/cognito'),
    );
    expect(cognitoFetch).toBeUndefined();
  });

  it('re-exchanges when the stored backend JWT is expired', async () => {
    sessionStorage.setItem('awsUiAuthSession', VALID_COGNITO_SESSION);
    getStoredAuthToken.mockReturnValue(makeFakeJwt(-1000)); // expired 1s ago
    document.body.innerHTML = '<div id="root"></div>';

    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (String(url).endsWith('/config.json')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(CONFIG_WITH_COGNITO),
          });
        }
        if (String(url).endsWith('/token/cognito')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ access_token: 'fresh-backend-jwt' }),
          });
        }
        return Promise.resolve({ ok: false });
      }),
    );

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    const cognitoFetch = (fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url]: [string]) => String(url).endsWith('/token/cognito'),
    );
    expect(cognitoFetch).toBeDefined();
    expect(setAuthToken).toHaveBeenCalledWith('fresh-backend-jwt');
  });

  it('clears Cognito session and auth state when backend exchange returns an error', async () => {
    sessionStorage.setItem('awsUiAuthSession', VALID_COGNITO_SESSION);
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
        if (String(url).endsWith('/token/cognito')) {
          return Promise.resolve({ ok: false, status: 401 });
        }
        return Promise.resolve({ ok: false });
      }),
    );

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    expect(consoleError).toHaveBeenCalledWith(
      'Cognito authentication failed — clearing session:',
      expect.any(Error),
    );
    expect(logout).toHaveBeenCalled();
    // Cognito session must be cleared to prevent an infinite retry loop on next page load.
    expect(sessionStorage.getItem('awsUiAuthSession')).toBeNull();
    consoleError.mockRestore();
  });
});
