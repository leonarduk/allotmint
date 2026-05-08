import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ensureAwsUiAuth, UserCancelledError } from '@/awsUiAuth';

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
  it('allows rendering when AWS UI auth is disabled', async () => {
    await expect(ensureAwsUiAuth({ enabled: false })).resolves.toBe(true);
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('redirects to Cognito when enabled is the string "true"', async () => {
    vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => {
      (array as Uint8Array).fill(1);
      return array;
    });
    vi.spyOn(crypto.subtle, 'digest').mockResolvedValue(new Uint8Array(32).buffer);

    const result = await ensureAwsUiAuth({ ...AUTH_CONFIG, enabled: 'true' });
    expect(result).toBe(false);
    expect(assignMock).toHaveBeenCalledTimes(1);
  });

  it('throws when enabled but domain is missing', async () => {
    await expect(
      ensureAwsUiAuth({ enabled: true, clientId: 'client123' })
    ).rejects.toThrow('AWS UI authentication is enabled but not configured');
  });

  it('throws when enabled but clientId is missing', async () => {
    await expect(
      ensureAwsUiAuth({ enabled: true, domain: 'auth.example.test' })
    ).rejects.toThrow('AWS UI authentication is enabled but not configured');
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

  it('uses a configured redirectPath in the hosted UI redirect URL', async () => {
    vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => {
      (array as Uint8Array).fill(1);
      return array;
    });
    vi.spyOn(crypto.subtle, 'digest').mockResolvedValue(new Uint8Array(32).buffer);

    await ensureAwsUiAuth({ ...AUTH_CONFIG, redirectPath: '/callback' });

    const target = new URL(assignMock.mock.calls[0][0]);
    expect(target.searchParams.get('redirect_uri')).toBe(
      'https://app.example.test/callback'
    );
  });

  it('skips redirect when a valid session is already stored', async () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt: Date.now() + 3600 * 1000 })
    );

    await expect(ensureAwsUiAuth(AUTH_CONFIG)).resolves.toBe(true);
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('redirects back to Cognito when session is expired', async () => {
    vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => {
      (array as Uint8Array).fill(1);
      return array;
    });
    vi.spyOn(crypto.subtle, 'digest').mockResolvedValue(new Uint8Array(32).buffer);

    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt: Date.now() - 1000 })
    );

    const result = await ensureAwsUiAuth(AUTH_CONFIG);
    expect(result).toBe(false);
    expect(assignMock).toHaveBeenCalledTimes(1);
  });

  it('throws UserCancelledError and cleans up URL when user cancels (access_denied)', async () => {
    const replaceState = vi.spyOn(window.history, 'replaceState');
    setLocation('?error=access_denied');

    await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toBeInstanceOf(UserCancelledError);
    expect(assignMock).not.toHaveBeenCalled();
    expect(replaceState).toHaveBeenCalledWith({}, document.title, '/');
    expect(window.sessionStorage.getItem('awsUiAuthState')).toBeNull();
    expect(window.sessionStorage.getItem('awsUiAuthCodeVerifier')).toBeNull();
  });

  it('throws when Cognito returns a non-cancellation error', async () => {
    setLocation('?error=server_error');

    await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
      'Cognito auth error: server_error'
    );
    expect(assignMock).not.toHaveBeenCalled();
  });

  describe('token exchange (OAuth callback path)', () => {
    const STORED_STATE = 'test-state-abc';
    const STORED_VERIFIER = 'test-verifier-xyz';

    beforeEach(() => {
      setLocation(`?code=auth-code-123&state=${STORED_STATE}`);
      window.sessionStorage.setItem('awsUiAuthState', STORED_STATE);
      window.sessionStorage.setItem('awsUiAuthCodeVerifier', STORED_VERIFIER);
      vi.spyOn(window.history, 'replaceState').mockImplementation(() => {});
    });

    it('completes token exchange and returns true on success', async () => {
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

      const storedRaw = window.sessionStorage.getItem('awsUiAuthSession');
      expect(storedRaw).not.toBeNull();
      const stored = JSON.parse(storedRaw!);
      expect(stored.idToken).toBe('id-tok');
      expect(stored.accessToken).toBe('access-tok');
    });

    it('uses configured redirectPath in the token exchange request', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ id_token: 'tok', expires_in: 3600 }),
        })
      );

      await ensureAwsUiAuth({ ...AUTH_CONFIG, redirectPath: '/callback' });

      const fetchCall = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = new URLSearchParams(fetchCall[1].body as string);
      expect(body.get('redirect_uri')).toBe('https://app.example.test/callback');
    });

    it('clears the code and state from the URL after exchange', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ id_token: 'tok', expires_in: 3600 }),
        })
      );
      const replaceState = vi.spyOn(window.history, 'replaceState');

      await ensureAwsUiAuth(AUTH_CONFIG);

      expect(replaceState).toHaveBeenCalledWith({}, document.title, '/');
    });

    it('throws on state mismatch', async () => {
      window.sessionStorage.setItem('awsUiAuthState', 'different-state');

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
        'Invalid AWS UI authentication callback state'
      );
    });

    it('throws when token endpoint returns an error response', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
        'AWS UI authentication token exchange failed'
      );
    });
  });
});
