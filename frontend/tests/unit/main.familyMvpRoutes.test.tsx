import { render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

function AppShellPath() {
  const location = useLocation();
  return <div data-testid="app-shell-path">{location.pathname}</div>;
}

async function renderRootAt(path: string) {
  document.body.innerHTML = '<div id="root"></div>';
  const { Root } = await import('@/main');
  const { AuthProvider } = await import('@/AuthContext');
  const { UserProvider } = await import('@/UserContext');

  return render(
    <AuthProvider>
      <UserProvider>
        <MemoryRouter initialEntries={[path]}>
          <Root />
        </MemoryRouter>
      </UserProvider>
    </AuthProvider>
  );
}

describe('Root Family MVP route gating', () => {
  afterEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('redirects disabled input route to a safe fallback', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          disable_auth: true,
          google_auth_enabled: false,
          local_login_email: 'demo@example.com',
        }),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    vi.doMock('@/App.tsx', () => ({
      default: AppShellPath,
    }));

    await renderRootAt('/input');
    expect(await screen.findByTestId('app-shell-path')).toHaveTextContent('/');
  });
});
