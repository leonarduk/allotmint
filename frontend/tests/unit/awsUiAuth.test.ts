import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearCognitoSession, cognitoLogout, ensureAwsUiAuth, extractTokenExchangeErrorReason, getCognitoSessionExpiresAt, getStoredCognitoAccessToken, getStoredCognitoIdToken, refreshCognitoSession, signInWithCognito, UserCancelledError } from '@/awsUiAuth';

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

  it('returns true without redirecting when enabled is the string "true" and no session', async () => {
    const result = await ensureAwsUiAuth({ ...AUTH_CONFIG, enabled: 'true' });
    expect(result).toBe(true);
    expect(assignMock).not.toHaveBeenCalled();
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

  it('does not auto-redirect unauthenticated users — returns true to let React mount', async () => {
    await expect(ensureAwsUiAuth(AUTH_CONFIG)).resolves.toBe(true);
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('does not invoke exchangeCode when no OAuth callback params are present', async () => {
    // exchangeCode's only externally observable side effect is the token-endpoint
    // fetch, so absence of that call is the proxy for "exchangeCode was not run"
    // (exchangeCode is an unexported module-internal function and, under
    // Vitest/ESM, spying on it directly would not intercept the in-module call
    // from ensureAwsUiAuth anyway).
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(ensureAwsUiAuth(AUTH_CONFIG)).resolves.toBe(true);

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('skips redirect when a valid session is already stored', async () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt: Date.now() + 3600 * 1000 })
    );

    await expect(ensureAwsUiAuth(AUTH_CONFIG)).resolves.toBe(true);
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('skips code exchange when a valid session exists despite stale ?code= in URL', async () => {
    // A stale ?code= with no PKCE verifier in sessionStorage would throw
    // 'Invalid AWS UI authentication callback state' if exchangeCode ran first.
    setLocation('?code=stale-code&state=stale-state');
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt: Date.now() + 3600 * 1000 })
    );

    await expect(ensureAwsUiAuth(AUTH_CONFIG)).resolves.toBe(true);
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('returns true without redirecting when session is expired', async () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt: Date.now() - 1000 })
    );

    const result = await ensureAwsUiAuth(AUTH_CONFIG);
    expect(result).toBe(true);
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('throws UserCancelledError and cleans up URL when user cancels (access_denied)', async () => {
    const replaceState = vi.spyOn(window.history, 'replaceState');
    setLocation('?error=access_denied');

    await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toBeInstanceOf(UserCancelledError);
    expect(assignMock).not.toHaveBeenCalled();
    // Assert against the live pathname rather than a hardcoded '/' so this
    // stays correct if the test's simulated route ever changes (#3962).
    expect(replaceState).toHaveBeenCalledWith({}, document.title, window.location.pathname);
    expect(window.sessionStorage.getItem('awsUiAuthState')).toBeNull();
    expect(window.sessionStorage.getItem('awsUiAuthCodeVerifier')).toBeNull();
  });

  it('preserves non-auth query params when cleaning up after access_denied', async () => {
    const replaceState = vi.spyOn(window.history, 'replaceState');
    setLocation('?error=access_denied&redirect=/dashboard&locale=en');

    await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toBeInstanceOf(UserCancelledError);
    expect(replaceState).toHaveBeenCalledWith(
      {},
      document.title,
      '/?redirect=%2Fdashboard&locale=en'
    );
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
              refresh_token: 'refresh-tok',
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
      // The refresh token is persisted so the session can be silently renewed.
      expect(stored.refreshToken).toBe('refresh-tok');
    });

    it('invokes exchangeCode (hits the token endpoint exactly once) when OAuth callback params are present', async () => {
      // Same proxy reasoning as the "no OAuth params" test above: exchangeCode
      // itself isn't mockable across the module boundary, so we assert on its
      // one externally observable effect — the /oauth2/token fetch call.
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id_token: 'tok', expires_in: 3600 }),
      });
      vi.stubGlobal('fetch', fetchMock);

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).resolves.toBe(true);

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock.mock.calls[0][0]).toBe('https://auth.example.test/oauth2/token');
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

      expect(replaceState).toHaveBeenCalledWith({}, document.title, window.location.pathname);
    });

    it('throws on state mismatch and cleans up URL', async () => {
      const replaceState = vi.spyOn(window.history, 'replaceState');
      window.sessionStorage.setItem('awsUiAuthState', 'different-state');

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
        'Invalid AWS UI authentication callback state'
      );
      expect(replaceState).toHaveBeenCalledWith({}, document.title, window.location.pathname);
      expect(window.sessionStorage.getItem('awsUiAuthState')).toBeNull();
      expect(window.sessionStorage.getItem('awsUiAuthCodeVerifier')).toBeNull();
    });

    it('preserves non-auth query params when cleaning up after a state mismatch', async () => {
      setLocation(`?code=auth-code-123&state=${STORED_STATE}&redirect=/dashboard&locale=en`);
      const replaceState = vi.spyOn(window.history, 'replaceState');
      window.sessionStorage.setItem('awsUiAuthState', 'different-state');

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
        'Invalid AWS UI authentication callback state'
      );
      expect(replaceState).toHaveBeenCalledWith(
        {},
        document.title,
        '/?redirect=%2Fdashboard&locale=en'
      );
    });

    it('throws and cleans up URL when token endpoint returns an error response', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
      const replaceState = vi.spyOn(window.history, 'replaceState');

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
        'AWS UI authentication token exchange failed'
      );
      expect(replaceState).toHaveBeenCalledWith({}, document.title, window.location.pathname);
    });

    it('preserves non-auth query params when cleaning up after a token exchange failure', async () => {
      setLocation(`?code=auth-code-123&state=${STORED_STATE}&redirect=/dashboard&locale=en`);
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
      const replaceState = vi.spyOn(window.history, 'replaceState');

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
        'AWS UI authentication token exchange failed'
      );
      expect(replaceState).toHaveBeenCalledWith(
        {},
        document.title,
        '/?redirect=%2Fdashboard&locale=en'
      );
    });

    it('includes the OAuth error code from the response body when token exchange fails', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ error: 'invalid_grant' }),
        })
      );

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
        'AWS UI authentication token exchange failed: invalid_grant'
      );
    });

    it('falls back to the HTTP status when the error response body has no error field', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: false,
          status: 401,
          json: () => Promise.resolve({}),
        })
      );

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
        'AWS UI authentication token exchange failed: HTTP 401'
      );
    });

    it('falls back to a generic reason when the error response body is unparseable', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));

      await expect(ensureAwsUiAuth(AUTH_CONFIG)).rejects.toThrow(
        'AWS UI authentication token exchange failed: HTTP 500'
      );
    });
  });
});

