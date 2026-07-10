import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';

// Full logout lifecycle in Cognito mode (issue #4802): click -> cognitoLogout()
// called -> session cleared -> redirect to the Cognito hosted-UI logout
// endpoint. The unit tests in Menu.test.tsx only assert that the logout
// callback is invoked; this exercises the real callback registered by
// src/main.tsx's Root component end to end.

const assignMock = vi.fn();

const setLocation = () => {
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
};

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
    </AuthProvider>
  );
};

beforeEach(() => {
  setLocation();
  assignMock.mockClear();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.resetModules();
  vi.restoreAllMocks();
});

describe('Logout flow: Cognito mode (#4802)', () => {
  it('clicking logout clears the session and redirects to the Cognito hosted-UI logout endpoint', async () => {
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
          awsUiAuth: {
            enabled: true,
            domain: 'https://cognito.example.test',
            clientId: 'client-abc',
            redirectPath: '/',
          },
        }),
        getStoredAuthToken: vi.fn(() => 'cognito-id-token'),
      };
    });

    vi.doMock('@/LoginPage', () => ({
      default: () => <div data-testid="login-page">sign in</div>,
    }));

    // Render the real Menu component (the actual logout button end users
    // click), not a stand-in, so a regression in Menu's onClick wiring would
    // be caught here too.
    vi.doMock('@/App.tsx', async () => {
      const { default: Menu } = await import('@/components/Menu');
      return {
        default: ({ onLogout }: { onLogout?: () => void }) => (
          <Menu onLogout={onLogout} />
        ),
      };
    });

    window.localStorage.setItem('authToken', 'cognito-id-token');
    window.localStorage.setItem(
      'auth.user',
      JSON.stringify({ email: 'demo@example.test' })
    );
    window.localStorage.setItem(
      'user.profile',
      JSON.stringify({ email: 'demo@example.test' })
    );
    window.sessionStorage.setItem(
      'awsUiAuthSession',
      JSON.stringify({
        idToken: 'cognito-id-token',
        expiresAt: Date.now() + 60_000,
      })
    );

    await mountRoot();

    const preferencesToggle = await screen.findByRole('button', {
      name: i18n.t('app.menuCategories.preferences'),
    });
    fireEvent.click(preferencesToggle);
    const logoutButton = await screen.findByRole('menuitem', {
      name: i18n.t('app.logout'),
    });
    fireEvent.click(logoutButton);

    // cognitoLogout() was called: the hosted-UI logout endpoint is reached
    // via window.location.assign() with the configured client_id.
    await waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1));
    const [redirectUrl] = assignMock.mock.calls[0] as [string];
    expect(redirectUrl).toMatch(/^https:\/\/cognito\.example\.test\/logout\?/);
    expect(redirectUrl).toContain('client_id=client-abc');

    // Session state is cleared before the redirect fires.
    expect(window.sessionStorage.getItem('awsUiAuthSession')).toBeNull();
    expect(window.localStorage.getItem('authToken')).toBeNull();
    expect(window.localStorage.getItem('auth.user')).toBeNull();
    expect(window.localStorage.getItem('user.profile')).toBeNull();

    // The app falls back to the login screen once authed flips to false.
    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(
      screen.queryByRole('menuitem', { name: i18n.t('app.logout') })
    ).not.toBeInTheDocument();
  });
});
