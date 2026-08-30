import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UNAUTHORIZED_EVENT } from '@/api';

// Coverage for issue #7410: the /demo?token=<...> route that applies a
// demo-mint token (#7409), skips the Cognito/Google sign-in wall, and flags
// the session read-only via AuthContext. Does NOT cover hiding individual
// mutating controls — that is #7411.

const CONFIG_WITH_AUTH = {
  google_auth_enabled: true,
  google_client_id: 'client-123',
  disable_auth: false,
};

const stubConfigOnlyFetch = () =>
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (String(url).endsWith('/config.json')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }
      return Promise.resolve({ ok: false });
    }),
  );

const mountRoot = async () => {
  document.body.innerHTML = '<div id="root"></div>';
  const { Root } = await import('@/main');
  const { AuthProvider } = await import('@/AuthContext');
  const { UserProvider } = await import('@/UserContext');
  return render(
    <AuthProvider>
      <UserProvider>
        <BrowserRouter>
          <Root />
        </BrowserRouter>
      </UserProvider>
    </AuthProvider>,
  );
};

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.resetModules();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.pushState({}, '', '/');
});

describe('bootstrapRuntimeConfig — demo token wiring (issue #7410)', () => {
  it('applies a /demo?token=<...> token as the auth token and never redirects to the hosted UI', async () => {
    window.history.pushState({}, '', '/demo?token=demo-token-abc');

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    const setAuthToken = vi.fn();
    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue(CONFIG_WITH_AUTH),
        getStoredAuthToken: vi.fn(() => null),
        setAuthToken,
      };
    });

    document.body.innerHTML = '<div id="root"></div>';
    stubConfigOnlyFetch();

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    expect(setAuthToken).toHaveBeenCalledWith('demo-token-abc');
    // ensureAwsUiAuth (and thus a hosted-UI code/token exchange) never ran:
    // the only fetch made was the /config.json bootstrap request.
    const fetchCalls = (fetch as ReturnType<typeof vi.fn>).mock.calls;
    expect(fetchCalls).toHaveLength(1);
    expect(String(fetchCalls[0][0])).toContain('/config.json');
  });

  it('strips the token from the URL after applying it', async () => {
    window.history.pushState({}, '', '/demo?token=demo-token-abc');

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));
    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue(CONFIG_WITH_AUTH),
        getStoredAuthToken: vi.fn(() => null),
      };
    });
    document.body.innerHTML = '<div id="root"></div>';
    stubConfigOnlyFetch();

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    expect(window.location.pathname).toBe('/');
    expect(window.location.search).toBe('');
  });

  it('marks the tab as a demo session in sessionStorage', async () => {
    window.history.pushState({}, '', '/demo?token=demo-token-abc');

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));
    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue(CONFIG_WITH_AUTH),
        getStoredAuthToken: vi.fn(() => null),
      };
    });
    document.body.innerHTML = '<div id="root"></div>';
    stubConfigOnlyFetch();

    await import('@/main');
    await new Promise((r) => setTimeout(r, 0));

    expect(window.sessionStorage.getItem('demoSession')).toBe('true');
  });
});

describe('Root — demo session rendering (issue #7410)', () => {
  it('skips the sign-in wall and renders the app with demoReadOnly true when a demo session is active', async () => {
    window.sessionStorage.setItem('demoSession', 'true');

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue(CONFIG_WITH_AUTH),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    vi.doMock('@/LoginPage', () => ({
      default: () => <div data-testid="login-page">sign in</div>,
    }));

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">App ready</div>,
    }));

    await mountRoot();

    expect(await screen.findByTestId('app-shell')).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
    expect(await screen.findByTestId('demo-readonly-banner')).toBeInTheDocument();
  });

  it('falls through to the normal sign-in flow on a /demo visit with no demo session marker', async () => {
    // No sessionStorage marker set (mirrors a /demo?token= visit with a
    // missing/blank token, which applyDemoTokenFromUrl leaves untouched).
    window.history.pushState({}, '', '/demo');

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue(CONFIG_WITH_AUTH),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    vi.doMock('@/LoginPage', () => ({
      default: () => <div data-testid="login-page">sign in</div>,
    }));

    await mountRoot();

    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
  });

  it('does not render the demo banner for an ordinary authenticated session', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: false,
          google_client_id: '',
          disable_auth: true,
        }),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">App ready</div>,
    }));

    await mountRoot();

    expect(await screen.findByTestId('app-shell')).toBeInTheDocument();
    expect(screen.queryByTestId('demo-readonly-banner')).not.toBeInTheDocument();
  });

  it('returns an expired demo session to the sign-in wall instead of looping (no refresh attempted)', async () => {
    window.sessionStorage.setItem('demoSession', 'true');

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue(CONFIG_WITH_AUTH),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    vi.doMock('@/LoginPage', () => ({
      default: ({ sessionExpired }: { sessionExpired?: boolean }) => (
        <div data-testid="login-page" data-session-expired={String(Boolean(sessionExpired))}>
          sign in
        </div>
      ),
    }));

    vi.doMock('@/App.tsx', async () => {
      const { useEffect } = await import('react');
      function ExpiringDemoApp() {
        useEffect(() => {
          // Simulates the first API call the app shell makes against the
          // now-expired demo token getting rejected with a 401.
          window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
        }, []);
        return <div data-testid="app-shell">App ready</div>;
      }
      return { default: ExpiringDemoApp };
    });

    await mountRoot();

    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(screen.queryByTestId('app-shell')).not.toBeInTheDocument();
    expect(screen.queryByTestId('demo-readonly-banner')).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem('demoSession')).toBeNull();
  });
});

describe('Logout — demo session cleanup (issue #7410)', () => {
  it('clears the demo marker and navigates home without a Cognito redirect', async () => {
    window.sessionStorage.setItem('demoSession', 'true');

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('react-router-dom', async () =>
      vi.importActual<typeof import('react-router-dom')>('react-router-dom'),
    );

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue(CONFIG_WITH_AUTH),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    const cognitoLogout = vi.fn();
    vi.doMock('@/awsUiAuth', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/awsUiAuth')>();
      return { ...mod, cognitoLogout };
    });

    vi.doMock('@/App.tsx', () => ({
      default: ({ onLogout }: { onLogout?: () => void }) => (
        <button type="button" onClick={onLogout}>
          log out
        </button>
      ),
    }));

    await mountRoot();

    const logoutButton = await screen.findByRole('button', { name: 'log out' });
    fireEvent.click(logoutButton);

    await waitFor(() => expect(window.location.pathname).toBe('/'));
    expect(window.sessionStorage.getItem('demoSession')).toBeNull();
    expect(cognitoLogout).not.toHaveBeenCalled();
  });
});