describe('signInWithCognito', () => {
  const setupCrypto = () => {
    vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => {
      (array as Uint8Array).fill(1);
      return array;
    });
    vi.spyOn(crypto.subtle, 'digest').mockResolvedValue(new Uint8Array(32).buffer);
  };

  it('is a no-op when awsUiAuth is disabled', async () => {
    await signInWithCognito({ enabled: false, domain: 'auth.example.test', clientId: 'client123' });
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('throws when enabled but config is incomplete', async () => {
    await expect(
      signInWithCognito({ enabled: true, domain: 'auth.example.test' })
    ).rejects.toThrow('AWS UI authentication is enabled but not configured');
  });

  it('redirects to the Cognito hosted UI', async () => {
    setupCrypto();
    await signInWithCognito(AUTH_CONFIG);

    expect(assignMock).toHaveBeenCalledTimes(1);
    const target = new URL(assignMock.mock.calls[0][0]);
    expect(target.origin).toBe('https://auth.example.test');
    expect(target.pathname).toBe('/oauth2/authorize');
    expect(target.searchParams.get('response_type')).toBe('code');
    expect(target.searchParams.get('client_id')).toBe('client123');
    expect(target.searchParams.get('redirect_uri')).toBe('https://app.example.test/');
    expect(target.searchParams.get('scope')).toBe('openid email profile');
  });

  it('uses a configured redirectPath in the hosted UI redirect URL', async () => {
    setupCrypto();
    await signInWithCognito({ ...AUTH_CONFIG, redirectPath: '/callback' });

    const target = new URL(assignMock.mock.calls[0][0]);
    expect(target.searchParams.get('redirect_uri')).toBe('https://app.example.test/callback');
  });
});

describe('cognitoLogout', () => {
  it('redirects to the Cognito logout URL when domain and clientId are set', () => {
    cognitoLogout(AUTH_CONFIG);

    expect(assignMock).toHaveBeenCalledTimes(1);
    const target = new URL(assignMock.mock.calls[0][0]);
    expect(target.origin).toBe('https://auth.example.test');
    expect(target.pathname).toBe('/logout');
    expect(target.searchParams.get('client_id')).toBe('client123');
    expect(target.searchParams.get('logout_uri')).toBe('https://app.example.test/');
  });

  it('uses a configured redirectPath in the logout_uri', () => {
    cognitoLogout({ ...AUTH_CONFIG, redirectPath: '/goodbye' });

    const target = new URL(assignMock.mock.calls[0][0]);
    expect(target.searchParams.get('logout_uri')).toBe('https://app.example.test/goodbye');
  });

  it('does not redirect when domain is missing', () => {
    cognitoLogout({ clientId: 'client123' });
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('does not redirect when clientId is missing', () => {
    cognitoLogout({ domain: 'auth.example.test' });
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('does not redirect when config is null/undefined', () => {
    cognitoLogout(null);
    cognitoLogout();
    expect(assignMock).not.toHaveBeenCalled();
  });

  it('clears the local session before redirecting', () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt: Date.now() + 3600 * 1000 }),
    );
    const removeItemSpy = vi.spyOn(Storage.prototype, 'removeItem');

    cognitoLogout(AUTH_CONFIG);

    expect(removeItemSpy).toHaveBeenCalledWith('awsUiAuthSession');
    expect(window.sessionStorage.getItem('awsUiAuthSession')).toBeNull();
    const clearCallOrder = removeItemSpy.mock.invocationCallOrder[0];
    const assignCallOrder = assignMock.mock.invocationCallOrder[0];
    expect(clearCallOrder).toBeLessThan(assignCallOrder);
  });

  it('clears the local session even when config is missing, before returning early', () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt: Date.now() + 3600 * 1000 }),
    );

    cognitoLogout({});

    expect(window.sessionStorage.getItem('awsUiAuthSession')).toBeNull();
    expect(assignMock).not.toHaveBeenCalled();
  });
});

