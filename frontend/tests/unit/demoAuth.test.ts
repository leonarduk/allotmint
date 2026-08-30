import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const setAuthToken = vi.fn();

vi.mock('@/api', () => ({
  setAuthToken,
}));

beforeEach(() => {
  vi.resetModules();
  setAuthToken.mockClear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', '/');
});

afterEach(() => {
  window.history.pushState({}, '', '/');
});

describe('applyDemoTokenFromUrl (issue #7410)', () => {
  it('applies the token, marks the demo session, and strips the URL back to the root', async () => {
    window.history.pushState({}, '', '/demo?token=abc123');
    const { applyDemoTokenFromUrl, isDemoSession } = await import(
      '@/demoAuth'
    );

    const applied = applyDemoTokenFromUrl();

    expect(applied).toBe(true);
    expect(setAuthToken).toHaveBeenCalledWith('abc123');
    expect(isDemoSession()).toBe(true);
    expect(window.location.pathname).toBe('/');
    expect(window.location.search).toBe('');
  });

  it('preserves other query params while stripping the token', async () => {
    window.history.pushState({}, '', '/demo?token=abc123&foo=bar');
    const { applyDemoTokenFromUrl } = await import('@/demoAuth');

    applyDemoTokenFromUrl();

    // The route itself is rewritten to the plain root (there is no bespoke
    // /demo page), so any other query params on the /demo URL are dropped
    // along with the path — nothing downstream depends on them.
    expect(window.location.pathname).toBe('/');
  });

  it('does nothing on a /demo visit with no token', async () => {
    window.history.pushState({}, '', '/demo');
    const { applyDemoTokenFromUrl, isDemoSession } = await import(
      '@/demoAuth'
    );

    const applied = applyDemoTokenFromUrl();

    expect(applied).toBe(false);
    expect(setAuthToken).not.toHaveBeenCalled();
    expect(isDemoSession()).toBe(false);
    expect(window.location.pathname).toBe('/demo');
  });

  it('does nothing on a /demo visit with a blank token', async () => {
    window.history.pushState({}, '', '/demo?token=');
    const { applyDemoTokenFromUrl, isDemoSession } = await import(
      '@/demoAuth'
    );

    expect(applyDemoTokenFromUrl()).toBe(false);
    expect(setAuthToken).not.toHaveBeenCalled();
    expect(isDemoSession()).toBe(false);
  });

  it('does nothing for any other route, even with a token param', async () => {
    window.history.pushState({}, '', '/?token=abc123');
    const { applyDemoTokenFromUrl } = await import('@/demoAuth');

    expect(applyDemoTokenFromUrl()).toBe(false);
    expect(setAuthToken).not.toHaveBeenCalled();
  });
});

describe('isDemoSession / clearDemoSession', () => {
  it('reflects the sessionStorage marker', async () => {
    const { isDemoSession } = await import('@/demoAuth');
    expect(isDemoSession()).toBe(false);

    window.sessionStorage.setItem('demoSession', 'true');
    expect(isDemoSession()).toBe(true);
  });

  it('clearDemoSession removes the marker', async () => {
    const { isDemoSession, clearDemoSession } = await import('@/demoAuth');
    window.sessionStorage.setItem('demoSession', 'true');

    clearDemoSession();

    expect(isDemoSession()).toBe(false);
  });
});
