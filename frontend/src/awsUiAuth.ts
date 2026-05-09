export interface AwsUiAuthConfig {
  enabled: boolean;
  domain: string;
  clientId: string;
  redirectPath: string;
}

export interface CognitoAuthSession {
  state: string;
  codeVerifier: string;
  returnPath: string;
}

export interface CognitoTokenResponse {
  id_token?: string;
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  token_type?: string;
}

const DEFAULT_REDIRECT_PATH = '/';
const AUTH_SCOPES = ['openid', 'email', 'profile'];
const SESSION_STORAGE_KEY = 'allotmint:cognitoAuthSession';

let runtimeAwsUiAuth: AwsUiAuthConfig | null = null;

const asTrimmedString = (value: unknown): string =>
  typeof value === 'string' ? value.trim() : '';

const normalizeRedirectPath = (value: unknown): string => {
  const redirectPath = asTrimmedString(value) || DEFAULT_REDIRECT_PATH;
  return redirectPath.startsWith('/') ? redirectPath : `/${redirectPath}`;
};

const base64UrlEncode = (bytes: Uint8Array): string => {
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

const randomBase64Url = (byteLength: number): string => {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
};

const sha256Base64Url = async (value: string): Promise<string> => {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(value)
  );
  return base64UrlEncode(new Uint8Array(digest));
};

const storage = (): Storage | null => {
  try {
    return window.sessionStorage;
  } catch (error) {
    console.warn('Cognito auth session storage is unavailable', error);
    return null;
  }
};

const safeReturnPath = (returnPath: string): string => {
  if (!returnPath.startsWith('/')) return DEFAULT_REDIRECT_PATH;
  if (returnPath.startsWith('//')) return DEFAULT_REDIRECT_PATH;
  return returnPath;
};

export const parseAwsUiAuthConfig = (
  value: unknown
): AwsUiAuthConfig | null => {
  if (!value || typeof value !== 'object') return null;

  const rawConfig = value as Record<string, unknown>;
  if (rawConfig.enabled !== true) return null;

  const domain = asTrimmedString(rawConfig.domain).replace(/\/+$/, '');
  const clientId = asTrimmedString(rawConfig.clientId);
  const redirectPath = normalizeRedirectPath(rawConfig.redirectPath);
  if (!domain || !clientId) return null;

  return { enabled: true, domain, clientId, redirectPath };
};

export const setRuntimeAwsUiAuth = (config: AwsUiAuthConfig | null): void => {
  runtimeAwsUiAuth = config;
};

export const getRuntimeAwsUiAuth = (): AwsUiAuthConfig | null =>
  runtimeAwsUiAuth;

export const createCognitoAuthSession = async (
  returnPath: string
): Promise<CognitoAuthSession & { codeChallenge: string }> => {
  const codeVerifier = randomBase64Url(64);
  const session = {
    state: randomBase64Url(32),
    codeVerifier,
    returnPath: safeReturnPath(returnPath),
  };
  storage()?.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  return { ...session, codeChallenge: await sha256Base64Url(codeVerifier) };
};

export const consumeCognitoAuthSession = (
  state: string | null
): CognitoAuthSession | null => {
  const rawSession = storage()?.getItem(SESSION_STORAGE_KEY);
  storage()?.removeItem(SESSION_STORAGE_KEY);
  if (!rawSession || !state) return null;

  try {
    const session = JSON.parse(rawSession) as Partial<CognitoAuthSession>;
    if (session.state !== state || !session.codeVerifier) return null;
    return {
      state,
      codeVerifier: session.codeVerifier,
      returnPath: safeReturnPath(session.returnPath ?? DEFAULT_REDIRECT_PATH),
    };
  } catch (error) {
    console.warn('Failed to parse Cognito auth session', error);
    return null;
  }
};

export const buildCognitoHostedUiUrl = (
  config: AwsUiAuthConfig,
  origin: string,
  session: CognitoAuthSession & { codeChallenge: string }
): string => {
  const params = new URLSearchParams({
    client_id: config.clientId,
    code_challenge: session.codeChallenge,
    code_challenge_method: 'S256',
    redirect_uri: `${origin}${config.redirectPath}`,
    response_type: 'code',
    scope: AUTH_SCOPES.join(' '),
    state: session.state,
  });

  return `${config.domain}/oauth2/authorize?${params.toString()}`;
};

export const exchangeCognitoCodeForTokens = async (
  config: AwsUiAuthConfig,
  origin: string,
  code: string,
  codeVerifier: string
): Promise<CognitoTokenResponse> => {
  const body = new URLSearchParams({
    client_id: config.clientId,
    code,
    code_verifier: codeVerifier,
    grant_type: 'authorization_code',
    redirect_uri: `${origin}${config.redirectPath}`,
  });

  const response = await fetch(`${config.domain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!response.ok) throw new Error('Cognito token exchange failed');
  return (await response.json()) as CognitoTokenResponse;
};