describe('extractTokenExchangeErrorReason', () => {
  it('extracts the OAuth error code from a token exchange failure', () => {
    const error = new Error(
      'AWS UI authentication token exchange failed: invalid_grant'
    );
    expect(extractTokenExchangeErrorReason(error)).toBe('invalid_grant');
  });

  it('returns null for unrelated errors', () => {
    expect(extractTokenExchangeErrorReason(new Error('some other error'))).toBeNull();
  });

  it('returns null for non-Error values', () => {
    expect(extractTokenExchangeErrorReason('oops')).toBeNull();
  });
});

describe('getStoredCognitoIdToken', () => {
  it('returns null when no session is stored', () => {
    expect(getStoredCognitoIdToken()).toBeNull();
  });

  it('returns the id_token from a valid session', () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'my-id-token', expiresAt: Date.now() + 3600 * 1000 }),
    );
    expect(getStoredCognitoIdToken()).toBe('my-id-token');
  });

  it('returns null for an expired session', () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'expired-token', expiresAt: Date.now() - 1000 }),
    );
    expect(getStoredCognitoIdToken()).toBeNull();
  });

  it('returns null for a malformed session entry', () => {
    window.sessionStorage.setItem('awsUiAuthSession', 'not-json');
    expect(getStoredCognitoIdToken()).toBeNull();
  });
});

