import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { UNAUTHORIZED_EVENT } from '@/api'

const mountRoot = async () => {
  document.body.innerHTML = '<div id="root"></div>'
  const { Root } = await import('@/main')
  const { AuthProvider } = await import('@/AuthContext')
  const { UserProvider } = await import('@/UserContext')
  return render(
    <AuthProvider>
      <UserProvider>
        <BrowserRouter>
          <Root />
        </BrowserRouter>
      </UserProvider>
    </AuthProvider>,
  )
}

afterEach(() => {
  vi.useRealTimers()
  vi.resetModules()
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('Root bootstrap integration coverage', () => {
  it('shows Google login on first load when auth is enabled and no token is stored', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: true,
          google_client_id: 'client-123',
          disable_auth: false
        }),
        getStoredAuthToken: vi.fn(() => null)
      }
    })

    vi.doMock('@/LoginPage', () => ({
      default: ({ clientId }: { clientId: string }) => (
        <div data-testid="login-page">Login ready for {clientId}</div>
      )
    }))

    const { container } = await mountRoot()

    expect(await screen.findByTestId('login-page')).toHaveTextContent('client-123')
    expect(container.querySelector('[data-testid="route-bootstrap-marker"]'))
      .toHaveAttribute('data-mode', 'group')
    expect(container.querySelector('[data-testid="route-bootstrap-marker"]'))
      .toHaveAttribute('data-route-state', 'auth')
  })

  it('tolerates null allowed_emails while auth is enabled', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: true,
          google_client_id: 'client-123',
          disable_auth: false,
          allowed_emails: null,
        }),
        getStoredAuthToken: vi.fn(() => null)
      }
    })

    vi.doMock('@/LoginPage', () => ({
      default: ({ clientId }: { clientId: string }) => (
        <div data-testid="login-page">Login ready for {clientId}</div>
      )
    }))

    await mountRoot()

    expect(await screen.findByTestId('login-page')).toHaveTextContent('client-123')
  })

  it('restores local-login identity and renders the app when auth is disabled', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: false,
          google_client_id: '',
          disable_auth: true,
          local_login_email: 'demo@example.com'
        }),
        getStoredAuthToken: vi.fn(() => null)
      }
    })

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">App ready</div>
    }))

    await mountRoot()

    expect(await screen.findByTestId('app-shell')).toBeInTheDocument()
    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem('auth.user') ?? '{}')).toMatchObject({
        email: 'demo@example.com'
      })
    )
    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem('user.profile') ?? '{}')).toMatchObject({
        email: 'demo@example.com'
      })
    )
  })

  it('restores stored user context when a token is already present', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    localStorage.setItem('authToken', 'stale-but-present')
    localStorage.setItem('auth.user', JSON.stringify({ email: 'saved@example.com' }))
    localStorage.setItem('user.profile', JSON.stringify({ email: 'saved@example.com', name: 'Saved User' }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: true,
          google_client_id: 'client-123',
          disable_auth: false
        }),
        getStoredAuthToken: vi.fn(() => 'stale-but-present')
      }
    })

    vi.doMock('@/App.tsx', async () => {
      const { useAuth } = await import('@/AuthContext')
      const { useUser } = await import('@/UserContext')
      function RestoredSessionApp() {
        const { user } = useAuth()
        const { profile } = useUser()
        return (
          <div data-testid="restored-session">
            {user?.email} / {profile?.name}
          </div>
        )
      }

      return {
        default: RestoredSessionApp
      }
    })

    await mountRoot()

    await waitFor(() =>
      expect(screen.getByTestId('restored-session')).toHaveTextContent(
        'saved@example.com / Saved User',
      )
    )
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument()
  })

  it('returns to the login page when a stale stored token is rejected with 401 (issue #4674)', async () => {
    // Simulates: localStorage['authToken'] outlived the Cognito session (e.g.
    // sessionStorage was cleared on tab close, or the ID token expired), so
    // Root seeds `authed=true` and renders the app shell — but the first API
    // call the app shell makes 401s against the stale token. The app should
    // clear the stale credential and fall back to the login screen instead of
    // looping on the rejected token.
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    localStorage.setItem('authToken', 'stale-expired-token')

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: true,
          google_client_id: 'client-123',
          disable_auth: false
        }),
        getStoredAuthToken: vi.fn(() => 'stale-expired-token')
      }
    })

    vi.doMock('@/LoginPage', () => ({
      default: () => <div data-testid="login-page">sign in</div>
    }))

    vi.doMock('@/App.tsx', async () => {
      const { useEffect } = await import('react')
      // Simulates App.tsx's own data-fetching effect discovering the stale
      // token is rejected as soon as it mounts and makes its first API call.
      function StaleTokenApp() {
        useEffect(() => {
          window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
        }, [])
        return <div data-testid="app-shell">App ready</div>
      }
      return { default: StaleTokenApp }
    })

    await mountRoot()

    expect(await screen.findByTestId('login-page')).toBeInTheDocument()
    expect(screen.queryByTestId('app-shell')).not.toBeInTheDocument()
    expect(localStorage.getItem('authToken')).toBeNull()
  })

  it('shows login page when backend cfg carries awsUiAuth.enabled and disable_auth=true', async () => {
    // Covers the primary path: backend GET /config is authoritative.
    // /config.json has no awsUiAuth (prop is absent), but the backend response
    // includes it — the case that #4610 was designed to enable.
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: false,
          google_client_id: null,
          disable_auth: true,
          awsUiAuth: {
            enabled: true,
            domain: 'https://cognito.example.com',
            clientId: 'client-from-backend',
          },
        }),
        getStoredAuthToken: vi.fn(() => null),
      }
    })

    vi.doMock('@/LoginPage', () => ({
      default: () => <div data-testid="login-page">sign in</div>
    }))

    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('@/main')
    const { AuthProvider } = await import('@/AuthContext')
    const { UserProvider } = await import('@/UserContext')

    render(
      <AuthProvider>
        <UserProvider>
          <BrowserRouter>
            {/* No awsUiAuth prop — simulates /config.json without the field */}
            <Root />
          </BrowserRouter>
        </UserProvider>
      </AuthProvider>,
    )

    expect(await screen.findByTestId('login-page')).toBeInTheDocument()
  })

  it('shows login page when backend cfg carries awsUiAuth.enabled as the string "true" (issue #4635)', async () => {
    // CDK sometimes serializes booleans as strings, so the backend /config
    // response can carry awsUiAuth.enabled: 'true' instead of boolean true.
    // The coercion in main.tsx (cfgAwsUiAuth?.enabled === 'true') must still
    // force the login page in that case.
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: false,
          google_client_id: null,
          disable_auth: true,
          awsUiAuth: {
            enabled: 'true',
            domain: 'https://cognito.example.com',
            clientId: 'client-from-backend',
          },
        }),
        getStoredAuthToken: vi.fn(() => null),
      }
    })

    vi.doMock('@/LoginPage', () => ({
      default: () => <div data-testid="login-page">sign in</div>
    }))

    await mountRoot()

    expect(await screen.findByTestId('login-page')).toBeInTheDocument()
  })

  it('renders the app without a login page when backend cfg carries awsUiAuth.enabled as the string "false" (issue #4635)', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: false,
          google_client_id: null,
          disable_auth: true,
          awsUiAuth: {
            enabled: 'false',
            domain: 'https://cognito.example.com',
            clientId: 'client-from-backend',
          },
        }),
        getStoredAuthToken: vi.fn(() => null),
      }
    })

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">App ready</div>
    }))

    await mountRoot()

    expect(await screen.findByTestId('app-shell')).toBeInTheDocument()
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument()
  })

  it('shows login page when /config.json awsUiAuth prop is set but disable_auth=true', async () => {
    // Covers the fallback path: /config.json has awsUiAuth but the backend
    // response does not (e.g. older backend deployment).
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: false,
          google_client_id: null,
          disable_auth: true,
        }),
        getStoredAuthToken: vi.fn(() => null),
      }
    })

    vi.doMock('@/LoginPage', () => ({
      default: () => <div data-testid="login-page">sign in</div>
    }))

    document.body.innerHTML = '<div id="root"></div>'
    const { Root } = await import('@/main')
    const { AuthProvider } = await import('@/AuthContext')
    const { UserProvider } = await import('@/UserContext')

    render(
      <AuthProvider>
        <UserProvider>
          <BrowserRouter>
            <Root awsUiAuth={{ enabled: true, domain: 'https://cognito.example.com', clientId: 'client-abc' }} />
          </BrowserRouter>
        </UserProvider>
      </AuthProvider>,
    )

    expect(await screen.findByTestId('login-page')).toBeInTheDocument()
  })

  it('schedules a retry after config failure and cancels it on unmount', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    const getConfig = vi.fn().mockRejectedValue(new Error('network down'))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig,
        getStoredAuthToken: vi.fn(() => null)
      }
    })

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">App ready</div>
    }))

    try {
      const setTimeoutSpy = vi.spyOn(window, 'setTimeout')
      const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout')
      const view = await mountRoot()

      await waitFor(() => expect(getConfig).toHaveBeenCalledTimes(1))
      await waitFor(() =>
        expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 2000)
      )

      view.unmount()

      expect(clearTimeoutSpy).toHaveBeenCalled()
    } finally {
      consoleError.mockRestore()
    }
  })

  it('backs off exponentially across consecutive config failures before recovering', async () => {
    // Asserts the retryDelay = min(30000, 2000 * 2**attempt) sequence in
    // main.tsx's fetchConfig catch handler: three consecutive failures should
    // schedule retries at 2s, 4s, then 8s before the fourth attempt succeeds.
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    const getConfig = vi
      .fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockRejectedValueOnce(new Error('network down'))
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValue({ google_auth_enabled: false, google_client_id: '', disable_auth: true })

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig,
        getStoredAuthToken: vi.fn(() => null)
      }
    })

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">App ready</div>
    }))

    const nativeSetTimeout = window.setTimeout
    const recordedDelays: number[] = []
    // Only intercept the exact retry-scheduling delays fetchConfig's catch
    // handler can produce (2000 * 2**attempt); everything else — including
    // testing-library's own internal waitFor polling timers — must run
    // natively, or waitFor itself deadlocks.
    const expectedRetryDelays = new Set([2000, 4000, 8000])
    const setTimeoutSpy = vi
      .spyOn(window, 'setTimeout')
      .mockImplementation(((callback: TimerHandler, delay?: number, ...args: unknown[]) => {
        if (typeof callback === 'function' && expectedRetryDelays.has(delay ?? -1)) {
          recordedDelays.push(delay as number)
          callback(...args)
          return 0 as unknown as ReturnType<typeof window.setTimeout>
        }
        return nativeSetTimeout(callback as TimerHandler, (delay ?? 0) as number, ...(args as []))
      }) as typeof window.setTimeout)

    try {
      document.body.innerHTML = '<div id="root"></div>'
      const { Root } = await import('@/main')

      render(
        <BrowserRouter>
          <Root />
        </BrowserRouter>,
      )

      await waitFor(() => expect(getConfig).toHaveBeenCalledTimes(4))
      await screen.findByTestId('app-shell')

      expect(recordedDelays).toEqual([2000, 4000, 8000])
    } finally {
      setTimeoutSpy.mockRestore()
      consoleError.mockRestore()
    }
  })

  it('renders the app without restoring an identity when auth is disabled and no local_login_email is configured', async () => {
    vi.doMock('react-dom/client', () => ({
      createRoot: () => ({ render: vi.fn() })
    }))

    vi.doMock('@/api', async importOriginal => {
      const mod = await importOriginal<typeof import('@/api')>()
      return {
        ...mod,
        getConfig: vi.fn().mockResolvedValue({
          google_auth_enabled: false,
          google_client_id: '',
          disable_auth: true
          // No local_login_email: bootstrap must not fabricate an identity.
        }),
        getStoredAuthToken: vi.fn(() => null)
      }
    })

    vi.doMock('@/App.tsx', () => ({
      default: () => <div data-testid="app-shell">App ready</div>
    }))

    await mountRoot()

    expect(await screen.findByTestId('app-shell')).toBeInTheDocument()
    expect(localStorage.getItem('auth.user')).toBeNull()
    expect(localStorage.getItem('user.profile')).toBeNull()
  })
})
