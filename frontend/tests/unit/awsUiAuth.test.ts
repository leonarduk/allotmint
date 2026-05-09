import { buildCognitoHostedUiUrl, parseAwsUiAuthConfig } from '@/awsUiAuth';
import { describe, expect, it } from 'vitest';

describe('awsUiAuth helpers', () => {
  it('parses enabled hosted UI config with normalized domain and redirect path', () => {
    expect(
      parseAwsUiAuthConfig({
        enabled: true,
        domain: 'https://example.auth.eu-west-2.amazoncognito.com/',
        clientId: ' client-123 ',
        redirectPath: 'auth/callback',
      })
    ).toEqual({
      enabled: true,
      domain: 'https://example.auth.eu-west-2.amazoncognito.com',
      clientId: 'client-123',
      redirectPath: '/auth/callback',
    });
  });

  it('ignores absent, disabled, or incomplete hosted UI config', () => {
    expect(parseAwsUiAuthConfig(undefined)).toBeNull();
    expect(parseAwsUiAuthConfig({ enabled: false })).toBeNull();
    expect(
      parseAwsUiAuthConfig({ enabled: true, domain: '', clientId: 'client' })
    ).toBeNull();
  });

  it('builds the Cognito authorization-code redirect URL', () => {
    const url = new URL(
      buildCognitoHostedUiUrl(
        {
          enabled: true,
          domain: 'https://example.auth.eu-west-2.amazoncognito.com',
          clientId: 'client-123',
          redirectPath: '/',
        },
        'https://app.example.com',
        '/portfolio?family=demo'
      )
    );

    expect(url.origin).toBe('https://example.auth.eu-west-2.amazoncognito.com');
    expect(url.pathname).toBe('/oauth2/authorize');
    expect(url.searchParams.get('client_id')).toBe('client-123');
    expect(url.searchParams.get('redirect_uri')).toBe(
      'https://app.example.com/'
    );
    expect(url.searchParams.get('response_type')).toBe('code');
    expect(url.searchParams.get('scope')).toBe('openid email profile');
    expect(url.searchParams.get('state')).toBe('/portfolio?family=demo');
  });
});
