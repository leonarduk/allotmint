import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

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
  vi.clearAllMocks()
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
      const React = await import('react')
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
})
