import {
  buildCognitoHostedUiUrl,
  consumeCognitoAuthSession,
  createCognitoAuthSession,
  parseAwsUiAuthConfig,
} from '@/awsUiAuth';
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
    expect(
      parseAwsUiAuthConfig({
        enabled: true,
        domain: 'https://example.auth.eu-west-2.amazoncognito.com',
        clientId: '',
      })
    ).toBeNull();
    expect(
      parseAwsUiAuthConfig({
        enabled: true,
        domain: 'http://example.auth.eu-west-2.amazoncognito.com',
        clientId: 'client',
      })
    ).toBeNull();
    expect(
      parseAwsUiAuthConfig({
        enabled: true,
        domain: 'https://example.auth.eu-west-2.amazoncognito.com/path',
        clientId: 'client',
      })
    ).toBeNull();
  });

  it('builds the Cognito authorization-code redirect URL with PKCE', () => {
    const url = new URL(
      buildCognitoHostedUiUrl(
        {
          enabled: true,
          domain: 'https://example.auth.eu-west-2.amazoncognito.com',
          clientId: 'client-123',
          redirectPath: '/',
        },
        'https://app.example.com',
        {
          state: 'state-123',
          codeVerifier: 'verifier-123',
          codeChallenge: 'challenge-123',
          returnPath: '/portfolio?family=demo',
        }
      )
    );

    expect(url.origin).toBe('https://example.auth.eu-west-2.amazoncognito.com');
    expect(url.pathname).toBe('/oauth2/authorize');
    expect(url.searchParams.get('client_id')).toBe('client-123');
    expect(url.searchParams.get('code_challenge')).toBe('challenge-123');
    expect(url.searchParams.get('code_challenge_method')).toBe('S256');
    expect(url.searchParams.get('redirect_uri')).toBe(
      'https://app.example.com/'
    );
    expect(url.searchParams.get('response_type')).toBe('code');
    expect(url.searchParams.get('scope')).toBe('openid email profile');
    expect(url.searchParams.get('state')).toBe('state-123');
  });

  it('stores and consumes a same-origin Cognito auth session', async () => {
    const session = await createCognitoAuthSession('/portfolio?family=demo');

    expect(session.state).toBeTruthy();
    expect(session.codeVerifier).toBeTruthy();
    expect(session.codeChallenge).toBeTruthy();
    expect(consumeCognitoAuthSession(session.state)).toEqual({
      state: session.state,
      codeVerifier: session.codeVerifier,
      returnPath: '/portfolio?family=demo',
    });
    expect(consumeCognitoAuthSession(session.state)).toBeNull();
  });

  it('rejects a mismatched state without consuming the stored session', async () => {
    const session = await createCognitoAuthSession('/portfolio?family=demo');

    expect(consumeCognitoAuthSession('wrong-state')).toBeNull();
    expect(consumeCognitoAuthSession(session.state)).toEqual({
      state: session.state,
      codeVerifier: session.codeVerifier,
      returnPath: '/portfolio?family=demo',
    });
  });

  it('rejects external return paths from stored Cognito auth sessions', async () => {
    const session = await createCognitoAuthSession('//evil.example/path');

    expect(consumeCognitoAuthSession(session.state)?.returnPath).toBe('/');
  });
});
