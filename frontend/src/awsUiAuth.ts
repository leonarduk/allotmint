import { stripAuthCallbackParams } from './utils/urlUtils';

export class UserCancelledError extends Error {
  constructor() {
    super('User cancelled Cognito login');
    this.name = 'UserCancelledError';
  }
}

const TOKEN_EXCHANGE_FAILURE_PREFIX =
  'AWS UI authentication token exchange failed';

/**
 * Extracts the OAuth error code (e.g. "invalid_grant") appended to a token
 * exchange failure message, or null if `error` is not such a failure.
 */
export const extractTokenExchangeErrorReason = (
  error: unknown
): string | null => {
  if (!(error instanceof Error)) return null;
  const match = error.message.match(
    new RegExp(`^${TOKEN_EXCHANGE_FAILURE_PREFIX}: (.+)$`)
  );
  return match ? match[1] : null;
};

export interface AwsUiAuthConfig {
  enabled?: boolean | string;
  domain?: string;
  clientId?: string;
  redirectPath?: string;
}

interface StoredSession {
  idToken: string;
  accessToken?: string;
  refreshToken?: string;
  expiresAt: number;
}

interface AuthConfig {
  domain: string;
  clientId: string;
  redirectPath: string;
}

const SESSION_KEY = 'awsUiAuthSession';
const STATE_KEY = 'awsUiAuthState';
const VERIFIER_KEY = 'awsUiAuthCodeVerifier';
const DEFAULT_REDIRECT_PATH = '/';
const SCOPE = 'openid email profile';

const base64UrlEncode = (bytes: Uint8Array) =>
  btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

const randomString = (bytes = 32) => {
  const values = new Uint8Array(bytes);
  crypto.getRandomValues(values);
  return base64UrlEncode(values);
};

const sha256Base64Url = async (value: string) => {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return base64UrlEncode(new Uint8Array(digest));
};

const normaliseDomain = (domain: string) => {
  const trimmed = domain.trim().replace(/\/+$/, '');
  if (!trimmed) return '';
  return trimmed.startsWith('https://') ? trimmed : `https://${trimmed}`;
};

const redirectUri = (redirectPath?: string) => {
  const path = redirectPath?.startsWith('/')
    ? redirectPath
    : DEFAULT_REDIRECT_PATH;
  return `${window.location.origin}${path}`;
};

const loadSession = (): StoredSession | null => {
  // sessionStorage is cleared on tab close, limiting token exposure window.
  const raw = window.sessionStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    if (
      typeof parsed.idToken !== 'string' ||
      typeof parsed.expiresAt !== 'number'
    ) {
      return null;
    }
    return parsed as StoredSession;
  } catch (error) {
    console.warn('Discarding unreadable AWS UI auth session', error);
    window.sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
};

const storeSession = (
  payload: {
    id_token: string;
    access_token?: string;
    refresh_token?: string;
    expires_in?: number;
  },
  // Cognito's refresh_token grant response does not echo a new refresh_token,
  // so a caller refreshing the session passes the existing one to preserve it.
  fallbackRefreshToken?: string,
) => {
  const expiresInSeconds = Math.max(60, payload.expires_in ?? 3600);
  const session: StoredSession = {
    idToken: payload.id_token,
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token ?? fallbackRefreshToken,
    expiresAt: Date.now() + expiresInSeconds * 1000,
  };
  // sessionStorage scopes the token to this tab/session only.
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
};

const hasValidSession = () => {
  const session = loadSession();
  if (!session || session.expiresAt <= Date.now() + 60000) return false;
  return true;
};

/** Returns the stored Cognito ID token if the session is still valid, else null. */
export const getStoredCognitoIdToken = (): string | null => {
  const session = loadSession();
  if (!session || session.expiresAt <= Date.now()) return null;
  return session.idToken;
};

/** Returns the stored Cognito access token if the session is still valid, else null. */
export const getStoredCognitoAccessToken = (): string | null => {
  const session = loadSession();
  if (!session || session.expiresAt <= Date.now()) return null;
  return session.accessToken ?? null;
};

