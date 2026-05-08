import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ensureAwsUiAuth, getAwsUiAuthIdToken } from '@/awsUiAuth';

const assignMock = vi.fn();

const AUTH_CONFIG = {
  enabled: true as const,
  domain: 'auth.example.test',
  clientId: 'client123',
};

const setLocation = (search = '') => {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      origin: 'https://app.example.test',
      pathname: '/',
      search,
      hash: '',
      assign: assignMock,
    },
  });
};

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  assignMock.mockClear();
  setLocation();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('ensureAwsUiAuth', () => {
  it('allows rendering when disabled', async () => {
    await expect(ensureAwsUiAuth({ enabled: false })).resolves.toBe(true);
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('redirects enabled unauthenticated users to the Cognito hosted UI', async () => {
    vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => {
      const bytes = array as Uint8Array;
      bytes.fill(1);
      return array;
    });
    vi.spyOn(crypto.subtle, 'digest').mockResolvedValue(
      new Uint8Array(32).buffer
    );

    await expect(ensureAwsUiAuth(AUTH_CONFIG)).resolves.toBe(false);

    expect(assignMock).toHaveBeenCalledTimes(1);
    const target = new URL(assignMock.mock.calls[0][0]);
    expect(target.origin).toBe('https://auth.example.test');
    expect(target.pathname).toBe('/oauth2/authorize');
    expect(target.searchParams.get('response_type')).toBe('code');
    expect(target.searchParams.get('client_id')).toBe('client123');
    expect(target.searchParams.get('redirect_uri')).toBe(
      'https://app.example.test/'
    );
    expect(target.searchParams.get('scope')).toBe('openid email profile');
  });

  it('uses redirectPath consistently for hosted UI redirects', async () => {
    vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => array);
    vi.spyOn(crypto.subtle, 'digest').mockResolvedValue(
      new Uint8Array(32).buffer
    );

    await ensureAwsUiAuth({ ...AUTH_CONFIG, redirectPath: '/dashboard' });

    const target = new URL(assignMock.mock.calls[0][0]);
    expect(target.searchParams.get('redirect_uri')).toBe(
      'https://app.example.test/dashboard'
    );
  });

  it('uses the stored session ID token for API authorization', () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'id-token', expiresAt: Date.now() + 3600 * 1000 })
    );

    expect(getAwsUiAuthIdToken()).toBe('id-token');
  });

  it('skips redirect when a valid session is already stored', async () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt: Date.now() + 3600 * 1000 })
    );

    await expect(ensureAwsUiAuth(AUTH_CONFIG)).resolves.toBe(true);
    expect(assignMock).not.toHaveBeenCalled();
  });

  describe('token exchange', () => {
    const storedState = 'test-state-abc';
    const storedVerifier = 'test-verifier-xyz';

    beforeEach(() => {
      setLocation(`?code=auth-code-123&state=${storedState}`);
      window.sessionStorage.setItem('awsUiAuthState', storedState);
      window.sessionStorage.setItem('awsUiAuthCodeVerifier', storedVerifier);
      vi.spyOn(window.history, 'replaceState').mockImplementation(() => {});
    });

    it('stores the ID token in sessionStorage after a successful callback', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () =>
            Promise.resolve({
              id_token: 'id-tok',
              access_token: 'access-tok',
              expires_in: 3600,
            }),
        })
      );

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).resolves.toBe(true);
      expect(assignMock).not.toHaveBeenCalled();
      expect(getAwsUiAuthIdToken()).toBe('id-tok');
    });

    it('uses redirectPath during token exchange', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id_token: 'tok', expires_in: 3600 }),
      });
      vi.stubGlobal('fetch', fetchMock);

      await ensureAwsUiAuth({ ...AUTH_CONFIG, redirectPath: '/dashboard' });

      const body = new URLSearchParams(fetchMock.mock.calls[0][1].body);
      expect(body.get('redirect_uri')).toBe(
        'https://app.example.test/dashboard'
      );
    });

    it('throws on state mismatch', async () => {
      window.sessionStorage.setItem('awsUiAuthState', 'different-state');

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
        'Invalid AWS UI authentication callback state'
      );
    });
  });
});