describe('getStoredCognitoAccessToken', () => {
  it('returns null when no session is stored', () => {
    expect(getStoredCognitoAccessToken()).toBeNull();
  });

  it('returns the access_token from a valid session', () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({
        idToken: 'my-id-token',
        accessToken: 'my-access-token',
        expiresAt: Date.now() + 3600 * 1000,
      }),
    );
    expect(getStoredCognitoAccessToken()).toBe('my-access-token');
  });

  it('returns null when session has no access token (only id token)', () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'my-id-token', expiresAt: Date.now() + 3600 * 1000 }),
    );
    expect(getStoredCognitoAccessToken()).toBeNull();
  });

  it('returns null for an expired session', () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({
        idToken: 'my-id-token',
        accessToken: 'expired-access',
        expiresAt: Date.now() - 1000,
      }),
    );
    expect(getStoredCognitoAccessToken()).toBeNull();
  });

  it('returns null for a malformed session entry', () => {
    window.sessionStorage.setItem('awsUiAuthSession', 'not-json');
    expect(getStoredCognitoAccessToken()).toBeNull();
  });
});

describe('clearCognitoSession', () => {
  it('removes the session from sessionStorage', () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt: Date.now() + 3600 * 1000 }),
    );
    clearCognitoSession();
    expect(window.sessionStorage.getItem('awsUiAuthSession')).toBeNull();
  });

  it('is a no-op when no session is stored', () => {
    expect(() => clearCognitoSession()).not.toThrow();
  });
});

describe('getCognitoSessionExpiresAt', () => {
  it('returns null when no session is stored', () => {
    expect(getCognitoSessionExpiresAt()).toBeNull();
  });

  it('returns the stored expiry timestamp', () => {
    const expiresAt = Date.now() + 3600 * 1000;
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt }),
    );
    expect(getCognitoSessionExpiresAt()).toBe(expiresAt);
  });
});

describe('refreshCognitoSession', () => {
  const storeRefreshableSession = () =>
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({
        idToken: 'old-id',
        accessToken: 'old-access',
        refreshToken: 'refresh-tok',
        expiresAt: Date.now() + 60 * 1000,
      }),
    );

  it('returns null when there is no refresh token in the session', async () => {
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({ idToken: 'tok', expiresAt: Date.now() + 60 * 1000 }),
    );
    await expect(refreshCognitoSession(AUTH_CONFIG)).resolves.toBeNull();
  });

  it('returns null when config is missing domain/clientId', async () => {
    storeRefreshableSession();
    await expect(refreshCognitoSession({ enabled: true })).resolves.toBeNull();
  });

  it('exchanges the refresh token and updates the stored session', async () => {
    storeRefreshableSession();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          id_token: 'new-id',
          access_token: 'new-access',
          expires_in: 3600,
        }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(refreshCognitoSession(AUTH_CONFIG)).resolves.toBe('new-id');

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('https://auth.example.test/oauth2/token');
    const body = new URLSearchParams(init.body as string);
    expect(body.get('grant_type')).toBe('refresh_token');
    expect(body.get('refresh_token')).toBe('refresh-tok');
    expect(body.get('client_id')).toBe('client123');

    const stored = JSON.parse(
      window.sessionStorage.getItem('awsUiAuthSession')!,
    );
    expect(stored.idToken).toBe('new-id');
    expect(stored.accessToken).toBe('new-access');
    // Cognito does not echo a new refresh token; the existing one is preserved.
    expect(stored.refreshToken).toBe('refresh-tok');
  });

  it('returns null when the refresh request fails', async () => {
    storeRefreshableSession();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400 }));
    await expect(refreshCognitoSession(AUTH_CONFIG)).resolves.toBeNull();
    // A failed refresh leaves the existing session untouched for the caller to handle.
    const stored = JSON.parse(
      window.sessionStorage.getItem('awsUiAuthSession')!,
    );
    expect(stored.idToken).toBe('old-id');
  });
});