/** Removes the Cognito session from sessionStorage (e.g. after a failed backend exchange). */
export const clearCognitoSession = (): void => {
  window.sessionStorage.removeItem(SESSION_KEY);
};

/**
 * Initiates a Cognito logout by redirecting to the Cognito logout endpoint.
 * Clears the local session before redirecting to ensure a clean state even if
 * the redirect fails. The logout_uri must be pre-registered in the Cognito App
 * Client's "Allowed sign-out URLs" setting.
 */
export const cognitoLogout = (config?: AwsUiAuthConfig | null): void => {
  const domain = normaliseDomain(config?.domain ?? '');
  const clientId = config?.clientId?.trim() ?? '';
  // Clear local session immediately, before any redirect
  clearCognitoSession();
  if (!domain || !clientId) return;
  const logoutUri = window.location.origin + (config?.redirectPath ?? '/');
  const params = new URLSearchParams({
    client_id: clientId,
    logout_uri: logoutUri,
  });
  window.location.assign(`${domain}/logout?${params.toString()}`);
};

/** Epoch-ms expiry of the stored Cognito session, or null when none is stored. */
export const getCognitoSessionExpiresAt = (): number | null => {
  const session = loadSession();
  return session ? session.expiresAt : null;
};

/**
 * Exchanges the stored Cognito refresh token for a fresh ID/access token via the
 * hosted UI's /oauth2/token endpoint (grant_type=refresh_token) and updates the
 * stored session. Returns the new ID token, or null when there is no refresh
 * token / config or the refresh fails. The refresh token is preserved because
 * Cognito does not return a new one on refresh.
 */
export const refreshCognitoSession = async (
  config?: AwsUiAuthConfig | null,
): Promise<string | null> => {
  const session = loadSession();
  const domain = normaliseDomain(config?.domain ?? '');
  const clientId = config?.clientId?.trim() ?? '';
  if (!session?.refreshToken || !domain || !clientId) return null;

  const params = new URLSearchParams({
    grant_type: 'refresh_token',
    client_id: clientId,
    refresh_token: session.refreshToken,
  });
  const response = await fetch(`${domain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  });
  if (!response.ok) return null;
  const data = (await response.json()) as {
    id_token?: string;
    access_token?: string;
    expires_in?: number;
  };
  if (!data.id_token) return null;
  storeSession(
    {
      id_token: data.id_token,
      access_token: data.access_token,
      expires_in: data.expires_in,
    },
    session.refreshToken,
  );
  return data.id_token;
};

/**
 * Extracts the OAuth 2.0 `error` field (RFC 6749) from a failed token
 * endpoint response, falling back to the HTTP status when the body is
 * missing, unparseable, or lacks an `error` field.
 */
const extractOAuthErrorCode = async (response: Response): Promise<string> => {
  try {
    const body = (await response.json()) as { error?: unknown };
    if (typeof body?.error === 'string' && body.error) return body.error;
  } catch {
    // Response body was missing or not valid JSON; fall back below.
  }
  return response.status ? `HTTP ${response.status}` : 'unknown_error';
};

const exchangeCode = async (config: AuthConfig) => {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  const state = params.get('state');
  const errorParam = params.get('error');

  // Not an OAuth callback at all (no error and no code/state pair): fall
  // through to redirectToHostedUi as before.
  if (!errorParam && (!code || !state)) return false;

  // This is an OAuth callback (error response, or a code/state pair):
  // unconditionally consume the one-time PKCE credentials and strip the
  // callback params from the URL, regardless of outcome, so a reload never
  // replays a dead code or loops on the same error.
  const expectedState = window.sessionStorage.getItem(STATE_KEY);
  const verifier = window.sessionStorage.getItem(VERIFIER_KEY);
  window.sessionStorage.removeItem(STATE_KEY);
  window.sessionStorage.removeItem(VERIFIER_KEY);
  stripAuthCallbackParams(['code', 'state', 'error']);

  // RFC 6749 defines standard OAuth error codes. access_denied = user clicked
  // Cancel on the Cognito hosted UI; other errors are surfaced as-is.
  if (errorParam) {
    if (errorParam === 'access_denied') throw new UserCancelledError();
    throw new Error(`Cognito auth error: ${errorParam}`);
  }
  if (
    !code ||
    !state ||
    !expectedState ||
    !verifier ||
    state !== expectedState
  ) {
    throw new Error('Invalid AWS UI authentication callback state');
  }

  const tokenParams = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: config.clientId,
    code,
    redirect_uri: redirectUri(config.redirectPath),
    code_verifier: verifier,
  });
  const response = await fetch(`${config.domain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: tokenParams.toString(),
  });
  if (!response.ok) {
    throw new Error(
      `${TOKEN_EXCHANGE_FAILURE_PREFIX}: ${await extractOAuthErrorCode(response)}`
    );
  }
  storeSession(
    (await response.json()) as {
      id_token: string;
      access_token?: string;
      expires_in?: number;
    }
  );
  window.history.replaceState(
    {},
    document.title,
    window.location.pathname + window.location.hash
  );
  return true;
};

