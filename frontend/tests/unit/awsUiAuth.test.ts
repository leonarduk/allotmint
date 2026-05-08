import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ensureAwsUiAuth } from '@/awsUiAuth';

const assignMock = vi.fn();

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  assignMock.mockClear();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      origin: 'https://app.example.test',
      pathname: '/',
      search: '',
      hash: '',
      assign: assignMock,
    },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ensureAwsUiAuth', () => {
  it('allows rendering when AWS UI auth is disabled', async () => {
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

    await expect(
      ensureAwsUiAuth({
        enabled: true,
        domain: 'auth.example.test',
        clientId: 'client123',
      })
    ).resolves.toBe(false);

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
});
