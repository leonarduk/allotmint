import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// A deliberately unusual delay so the Cognito refresh timer's setTimeout call
// can be picked out of the noise of every other setTimeout React/testing-library
// schedules, without racing real wall-clock time to prove cancellation.
const REFRESH_DELAY_MS = 123456;
const sessionDueForRefreshIn = (ms: number) =>
  JSON.stringify({
    idToken: 'cognito-id-token',
    accessToken: 'cognito-access-token',
    refreshToken: 'cognito-refresh-token',
    expiresAt: Date.now() + 5 * 60 * 1000 + ms,
  });

const CONFIG_WITH_COGNITO = {
  awsUiAuth: {
    enabled: true,
    domain: 'https://auth.example.test',
    clientId: 'cognito-client-123',
  },
};

const stubFetch = () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (String(url).endsWith('/config.json')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(CONFIG_WITH_COGNITO),
        });
      }
      return Promise.resolve({ ok: false });
    }),
  );
};

// Finds the setTimeout call that scheduled the Cognito refresh (identified by
// its unusually long delay — a few ms of real time elapse between computing
// the session's expiry and scheduleCognitoRefresh() actually running, so the
// delay won't match REFRESH_DELAY_MS exactly) and returns its timer id.
const findRefreshTimerId = (setTimeoutSpy: ReturnType<typeof vi.spyOn>) => {
  const callIndex = setTimeoutSpy.mock.calls.findIndex(
    ([, delay]) => typeof delay === 'number' && delay > REFRESH_DELAY_MS / 2,
  );
  if (callIndex === -1) return null;
  return setTimeoutSpy.mock.results[callIndex]?.value;
};

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = '<div id="root"></div>';
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Cognito refresh timer cleanup (#4298)', () => {
  it('cancels the pending refresh timer on beforeunload', async () => {
    sessionStorage.setItem('awsUiAuthSession', sessionDueForRefreshIn(REFRESH_DELAY_MS));
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));
    stubFetch();
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout');
    const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout');

    await import('@/main');
    await vi.waitFor(() => expect(findRefreshTimerId(setTimeoutSpy)).not.toBeNull());
    const timerId = findRefreshTimerId(setTimeoutSpy);

    window.dispatchEvent(new Event('beforeunload'));

    expect(clearTimeoutSpy).toHaveBeenCalledWith(timerId);
  });

  it('cancels the pending refresh timer on logout', async () => {
    sessionStorage.setItem('awsUiAuthSession', sessionDueForRefreshIn(REFRESH_DELAY_MS));
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));
    stubFetch();

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: false,
          google_client_id: null,
          disable_auth: true,
        }),
        getStoredAuthToken: vi.fn(() => null),
        logout: vi.fn(),
      };
    });

    vi.doMock('@/App.tsx', () => ({
      default: ({ onLogout }: { onLogout: () => void }) => (
        <button type="button" onClick={onLogout}>
          log out
        </button>
      ),
    }));

    const setTimeoutSpy = vi.spyOn(window, 'setTimeout');
    const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout');

    const { Root } = await import('@/main');
    const { AuthProvider } = await import('@/AuthContext');
    const { UserProvider } = await import('@/UserContext');

    render(
      <AuthProvider>
        <UserProvider>
          <BrowserRouter>
            <Root />
          </BrowserRouter>
        </UserProvider>
      </AuthProvider>,
    );

    const logoutButton = await screen.findByRole('button', { name: /log out/i });
    await waitFor(() => expect(findRefreshTimerId(setTimeoutSpy)).not.toBeNull());
    const timerId = findRefreshTimerId(setTimeoutSpy);

    await userEvent.click(logoutButton);

    expect(clearTimeoutSpy).toHaveBeenCalledWith(timerId);
  });
});