const redirectToHostedUi = async (config: AuthConfig) => {
  const verifier = randomString(64);
  const state = randomString(32);
  window.sessionStorage.setItem(STATE_KEY, state);
  window.sessionStorage.setItem(VERIFIER_KEY, verifier);
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.clientId,
    redirect_uri: redirectUri(config.redirectPath),
    scope: SCOPE,
    state,
    code_challenge: await sha256Base64Url(verifier),
    code_challenge_method: 'S256',
  });
  window.location.assign(
    `${config.domain}/oauth2/authorize?${params.toString()}`
  );
};

const isEnabled = (value: AwsUiAuthConfig['enabled']) =>
  value === true ||
  (typeof value === 'string' && value.toLowerCase() === 'true');

export const ensureAwsUiAuth = async (config?: AwsUiAuthConfig | null) => {
  if (!isEnabled(config?.enabled)) return true;
  const authConfigInput = config ?? {};
  const domain = normaliseDomain(authConfigInput.domain ?? '');
  const clientId = authConfigInput.clientId?.trim() ?? '';
  if (!domain || !clientId)
    throw new Error('AWS UI authentication is enabled but not configured');

  const redirectPath = authConfigInput.redirectPath ?? DEFAULT_REDIRECT_PATH;
  const authConfig: AuthConfig = { domain, clientId, redirectPath };
  // Session check before code exchange: if the user already has a valid session,
  // skip exchangeCode entirely to avoid a state-mismatch error when ?code= params
  // are present in the URL from a previous (already-consumed) callback.
  if (hasValidSession()) return true;
  // exchangeCode() return value intentionally unused.
  //   true  — OAuth callback present and code exchange succeeded; session stored.
  //   false — no OAuth callback in the URL at all (normal fresh visit).
  // Either way we return true and let React mount the login page.
  // NOTE: exchangeCode() never returns false for *failures* — every error path
  // (state mismatch, expired code, token endpoint error, OAuth error param)
  // throws. Those exceptions propagate to bootstrapRuntimeConfig's .catch(),
  // which renders an error screen with a "Sign in" reload button (recovery path).
  void (await exchangeCode(authConfig));
  return true;
};

/**
 * Initiates a Cognito hosted-UI sign-in by redirecting the browser to the
 * PKCE authorisation endpoint. Call this in response to an explicit user
 * action (e.g. a "Sign in" button click) rather than automatically on page
 * load, so new visitors can reach the create-account page first.
 */
export const signInWithCognito = async (
  config?: AwsUiAuthConfig | null,
): Promise<void> => {
  if (!isEnabled(config?.enabled)) return;
  const domain = normaliseDomain(config?.domain ?? '');
  const clientId = config?.clientId?.trim() ?? '';
  if (!domain || !clientId)
    throw new Error('AWS UI authentication is enabled but not configured');
  const redirectPath = config?.redirectPath ?? DEFAULT_REDIRECT_PATH;
  await redirectToHostedUi({ domain, clientId, redirectPath });
};
