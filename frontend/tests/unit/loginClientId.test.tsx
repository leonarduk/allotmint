import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { AUTH_USER_STORAGE_KEY, USER_PROFILE_STORAGE_KEY } from '@/authStorage';

afterEach(async () => {
  cleanup();
  const { setRuntimeAwsUiAuth } = await import('@/awsUiAuth');
  setRuntimeAwsUiAuth(null);
  localStorage.clear();
  vi.resetModules();
});

describe('Root login behaviour', () => {
  it('shows error when clientId is missing', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          disable_auth: false,
          google_auth_enabled: true,
          google_client_id: '',
        }),
        getStoredAuthToken: vi.fn(),
      };
    });

    vi.doMock('@/LoginPage', () => ({
      default: () => <div data-testid="login-page">login-page</div>,
    }));

    document.body.innerHTML = '<div id="root"></div>';
    const { Root } = await import('@/main');
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>
    );
    expect(
      await screen.findByText(/google login is not configured/i)
    ).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).toBeNull();
  });

  it('shows Cognito login when runtime AWS hosted UI auth is configured without Google sign-in', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          disable_auth: false,
          google_auth_enabled: false,
          google_client_id: '',
        }),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    const loginRender = vi.fn(
      ({ awsUiAuth }: { awsUiAuth: { clientId: string } | null }) => (
        <div data-testid="login-page">Cognito {awsUiAuth?.clientId}</div>
      )
    );
    vi.doMock('@/LoginPage', () => ({
      default: loginRender,
    }));

    const { setRuntimeAwsUiAuth } = await import('@/awsUiAuth');
    setRuntimeAwsUiAuth({
      enabled: true,
      domain: 'https://example.auth.eu-west-2.amazoncognito.com',
      clientId: 'aws-client',
      redirectPath: '/',
    });

    document.body.innerHTML = '<div id="root"></div>';
    const { Root } = await import('@/main');
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>
    );

    expect(await screen.findByTestId('login-page')).toHaveTextContent(
      'Cognito aws-client'
    );
    expect(screen.queryByText(/google login is not configured/i)).toBeNull();
  });

  it('completes the Cognito callback and stores the backend token', async () => {
    const setAuthTokenMock = vi.fn();
    const consumeSessionMock = vi.fn(() => ({
      state: 'state-123',
      codeVerifier: 'verifier-123',
      returnPath: '/portfolio?family=demo',
    }));
    const exchangeTokensMock = vi.fn(async () => ({
      id_token: 'cognito-id-token',
    }));
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/awsUiAuth', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/awsUiAuth')>();
      return {
        ...mod,
        consumeCognitoAuthSession: consumeSessionMock,
        exchangeCognitoCodeForTokens: exchangeTokensMock,
      };
    });

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          disable_auth: false,
          google_auth_enabled: false,
          google_client_id: '',
          awsUiAuth: {
            enabled: true,
            domain: 'https://example.auth.eu-west-2.amazoncognito.com',
            clientId: 'aws-client',
            redirectPath: '/auth/callback',
          },
        }),
        getStoredAuthToken: vi.fn(() => null),
        setAuthToken: setAuthTokenMock,
      };
    });

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">app-shell</div>,
    }));

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = input.toString();
      if (url === '/config.json') {
        return { ok: false, json: async () => ({}) } as Response;
      }
      if (url.endsWith('/token/cognito')) {
        return {
          ok: true,
          json: async () => ({ access_token: 'api-token' }),
        } as Response;
      }
      throw new Error(`Unexpected fetch ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    window.history.pushState(
      {},
      '',
      '/auth/callback?code=auth-code&state=state-123'
    );

    document.body.innerHTML = '<div id="root"></div>';
    const { Root } = await import('@/main');
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>
    );

    expect(await screen.findByTestId('app-shell')).toBeInTheDocument();
    await waitFor(() =>
      expect(setAuthTokenMock).toHaveBeenCalledWith('api-token')
    );
    expect(consumeSessionMock).toHaveBeenCalledWith('state-123');
    expect(exchangeTokensMock).toHaveBeenCalledWith(
      expect.objectContaining({ clientId: 'aws-client' }),
      window.location.origin,
      'auth-code',
      'verifier-123'
    );
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/token/cognito',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          client_id: 'aws-client',
          id_token: 'cognito-id-token',
        }),
      })
    );
  });

  it('skips the login screen when an auth token already exists', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          disable_auth: false,
          google_auth_enabled: true,
          google_client_id: 'mock-client',
        }),
        getStoredAuthToken: vi.fn(() => 'persisted-token'),
      };
    });

    const loginRender = vi.fn(() => <div data-testid="login-page">login</div>);
    vi.doMock('@/LoginPage', () => ({
      default: loginRender,
    }));

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">app-shell</div>,
    }));

    localStorage.setItem(
      AUTH_USER_STORAGE_KEY,
      JSON.stringify({ email: 'user@example.com' })
    );
    localStorage.setItem(
      USER_PROFILE_STORAGE_KEY,
      JSON.stringify({ email: 'user@example.com' })
    );

    document.body.innerHTML = '<div id="root"></div>';
    const { Root } = await import('@/main');
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>
    );

    expect(await screen.findByTestId('app-shell')).toBeInTheDocument();
    expect(loginRender).not.toHaveBeenCalled();
  });

  it('does not show the login screen when backend auth is disabled', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          disable_auth: true,
          google_auth_enabled: true,
          google_client_id: 'mock-client',
          local_login_email: 'demo@example.com',
        }),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    const loginRender = vi.fn(() => <div data-testid="login-page">login</div>);
    vi.doMock('@/LoginPage', () => ({
      default: loginRender,
    }));

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">app-shell</div>,
    }));

    const { setRuntimeAwsUiAuth } = await import('@/awsUiAuth');
    setRuntimeAwsUiAuth({
      enabled: true,
      domain: 'https://example.auth.eu-west-2.amazoncognito.com',
      clientId: 'aws-client',
      redirectPath: '/',
    });

    document.body.innerHTML = '<div id="root"></div>';
    const { Root } = await import('@/main');
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>
    );

    expect(await screen.findByTestId('app-shell')).toBeInTheDocument();
    expect(loginRender).not.toHaveBeenCalled();
  });

  it('shows configuration error when auth is enforced without Google sign-in', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          disable_auth: false,
          google_auth_enabled: false,
          google_client_id: '',
          awsUiAuth: { enabled: false },
        }),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    const loginRender = vi.fn(() => <div data-testid="login-page">login</div>);
    vi.doMock('@/LoginPage', () => ({
      default: loginRender,
    }));

    document.body.innerHTML = '<div id="root"></div>';
    const { Root } = await import('@/main');
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>
    );

    expect(
      await screen.findByText(/google login is not configured/i)
    ).toBeInTheDocument();
    expect(loginRender).not.toHaveBeenCalled();
  });

  it('keeps the support route reachable when auth is enforced but Google sign-in is unavailable', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() }),
    }));

    vi.doMock('@/api', async (importOriginal) => {
      const mod = await importOriginal<typeof import('@/api')>();
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          disable_auth: false,
          google_auth_enabled: false,
          google_client_id: '',
        }),
        getStoredAuthToken: vi.fn(() => null),
      };
    });

    vi.doMock('@/pages/Support', () => ({
      default: () => <div data-testid="support-page">support-page</div>,
    }));

    window.history.pushState({}, '', '/support');
    const { setRuntimeAwsUiAuth } = await import('@/awsUiAuth');
    setRuntimeAwsUiAuth({
      enabled: true,
      domain: 'https://example.auth.eu-west-2.amazoncognito.com',
      clientId: 'aws-client',
      redirectPath: '/',
    });

    document.body.innerHTML = '<div id="root"></div>';
    const { Root } = await import('@/main');
    render(
      <BrowserRouter>
        <Root />
      </BrowserRouter>
    );

    expect(await screen.findByTestId('support-page')).toBeInTheDocument();
    expect(screen.queryByText(/google login is not configured/i)).toBeNull();
  });
});
