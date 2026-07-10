import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';

// Full logout lifecycle in local dev mode (issue #4802): click -> navigate('/')
// -> redirect occurs, with no Cognito hosted-UI round trip. Exercises the real
// logout callback registered by src/main.tsx's Root component end to end,
// rather than a mocked stand-in as in Menu.test.tsx's unit coverage.
//
// src/setupTests.ts globally stubs react-router-dom's useNavigate with a
// no-op vi.fn() (see #4810), so this test opts back into the real hook to
// observe navigate('/') actually changing the browser location.

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
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', '/portfolio/demo-owner');
});

afterEach(() => {
  vi.resetModules();
  vi.restoreAllMocks();
  window.history.pushState({}, '', '/');
});

describe('Logout flow: local dev mode (#4802)', () => {
  it('clicking logout clears the session and navigates to / with no Cognito redirect', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('react-router-dom', async () =>
      vi.importActual<typeof import('react-router-dom')>('react-router-dom')
    );

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: false,
          google_client_id: '',
          disable_auth: true,
          local_login_email: 'demo@example.test',
        }),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    const cognitoLogout = vi.fn();
    vi.doMock('@/awsUiAuth', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/awsUiAuth')>();
      return { ...mod, cognitoLogout };
    });

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

    window.localStorage.setItem(
      'auth.user',
      JSON.stringify({ email: 'demo@example.test' })
    );
    window.localStorage.setItem(
      'user.profile',
      JSON.stringify({ email: 'demo@example.test' })
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

    // navigate('/') was called: the browser location changes to '/'.
    await waitFor(() => expect(window.location.pathname).toBe('/'));

    // Session state is cleared.
    expect(window.localStorage.getItem('auth.user')).toBeNull();
    expect(window.localStorage.getItem('user.profile')).toBeNull();

    // No Cognito hosted-UI round trip in local dev mode.
    expect(cognitoLogout).not.toHaveBeenCalled();

    // Auth is disabled with no awsUiAuth config, so the app shell (not a
    // login screen) remains reachable after the redirect. Menu closes its
    // open category on route change (navigate('/') just fired), so reopen
    // it to confirm the logout control is still there, not that the app
    // fell back to a login/error screen.
    const preferencesToggleAfterLogout = await screen.findByRole('button', {
      name: i18n.t('app.menuCategories.preferences'),
    });
    fireEvent.click(preferencesToggleAfterLogout);
    expect(
      await screen.findByRole('menuitem', { name: i18n.t('app.logout') })
    ).toBeInTheDocument();
  });
});
