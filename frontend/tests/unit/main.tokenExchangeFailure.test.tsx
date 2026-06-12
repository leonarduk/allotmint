import type { ReactElement } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

let renderedElement: ReactElement | null = null;

vi.mock('react-dom/client', () => ({
  createRoot: () => ({
    render: (el: ReactElement) => {
      renderedElement = el;
    },
  }),
}));

vi.mock('@/api', () => ({
  getConfig: vi.fn(),
  setAuthToken: vi.fn(),
  getStoredAuthToken: vi.fn(() => null),
  getApiBase: vi.fn(() => 'http://localhost:8000'),
  setApiBase: vi.fn(),
  logout: vi.fn(),
}));

const CONFIG_WITH_COGNITO = {
  awsUiAuth: {
    enabled: true,
    domain: 'https://auth.example.test',
    clientId: 'cognito-client-123',
  },
};

beforeEach(() => {
  renderedElement = null;
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  window.history.replaceState({}, '', '/');
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('bootstrapRuntimeConfig — generic auth bootstrap failure', () => {
  it('renders a "Sign in" retry button when token exchange fails', async () => {
    document.body.innerHTML = '<div id="root"></div>';
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    window.history.replaceState({}, '', '/?code=auth-code-123&state=test-state');
    sessionStorage.setItem('awsUiAuthState', 'test-state');
    sessionStorage.setItem('awsUiAuthCodeVerifier', 'test-verifier');

    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (String(url).endsWith('/config.json')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(CONFIG_WITH_COGNITO),
          });
        }
        if (String(url).endsWith('/oauth2/token')) {
          return Promise.resolve({ ok: false });
        }
        return Promise.resolve({ ok: false });
      }),
    );

    await import('@/main');

    await vi.waitFor(() => expect(renderedElement).not.toBeNull());

    expect(consoleError).toHaveBeenCalledWith(
      'AWS UI authentication bootstrap failed',
      expect.any(Error),
    );

    render(renderedElement!);
    const retryButton = screen.getByRole('button', { name: /sign in/i });
    expect(retryButton).toBeInTheDocument();
    expect(screen.getByText(/Authentication is unavailable/i)).toBeInTheDocument();

    // The dead authorization code must be cleared so a reload restarts the hosted-UI flow.
    expect(window.location.search).toBe('');

    const reloadSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload: reloadSpy },
    });

    await userEvent.click(retryButton);
    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });
});
