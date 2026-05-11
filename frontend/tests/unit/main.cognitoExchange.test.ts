import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-dom/client', () => ({
  createRoot: () => ({ render: vi.fn() }),
}));

const setAuthToken = vi.fn();
const getStoredAuthToken = vi.fn(() => null);
const getApiBase = vi.fn(() => 'http://localhost:8000');

vi.mock('@/api', () => ({
  getConfig: vi.fn().mockResolvedValue({}),
  setAuthToken,
  getStoredAuthToken,
  getApiBase,
  setApiBase: vi.fn(),
  logout: vi.fn(),
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

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  setAuthToken.mockClear();
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
    // Allow microtasks from the void bootstrapRuntimeConfig() call to settle.
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
    expect(setAuthToken).not.toHaveBeenCalledWith(expect.stringMatching(/backend/));
  });

  it('logs an error but does not throw when the backend exchange fails', async () => {
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

    await expect(import('@/main')).resolves.toBeDefined();
    await new Promise((r) => setTimeout(r, 0));

    expect(consoleError).toHaveBeenCalledWith(
      'Cognito backend token exchange failed',
      401,
    );
    consoleError.mockRestore();
  });
});
