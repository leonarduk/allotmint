export interface AwsUiAuthConfig {
  enabled: boolean;
  domain: string;
  clientId: string;
  redirectPath: string;
}

const DEFAULT_REDIRECT_PATH = '/';
const AUTH_SCOPES = ['openid', 'email', 'profile'];

let runtimeAwsUiAuth: AwsUiAuthConfig | null = null;

const asTrimmedString = (value: unknown): string =>
  typeof value === 'string' ? value.trim() : '';

const normalizeRedirectPath = (value: unknown): string => {
  const redirectPath = asTrimmedString(value) || DEFAULT_REDIRECT_PATH;
  return redirectPath.startsWith('/') ? redirectPath : `/${redirectPath}`;
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

export const buildCognitoHostedUiUrl = (
  config: AwsUiAuthConfig,
  origin: string,
  returnPath: string
): string => {
  const params = new URLSearchParams({
    client_id: config.clientId,
    redirect_uri: `${origin}${config.redirectPath}`,
    response_type: 'code',
    scope: AUTH_SCOPES.join(' '),
    state: returnPath,
  });

  return `${config.domain}/oauth2/authorize?${params.toString()}`;
};
