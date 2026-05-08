export interface AwsUiAuthConfig {
  enabled?: boolean | string;
  domain?: string;
  clientId?: string;
  redirectPath?: string;
}

interface StoredSession {
  idToken: string;
  accessToken?: string;
  expiresAt: number;
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
  const raw = window.localStorage.getItem(SESSION_KEY);
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
    window.localStorage.removeItem(SESSION_KEY);
    return null;
  }
};

const storeSession = (payload: {
  id_token: string;
  access_token?: string;
  expires_in?: number;
}) => {
  const expiresInSeconds = Math.max(60, payload.expires_in ?? 3600);
  const session: StoredSession = {
    idToken: payload.id_token,
    accessToken: payload.access_token,
    expiresAt: Date.now() + expiresInSeconds * 1000,
  };
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
};

const hasValidSession = () => {
  const session = loadSession();
  if (!session || session.expiresAt <= Date.now() + 60000) return false;
  return true;
};

const exchangeCode = async (
  config: Required<Pick<AwsUiAuthConfig, 'domain' | 'clientId'>>
) => {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  const state = params.get('state');
  if (!code || !state) return false;

  const expectedState = window.sessionStorage.getItem(STATE_KEY);
  const verifier = window.sessionStorage.getItem(VERIFIER_KEY);
  window.sessionStorage.removeItem(STATE_KEY);
  window.sessionStorage.removeItem(VERIFIER_KEY);
  if (!expectedState || !verifier || state !== expectedState) {
    throw new Error('Invalid AWS UI authentication callback state');
  }

  const tokenParams = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: config.clientId,
    code,
    redirect_uri: redirectUri(),
    code_verifier: verifier,
  });
  const response = await fetch(`${config.domain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: tokenParams.toString(),
  });
  if (!response.ok)
    throw new Error('AWS UI authentication token exchange failed');
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

const redirectToHostedUi = async (
  config: Required<Pick<AwsUiAuthConfig, 'domain' | 'clientId'>>
) => {
  const verifier = randomString(64);
  const state = randomString(32);
  window.sessionStorage.setItem(STATE_KEY, state);
  window.sessionStorage.setItem(VERIFIER_KEY, verifier);
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.clientId,
    redirect_uri: redirectUri(),
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

  const authConfig = { domain, clientId };
  if (await exchangeCode(authConfig)) return true;
  if (hasValidSession()) return true;
  await redirectToHostedUi(authConfig);
  return false;
};
